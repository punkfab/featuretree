#!/usr/bin/env python3
"""Collect runs/<mode>/<part>/ into results.json + results.md, and copy final programs / meshes to out/."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
MODES = ("paper", "extended", "pilot_n4")
WHOLE = ("whole_default", "whole_long")
TESS = json.loads((HERE / "stl" / "tessellation.json").read_text())


def load(path):
    m = trimesh.load(path, process=True)
    if isinstance(m, trimesh.Scene):
        m = trimesh.util.concatenate(list(m.geometry.values()))
    return m


def independent_check(gt_path: Path, pred_path: Path, out_mm: Path) -> dict:
    """Map the prediction (model frame: bbox-centre origin, GT max extent = 200) back to GT mm
    coordinates and recompute a plain volumetric IoU with manifold3d, as a cross-check."""
    gt, pred = load(gt_path), load(pred_path)
    centre = (gt.bounds[0] + gt.bounds[1]) / 2.0
    extent = float(np.max(gt.extents))
    pred_mm = pred.copy()
    pred_mm.apply_scale(extent / 200.0)
    pred_mm.apply_translation(centre)
    pred_mm.export(out_mm)
    info = {"pred_faces": int(len(pred.faces)), "pred_watertight": bool(pred.is_watertight),
            "pred_is_volume": bool(pred.is_volume), "pred_bodies": int(pred.body_count),
            "pred_volume_mm3": float(pred_mm.volume), "gt_volume_mm3": float(gt.volume)}
    try:
        inter = trimesh.boolean.intersection([gt, pred_mm], engine="manifold")
        iv = float(inter.volume)
        info["iou_check_mm"] = iv / (float(gt.volume) + float(pred_mm.volume) - iv)
    except Exception as exc:  # noqa: BLE001
        info["iou_check_error"] = repr(exc)[:200]
    return info


def collect_one(mode: str, part: str) -> dict:
    run_dir = HERE / "runs" / mode / part
    row = {"part": part, "mode": mode, "gt_faces": TESS[part]["faces"]}
    status = json.loads((run_dir / "driver_status.json").read_text()) if (run_dir / "driver_status.json").exists() else {}
    row["driver_status"] = status.get("status", "not_run")
    row["subprocess_wall_sec"] = status.get("subprocess_wall_sec")
    fig = run_dir / "figures" / "nist" / part
    rec_path = run_dir / "record.json"
    events = []
    if (fig / "events.jsonl").exists():
        events = [json.loads(line) for line in (fig / "events.jsonl").read_text().splitlines() if line.strip()]
    kinds = lambda k: [e for e in events if e.get("kind") == k]  # noqa: E731
    det = kinds("algo_rebuild")
    opt = [e for e in kinds("optimize") if e.get("enabled")]
    row["det_calls"] = sum(1 for e in det if e.get("outcome") not in ("timeout_cached", "budget_exhausted"))
    row["det_timeouts"] = sum(1 for e in det if e.get("timed_out"))
    row["det_budget_exhausted"] = sum(1 for e in det if e.get("outcome") == "budget_exhausted")
    row["det_ops_returned"] = [e.get("returned") for e in det]
    row["opt_calls"] = len(opt)
    row["opt_ok"] = sum(1 for e in opt if e.get("ok"))
    row["opt_changed"] = sum(1 for e in opt if e.get("ok") and e.get("changed"))
    row["opt_timeouts"] = sum(1 for e in opt if e.get("timed_out"))
    row["opt_errors"] = sorted({str(e.get("error"))[:120] for e in opt if not e.get("ok")})
    if not rec_path.exists():
        row.update(valid_solid=False, failure=f"no record ({row['driver_status']})")
        return row
    rec = json.loads(rec_path.read_text())
    met = rec.get("metrics") or {}
    row.update(
        n_ops=rec.get("n_steps"), iterations=rec.get("iterations"), stop_reason=rec.get("stop_reason"),
        done_by=rec.get("done_by"), error=(rec.get("error") or None), wall_sec=rec.get("wall_sec"),
        score=rec.get("score"), iou=met.get("iou"), gms_raw=met.get("gms_raw"), gms_norm=met.get("gms_norm"),
        cd=met.get("cd"), failure=met.get("failure"), gt_watertight=met.get("gt_watertight"),
        pred_watertight=met.get("pred_watertight"), calls=(rec.get("cost") or {}).get("calls"),
        native=rec.get("native"),
    )
    row["valid_solid"] = bool(met.get("pred_watertight")) and met.get("failure") is None
    out = HERE / "out" / mode
    out.mkdir(parents=True, exist_ok=True)
    if (fig / "best.py").exists():
        code = (fig / "best.py").read_text()
        shutil.copyfile(fig / "best.py", out / f"{part}.py")
        ops = re.findall(r"^r\s*=\s*(\w+)\(", code, re.M)
        row["program"] = str(out / f"{part}.py")
        row["program_ops"] = ops
        row["program_bytes"] = len(code)
        row["best_from_tool"] = None
    if (fig / "best.stl").exists():
        shutil.copyfile(fig / "best.stl", out / f"{part}.stl")
        row["result_stl_model_frame"] = str(out / f"{part}.stl")
        row["result_stl_mm"] = str(out / f"{part}_mm.stl")
        try:
            row.update(independent_check(HERE / "stl" / f"{part}.stl", fig / "best.stl", out / f"{part}_mm.stl"))
        except Exception as exc:  # noqa: BLE001
            row["independent_check_error"] = repr(exc)[:200]
    return row


def collect_whole(variant: str, part: str) -> dict:
    run_dir = HERE / "runs" / variant / part
    row = {"part": part, "mode": variant, "gt_faces": TESS[part]["faces"]}
    status = json.loads((run_dir / "driver_status.json").read_text()) if (run_dir / "driver_status.json").exists() else {}
    row["driver_status"] = status.get("status", "not_run")
    row["subprocess_wall_sec"] = status.get("subprocess_wall_sec")
    if not (run_dir / "record.json").exists():
        row.update(valid_solid=False, failure=f"no record ({row['driver_status']})")
        return row
    rec = json.loads((run_dir / "record.json").read_text())
    met = rec.get("metrics") or {}
    row.update(n_det_ops=rec.get("n_det_ops"), n_ops=rec.get("n_ops"), emit_coverage=rec.get("emit_coverage"),
               build_how=rec.get("build_how"), build_timeout_used=rec.get("build_timeout_used"),
               cadfit_voxel_iou=rec.get("cadfit_voxel_iou"), reconstruct_sec=rec.get("reconstruct_sec"),
               wall_sec=rec.get("total_wall_sec"), score=rec.get("score"), iou=met.get("iou"),
               gms_raw=met.get("gms_raw"), gms_norm=met.get("gms_norm"), cd=met.get("cd"),
               failure=rec.get("failure") or met.get("failure"), pred_watertight=met.get("pred_watertight"),
               native=rec.get("native"), config=rec.get("config"))
    row["valid_solid"] = bool(met.get("pred_watertight")) and met.get("failure") is None and not rec.get("failure")
    out = HERE / "out" / variant
    out.mkdir(parents=True, exist_ok=True)
    if (run_dir / "best.py").exists():
        shutil.copyfile(run_dir / "best.py", out / f"{part}.py")
        row["program"] = str(out / f"{part}.py")
        row["program_ops"] = re.findall(r"^r\s*=\s*(\w+)\(", (run_dir / "best.py").read_text(), re.M)
    if (run_dir / "best.stl").exists():
        shutil.copyfile(run_dir / "best.stl", out / f"{part}.stl")
        row["result_stl_model_frame"] = str(out / f"{part}.stl")
        row["result_stl_mm"] = str(out / f"{part}_mm.stl")
        try:
            row.update(independent_check(HERE / "stl" / f"{part}.stl", run_dir / "best.stl", out / f"{part}_mm.stl"))
        except Exception as exc:  # noqa: BLE001
            row["independent_check_error"] = repr(exc)[:200]
    return row


def fmt(v, nd=3):
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "NO"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def main() -> None:
    parts = sorted(TESS)
    results = {"tessellation": TESS, "runs": {}}
    md = ["# CADFather algorithmic tools only (det + optimize), NIST CTC/FTC parts",
          "",
          "NOT full CADFather: the CADENA generator VLM (`stepwise`) and the Qwen assistant were not run.",
          "A scripted greedy policy (`det_policy.py`) drives the repo's own harness, det and optimizer.",
          "IoU / GMS / CD are CADFather's own metric code (`agent/cad_agent/capabilities/metrics.py`).",
          ""]
    for mode in MODES:
        if not (HERE / "runs" / mode).exists():
            continue
        rows = [collect_one(mode, p) for p in parts if (HERE / "runs" / mode / p).exists()]
        results["runs"][mode] = rows
        title = {"paper": "Run A: agent harness, paper limits (depth 12, det 6, opt 10, exec 120, 30 s/candidate, 1000 s/part)",
                 "extended": "Run B: agent harness, EXTENDED - outside the paper configuration (depth 60, det 60, opt 30, exec 720, 3600 s/part)",
                 "pilot_n4": "Pilot (superseded policy): paper limits, top-4 of each det pool only, cold pool not drained"}[mode]
        md += [f"## {title}", "",
               "| part | GT faces | valid closed solid | ops | IoU | GMS_norm (raw) | CD x1e3 | score | det calls (timeouts) | opt ok/calls | wall s | stop |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            gms = "-" if r.get("gms_norm") is None else f"{r['gms_norm']:.3f} ({r['gms_raw']:.2f})"
            md.append("| " + " | ".join([
                r["part"], str(r["gt_faces"]), fmt(r.get("valid_solid")), fmt(r.get("n_ops")), fmt(r.get("iou")), gms,
                fmt(r.get("cd"), 2), fmt(r.get("score")), f"{r.get('det_calls')} ({r.get('det_timeouts')})",
                f"{r.get('opt_ok')}/{r.get('opt_calls')}", fmt(r.get("wall_sec"), 0),
                str(r.get("stop_reason") or r.get("failure") or r.get("driver_status")),
            ]) + " |")
        ious = [r["iou"] for r in rows if r.get("iou") is not None]
        if rows:
            md += ["", f"Mean IoU over parts with an IoU: {np.mean(ious):.3f} (n={len(ious)} of {len(rows)}); "
                       f"mean with failures as 0: {sum(ious) / len(rows):.3f}; "
                       f"mean score (mean of IoU and GMS_norm, failures 0): {np.mean([r.get('score') or 0.0 for r in rows]):.3f}", ""]
    for variant in WHOLE:
        if not (HERE / "runs" / variant).exists():
            continue
        rows = [collect_whole(variant, p) for p in parts if (HERE / "runs" / variant / p).exists()]
        results["runs"][variant] = rows
        title = {"whole_default": "Run C: cadfit `cadfit_reconstruct` whole-part, library defaults (NOT the agent's det wrapper; no op cap; outside the paper configuration)",
                 "whole_long": "Run C-long: `cadfit_reconstruct` with n_residual_iters=4, max_residual_ops=40, 900 s budget (outside the paper configuration)"}[variant]
        md += [f"## {title}", "",
               "| part | GT faces | valid closed solid | ops built / det ops | IoU | GMS_norm (raw) | CD x1e3 | score | cadfit voxel IoU | build path | wall s |",
               "|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            gms = "-" if r.get("gms_norm") is None else f"{r['gms_norm']:.3f} ({r['gms_raw']:.2f})"
            md.append("| " + " | ".join([
                r["part"], str(r["gt_faces"]), fmt(r.get("valid_solid")), f"{fmt(r.get('n_ops'))} / {fmt(r.get('n_det_ops'))}",
                fmt(r.get("iou")), gms, fmt(r.get("cd"), 2), fmt(r.get("score")), fmt(r.get("cadfit_voxel_iou")),
                str(r.get("build_how") or r.get("failure") or r.get("driver_status")), fmt(r.get("wall_sec"), 0),
            ]) + " |")
        ious = [r["iou"] for r in rows if r.get("iou") is not None]
        if rows and ious:
            md += ["", f"Mean IoU over parts with an IoU: {np.mean(ious):.3f} (n={len(ious)} of {len(rows)}); "
                       f"mean with failures as 0: {sum(ious) / len(rows):.3f}; "
                       f"mean score (failures 0): {np.mean([r.get('score') or 0.0 for r in rows]):.3f}", ""]
    (HERE / "results.json").write_text(json.dumps(results, indent=2, default=str))
    (HERE / "results.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
