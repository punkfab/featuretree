#!/usr/bin/env python3
"""Sweep run_part.py over the 11 NIST meshes: per-part subprocesses, hard timeouts, N concurrent.

    cf_env/bin/python sweep.py paper|extended [--jobs 3] [--parts a,b,...]
Outputs: runs/<mode>/<part>/ (harness run dir), out/<mode>/<part>.py|.stl|_mm.stl, and collect.py
then builds results.json / results.md.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = HERE.parent / "cf_env" / "bin" / "python"
# Soft per-part wall caps live in the harness config (1000 s paper / 3600 s extended). The hard kill
# leaves room for one last started unit of work (det call 180 s + candidate builds + final scoring).
HARD_TIMEOUT = {"paper": 1000 + 600, "extended": 3600 + 900}


def run_one(part: str, mode: str) -> dict:
    run_dir = HERE / "runs" / mode / part
    run_dir.mkdir(parents=True, exist_ok=True)
    log = open(run_dir / "driver.log", "w")
    started = time.time()
    proc = subprocess.Popen([str(PY), str(HERE / "run_part.py"), str(HERE / "stl" / f"{part}.stl"), str(run_dir), mode],
                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    status = "ok"
    try:
        rc = proc.wait(timeout=HARD_TIMEOUT[mode])
        if rc != 0:
            status = f"exit_{rc}"
    except subprocess.TimeoutExpired:
        status = "hard_timeout"
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
    wall = time.time() - started
    (run_dir / "driver_status.json").write_text(json.dumps({"part": part, "mode": mode, "status": status, "subprocess_wall_sec": wall}))
    print(f"[{time.strftime('%H:%M:%S')}] {mode} {part}: {status} in {wall:.0f}s", flush=True)
    return {"part": part, "status": status, "wall": wall}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["paper", "extended"])
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--parts", default="")
    args = ap.parse_args()
    parts = [p for p in args.parts.split(",") if p] or sorted(p.stem for p in (HERE / "stl").glob("*.stl"))
    with ThreadPoolExecutor(args.jobs) as pool:
        list(pool.map(lambda p: run_one(p, args.mode), parts))
    subprocess.run([str(PY), str(HERE / "collect.py")], check=False)


if __name__ == "__main__":
    main()
