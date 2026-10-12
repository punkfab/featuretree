#!/usr/bin/env python3
"""Run C: cadfit's own whole-part reconstruction (`cadfit_reconstruct`) on ONE target STL.

This is NOT how the CADFather agent uses det (the agent appends one det op per call and is capped at
6 det calls). Here cadfit composes its full union/cut assembly itself (occupancy space), the ops are
emitted in the agent's DSL with the repo's emitter (`vendor/image2cad/cadgen_emit.emit_cadgen`), the
program is built with the agent's executor and scored with the agent's metric code. No op cap.

    cf_env/bin/python run_cadfit_whole.py <part.stl> <run_dir> [default|long]
      default: cadfit_reconstruct defaults (n_residual_iters=1, max_residual_ops=10, DET_TIME_BUDGET=95 s)
      long:    n_residual_iters=4, max_residual_ops=40, DET_TIME_BUDGET=900 s
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT = HERE.parent / "cadfather" / "agent"
sys.path.insert(0, str(AGENT))
os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

VARIANTS = {"default": dict(n_residual_iters=1, max_residual_ops=10, budget=95),
            "long": dict(n_residual_iters=4, max_residual_ops=40, budget=900)}
BUILD_TIMEOUTS = (30.0, 300.0)   # paper's per-candidate cap first, then a relaxed one (flagged)


def main() -> None:
    stl, run_dir = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    variant = sys.argv[3] if len(sys.argv) > 3 else "default"
    cfg = VARIANTS[variant]
    os.environ["DET_TIME_BUDGET"] = str(cfg["budget"])
    run_dir.mkdir(parents=True, exist_ok=True)

    from cad_agent import dsl_runtime

    dsl_runtime.configure("wrapped")
    dsl_runtime.verify_dialect()
    dsl_runtime.apply_thread_limits(1)
    dsl_runtime.apply_graphics_limits()

    import numpy as np
    import trimesh

    from cad_agent.capabilities import det, execute, metrics as metrics_mod
    from cad_agent.capabilities import code as code_utils

    execute.preload_cad()
    dsl_runtime.import_det_deps()
    from cadfit.candidates.cadfit_pass import cadfit_reconstruct, emit_cadquery
    from cadgen_emit import emit_cadgen

    record: dict = {"part": stl.stem, "variant": variant, "config": cfg,
                    "native": dsl_runtime.cadfit_native_status()}
    frame_path = det.gt_frame_path(stl, run_dir / "_gt_frame")
    gt = det.DetProposer._load_mesh(frame_path)

    started = time.time()
    np.random.seed(det.DET_SEED)
    ops, occ_iou, info = cadfit_reconstruct(gt, n_residual_iters=cfg["n_residual_iters"],
                                            max_residual_ops=cfg["max_residual_ops"], verbose=False)
    record["reconstruct_sec"] = time.time() - started
    record["n_det_ops"] = len(ops)
    record["det_ops_sides"] = [side for side, _ in ops]
    record["cadfit_voxel_iou"] = float(occ_iou)
    record["cadfit_info"] = {k: v for k, v in (info or {}).items() if isinstance(v, (int, float, str, bool))}

    code, coverage = emit_cadgen(ops) if ops else (None, 0.0)
    record["emit_coverage"] = coverage
    if code is None:
        record["failure"] = "emit_cadgen produced no program"
        (run_dir / "record.json").write_text(json.dumps(record, indent=2, default=str))
        print(json.dumps(record, indent=2, default=str))
        return
    lines = code.rstrip("\n").split("\n")
    n_head = max(i for i, line in enumerate(lines) if line.strip() == "r = None") + 1
    header, op_lines = "\n".join(lines[:n_head]) + "\n", lines[n_head:]
    # The emitter's header lacks some imports of the agent prefix; use the agent's prefix instead.
    prefix = dsl_runtime.code_prefix()

    def build(program: str, tag: str, timeout: float):
        executor = execute.SerialForkExecutor(timeout=timeout)
        mesh_path = run_dir / f"{tag}.stl"
        mesh_path.unlink(missing_ok=True)
        res = executor.evaluate([execute.EvalTask(task_id=tag, code=program, mesh_path=str(mesh_path))])[0]
        ok = bool(res.success and mesh_path.exists())
        watertight = False
        if ok:
            m = trimesh.load_mesh(mesh_path)
            watertight = metrics_mod.is_watertight(m)
        return ok, watertight, res

    def program_of(op_list):
        return prefix.rstrip("\n") + "\n" + "\n".join(op_list) + "\n"

    attempts = []
    final_code, final_mesh, how, used_timeout = None, None, None, None
    variants = [("full", op_lines), ("full_thinned", [code_utils.thin_polygons(op) for op in op_lines])]
    for timeout in BUILD_TIMEOUTS:
        for tag, op_list in variants:
            ok, wt, res = build(program_of(op_list), tag, timeout)
            attempts.append({"attempt": tag, "timeout": timeout, "built": ok, "watertight": wt,
                             "outcome": res.outcome, "error": (res.error or "")[-300:], "wall_sec": res.wall_sec})
            if ok and wt:
                final_code, final_mesh, how, used_timeout = program_of(op_list), run_dir / f"{tag}.stl", tag, timeout
                break
        if final_code:
            break
    if final_code is None:
        # Keep each op only if the program still builds to a closed solid with it (30 s per build).
        kept: list[str] = []
        for i, op in enumerate(op_lines):
            for cand in (op, code_utils.thin_polygons(op)):
                ok, wt, res = build(program_of(kept + [cand]), "incremental", BUILD_TIMEOUTS[0])
                if ok and wt:
                    kept.append(cand)
                    (run_dir / "incremental.stl").replace(run_dir / "incremental_ok.stl")
                    break
        attempts.append({"attempt": "incremental_skip_failing_ops", "kept": len(kept), "of": len(op_lines)})
        if kept:
            final_code, final_mesh, how, used_timeout = program_of(kept), run_dir / "incremental_ok.stl", "incremental_skip_failing_ops", BUILD_TIMEOUTS[0]
            op_lines = kept
    record["build_attempts"] = attempts
    record["build_how"] = how
    record["build_timeout_used"] = used_timeout
    record["wall_sec"] = time.time() - started
    if final_code is None:
        record["failure"] = "no variant of the program built to a closed solid"
    else:
        (run_dir / "best.py").write_text(final_code)
        best_stl = run_dir / "best.stl"
        if final_mesh != best_stl:
            best_stl.write_bytes(Path(final_mesh).read_bytes())
        record["n_ops"] = sum(1 for l in final_code.split("\n") if l.startswith("r=") )
        gt_mesh = trimesh.load_mesh(stl)
        pred_mesh = trimesh.load_mesh(best_stl)
        metrics_mod.normalize_for_metrics(gt_mesh, pred_mesh)
        fm = metrics_mod.evaluate_pair(figure_id=stl.stem, gt_mesh=gt_mesh, pred_mesh=pred_mesh, compute_cd=True)
        record["metrics"] = fm.to_dict()
        record["score"] = fm.score()
    record["total_wall_sec"] = time.time() - started
    (run_dir / "record.json").write_text(json.dumps(record, indent=2, default=str))
    print(json.dumps({k: v for k, v in record.items() if k != "build_attempts"}, indent=2, default=str))


if __name__ == "__main__":
    main()
