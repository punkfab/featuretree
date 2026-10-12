#!/usr/bin/env python3
"""Run CADFather's algorithmic tools (det_cold / det_warm / optimize) on ONE target STL, no LLM, no GPU.

Uses the repo's own harness (`figure_run.run_figure` + `SearchLoop`) and the paper config
`agent/configs/dialogue_lean.yaml`, with these changes:
  - policy: `det_policy.DetGreedyPolicy` (scripted) instead of `dialogue_lean` (Qwen assistant);
  - tools: [det_cold, det_warm, optimize] (no `stepwise`: the CADENA generator is not available);
  - both vLLM servers disabled; metrics.cd on; local pool sizes; scratch dir on local disk;
  - mode "extended" lifts the caps (see EXTENDED below) and is OUTSIDE the paper configuration.

    cf_env/bin/python run_part.py <part.stl> <run_dir> [paper|extended]
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent / "cadfather"
AGENT = REPO / "agent"
sys.path.insert(0, str(AGENT))
sys.path.insert(0, str(HERE))
os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

import yaml  # noqa: E402

EXTENDED = {
    "limits": {"depth": 60, "iterations": 300},
    "budget": {"det": 60, "opt": 30, "exec": 720, "total": 2000},
    "execution": {"det_budget_sec": 3000},
    "figure_wall_sec": 3600,
    "patience": 12,
}


def build_config(stl_dir: Path, mode: str, scratch: Path, pool_size: int) -> dict:
    config = yaml.safe_load((AGENT / "configs" / "dialogue_lean.yaml").read_text())
    config["launch"]["servers"]["generation"]["enabled"] = False
    config["launch"]["servers"]["assistant"]["enabled"] = False
    exp = config["experiment"]
    exp["details"] = [{"nist": str(stl_dir)}]
    exp["tools"] = ["det_cold", "det_warm", "optimize"]
    exp["metrics"] = {"cd": True}
    exp["n_workers"] = 1
    exp["execution"]["pool_size"] = pool_size
    exp["execution"]["scratch_dir"] = str(scratch)
    exp["logging"]["load"] = False
    if mode == "extended":
        exp["limits"].update(EXTENDED["limits"])
        exp["budget"].update(EXTENDED["budget"])
        exp["execution"].update(EXTENDED["execution"])
        exp["figure_wall_sec"] = EXTENDED["figure_wall_sec"]
    return config


def main() -> None:
    stl = Path(sys.argv[1]).resolve()
    run_dir = Path(sys.argv[2]).resolve()
    mode = sys.argv[3] if len(sys.argv) > 3 else "paper"
    pool_size = int(os.environ.get("CF_POOL_SIZE", "2"))
    run_dir.mkdir(parents=True, exist_ok=True)
    scratch = HERE / "scratch"
    scratch.mkdir(exist_ok=True)

    # One-part "dataset" folder (the harness takes a folder of STLs).
    part_dir = run_dir / "input"
    part_dir.mkdir(exist_ok=True)
    link = part_dir / stl.name
    if not link.exists():
        link.symlink_to(stl)

    config = build_config(part_dir, mode, scratch, pool_size)

    from cad_agent import dsl_runtime

    dsl_runtime.configure(config.get("dsl", dsl_runtime.DEFAULT_DIALECT))
    dsl_runtime.verify_dialect()
    dsl_runtime.apply_thread_limits(int(config["experiment"]["execution"].get("native_threads", 1)))
    dsl_runtime.apply_graphics_limits()

    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                        handlers=[logging.FileHandler(run_dir / "run.log"), logging.StreamHandler()], force=True)

    from cad_agent.capabilities.execute import preload_cad

    preload_cad()

    import run_experiment as run_experiment_mod
    from cad_agent.harness import figure_run
    from cad_agent.harness.dataset import load_figures
    from cad_agent.harness.search import SearchLoop
    from det_policy import DetGreedyPolicy

    run_config = run_experiment_mod.build_run_config(config, None)
    (run_dir / "config.json").write_text(json.dumps(run_config, indent=2, default=str))
    native = {"cadfit_native": dsl_runtime.cadfit_native_status()}
    try:
        dsl_runtime.import_optimizer()
        import _cad_grad

        native["cad_grad"] = {"available": True, "file": _cad_grad.__file__}
    except Exception as exc:  # noqa: BLE001
        native["cad_grad"] = {"available": False, "error": repr(exc)}
    (run_dir / "native.json").write_text(json.dumps(native, indent=2, default=str))

    spec = load_figures(run_config["details"])[0]
    policy = DetGreedyPolicy(patience=EXTENDED["patience"] if mode == "extended" else None)
    started = time.time()
    record = figure_run.run_figure(spec, run_config, SearchLoop(policy), run_dir)
    record["driver_wall_sec"] = time.time() - started
    record["mode"] = mode
    record["native"] = native
    (run_dir / "record.json").write_text(json.dumps(record, indent=2, default=str))
    brief = {k: record.get(k) for k in ("figure_id", "n_steps", "iterations", "stop_reason", "done_by", "error", "score", "wall_sec", "cost")}
    brief["metrics"] = record.get("metrics")
    print(json.dumps(brief, indent=2, default=str))
    from cad_agent.capabilities.execute import shutdown_shared_executors

    shutdown_shared_executors()


if __name__ == "__main__":
    main()
