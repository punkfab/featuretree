#!/usr/bin/env python3
"""Boolean-FREE cross-check of the IoU figures, by Monte-Carlo point classification.

WHY THIS EXISTS. iou_corpus.py derives IoU from an OpenCASCADE union by
inclusion-exclusion. OCCT unions on these operands are unreliable, and a sanity
gate (U >= max(A, B), IoU in [0,1]) only catches degenerate results that are
IMPLAUSIBLE. It cannot catch a degenerate union that is wrong but plausible, and
that happened: FTC-10 was published at IoU 74.35% for a registration whose
bounding boxes overlap too little to allow more than ~27%.

The measurement itself lives in the library module iou_check.py (tested in
tests/test_iou_check.py); this script only runs it over the corpus. It uses only
point-in-solid classification (BRepClass3d_SolidClassifier): no Booleans anywhere. Points are drawn uniformly in the union of the two
bounding boxes; IoU = #(in A and in B) / #(in A or in B), and the box volume
cancels. The estimate carries a binomial confidence interval.

For each part it reports:
  * MC IoU at the rotation iou_corpus.py chose  -> does the published number hold?
  * the best MC IoU over all 24 orientations    -> what the right lower bound is

Same registration family as iou_corpus.py (24 axis-aligned rotations,
bounding-box-min-corner alignment), so the two are directly comparable.

Usage (from the REPO ROOT, after iou_corpus.py):
    python3 paper/figures/iou_mc_check.py [--coarse 4000] [--fine 60000]
Writes: paper/figures/iou_mc_results.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

CORPUS = os.path.expanduser("~/Downloads/NIST-PMI-STEP-Files/AP203 geometry only")
IOU_IN = os.path.join("paper", "figures", "iou_results.json")
OUT = os.path.join("paper", "figures", "iou_mc_results.json")

WORKER = r'''
import json, os, sys
sys.path.insert(0, os.getcwd())
import b3d_emit, iou_check, step_recognize as sr
from build123d import import_step

path, harness_rot, n_coarse, n_fine = sys.argv[1], json.loads(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])

res = {"part": os.path.basename(path)}
spec, rep = sr.recognize(path)
res["status"] = "VERIFIED" if rep.get("verified") else "PARTIAL"
out = b3d_emit.emit(spec)
rec = out[0] if isinstance(out, tuple) else out
orig = import_step(path)

if harness_rot is not None and False:   # the Boolean harness comparison is archived (README)
    p, ci = iou_check.iou(orig, iou_check.register(rec, orig, harness_rot), n=n_fine, seed=1)
    res["at_harness_rot"] = {"rot": harness_rot, "iou_pct": 100 * p, "ci_pct": 100 * ci}
    print("@@PROG@@" + json.dumps(res), flush=True)

if rep.get("extrude_axis"):
    # EXACT registration: undo the recogniser's own transform (step_recognize.input_frame). The
    # IoU is then a measurement of the recovery, not a lower bound on it.
    place, _, _ = sr.input_frame(orig, rep)
    p, ci = iou_check.iou(orig, place(rec), n=n_fine, seed=2)
    res["best"] = {"registration": "exact", "iou_pct": 100 * p, "ci_pct": 100 * ci}
else:
    r = iou_check.registered_iou(orig, rec, n=n_fine, n_search=n_coarse, seed=2)
    res["best"] = {"registration": "search", "rot": r["rot"], "iou_pct": 100 * r["iou"],
                   "ci_pct": 100 * r["ci"]}
print("@@JSON@@" + json.dumps(res), flush=True)
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coarse", type=int, default=4000)
    ap.add_argument("--fine", type=int, default=60000)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--only", default="", help="comma-separated part-name substrings")
    args = ap.parse_args()

    harness = {r["part"]: r for r in json.load(open(IOU_IN))["results"]}
    names = sorted(harness)
    if args.only:
        names = [n for n in names if any(k in n for k in args.only.split(","))]

    def one_part(fn):
        hb = harness[fn].get("best") or {}
        try:
            p = subprocess.run([sys.executable, "-c", WORKER, os.path.join(CORPUS, fn),
                                json.dumps(hb.get("rot")), str(args.coarse), str(args.fine)],
                               capture_output=True, text=True, timeout=args.timeout)
            lines = p.stdout.splitlines()
            got = [l for l in lines if l.startswith("@@JSON@@")] or \
                  [l for l in lines if l.startswith("@@PROG@@")]
            row = json.loads(got[-1][8:]) if got else {"part": fn, "error": "no output"}
        except subprocess.TimeoutExpired:
            row = {"part": fn, "error": "timeout"}
        row["boolean_iou_pct"] = hb.get("iou_pct")
        return row

    from concurrent.futures import ThreadPoolExecutor
    rows = []
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for row in ex.map(one_part, names):
            rows.append(row)
            fn = row["part"]

            bm = row.get("best") or {}
            f = lambda d: f"{d['iou_pct']:6.2f}±{d['ci_pct']:.2f}" if d.get("iou_pct") is not None else "   --   "
            print(f"  {fn[5:11]:<7} {row.get('status','?'):<9} IoU={f(bm)}  "
                  f"({bm.get('registration', 'n/a')} registration){'  ERROR ' + row['error'] if 'error' in row else ''}",
                  flush=True)

    if args.only and os.path.exists(OUT):
        keep = {r["part"]: r for r in json.load(open(OUT))["results"]}
        keep.update({r["part"]: r for r in rows})
        rows = [keep[k] for k in sorted(keep)]
    json.dump({"results": rows}, open(OUT, "w"), indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
