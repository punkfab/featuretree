#!/usr/bin/env python3
"""Run C sweep: run_cadfit_whole.py over the 11 NIST meshes, one at a time, hard timeout per part.

    cf_env/bin/python sweep_whole.py default|long
"""
import json, os, signal, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = HERE.parent / "cf_env" / "bin" / "python"
variant = sys.argv[1] if len(sys.argv) > 1 else "default"
HARD = {"default": 1200, "long": 3600}[variant]
for stl in sorted((HERE / "stl").glob("*.stl")):
    run_dir = HERE / "runs" / f"whole_{variant}" / stl.stem
    run_dir.mkdir(parents=True, exist_ok=True)
    t = time.time()
    with open(run_dir / "driver.log", "w") as log:
        proc = subprocess.Popen([str(PY), str(HERE / "run_cadfit_whole.py"), str(stl), str(run_dir), variant],
                                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            rc = proc.wait(timeout=HARD)
            status = "ok" if rc == 0 else f"exit_{rc}"
        except subprocess.TimeoutExpired:
            status = "hard_timeout"
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
    (run_dir / "driver_status.json").write_text(json.dumps({"status": status, "subprocess_wall_sec": time.time() - t}))
    print(f"[{time.strftime('%H:%M:%S')}] whole_{variant} {stl.stem}: {status} in {time.time() - t:.0f}s", flush=True)
