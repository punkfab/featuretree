#!/usr/bin/env python3
"""cells_corpus.py — cell_recognize.py on the NIST MBE PMI parts, beside the slicing recogniser.

Each part runs in its own process with a timeout. Results (IR + report) are cached per part in
paper/figures/cells/<part>.json; --fresh reruns. Prints one row per part with the slicing
recogniser's result from corpus_results.json for comparison.

    python3 paper/figures/cells_corpus.py [--fresh] [--timeout 1500] [part-substring ...]
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIG = Path(__file__).resolve().parent
OUT = FIG / "cells"
STEP = Path(os.environ.get("NIST_STEP", Path.home() / "Downloads/NIST-PMI-STEP-Files/AP203 geometry only"))


def main():
    a = sys.argv[1:]
    fresh = "--fresh" in a
    timeout = int(a[a.index("--timeout") + 1]) if "--timeout" in a else 1500
    pick = [x for i, x in enumerate(a) if not x.startswith("-") and (i == 0 or a[i - 1] != "--timeout")]
    OUT.mkdir(exist_ok=True)
    rows = json.loads((FIG / "corpus_results.json").read_text())
    rows = rows.get("results", rows) if isinstance(rows, dict) else rows
    slicer = {r["part"].split(".")[0]: r for r in rows}
    for f in sorted(STEP.glob("nist_*.stp")):
        if pick and not any(k in f.name for k in pick):
            continue
        cache = OUT / f"{f.stem}.json"
        if fresh or not cache.exists():
            try:
                subprocess.run([sys.executable, str(ROOT / "cell_recognize.py"), str(f), "--emit", str(cache)],
                               capture_output=True, timeout=timeout, cwd=ROOT)
            except subprocess.TimeoutExpired:
                pass
        r = json.loads(cache.read_text())["report"] if cache.exists() else {"reason": "timeout or crash"}
        s = slicer.get(f.stem, {})
        print(json.dumps({"part": f.stem, "cells": r.get("cells"), "cuts": r.get("cuts"), "iou_pct": r.get("iou_pct"),
                          "dvol_pct": r.get("dvol_pct"), "verified": r.get("verified"), "s": r.get("total_s"),
                          "unsupported_faces": r.get("unsupported_faces"), "reason": r.get("reason"),
                          "slicer_iou_pct": s.get("iou_gate_pct"), "slicer_features": s.get("features"),
                          "slicer_status": s.get("status")}), flush=True)


if __name__ == "__main__":
    main()
