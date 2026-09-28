#!/usr/bin/env python3
"""Boolean-FREE cross-check of the IoU figures, by Monte-Carlo point classification.

WHY THIS EXISTS. iou_corpus.py derives IoU from an OpenCASCADE union by
inclusion-exclusion. OCCT unions on these operands are unreliable, and a sanity
gate (U >= max(A, B), IoU in [0,1]) only catches degenerate results that are
IMPLAUSIBLE. It cannot catch a degenerate union that is wrong but plausible, and
that happened: FTC-10 was published at IoU 74.35% for a registration whose
bounding boxes overlap too little to allow more than ~27%.

This script uses only point-in-solid classification (BRepClass3d_SolidClassifier):
no booleans anywhere. Points are drawn uniformly in the union of the two
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
import itertools, json, math, os, sys
import numpy as np
sys.path.insert(0, os.getcwd())
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_IN
import b3d_emit, step_recognize as sr
from build123d import Compound, Pos, Rot, import_step

path, harness_rot, n_coarse, n_fine = sys.argv[1], json.loads(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])

def whole(o):
    s = o.solids() if hasattr(o, "solids") else []
    return (s[0] if len(s) == 1 else Compound(list(s))) if s else o

def inside(shape, pts):
    clfs = [BRepClass3d_SolidClassifier(s.wrapped) for s in shape.solids()]
    out = np.zeros(len(pts), dtype=bool)
    for i, (x, y, z) in enumerate(pts):
        p = gp_Pnt(float(x), float(y), float(z))
        for c in clfs:
            c.Perform(p, 1e-6)
            if c.State() == TopAbs_IN:
                out[i] = True
                break
    return out

def register(rec, orig, rot):
    r = Rot(*rot) * rec
    bo, br = orig.bounding_box(), r.bounding_box()
    return Pos(bo.min.X - br.min.X, bo.min.Y - br.min.Y, bo.min.Z - br.min.Z) * r

def mc_iou(orig, reg, n, seed):
    bo, br = orig.bounding_box(), reg.bounding_box()
    lo = np.minimum([bo.min.X, bo.min.Y, bo.min.Z], [br.min.X, br.min.Y, br.min.Z])
    hi = np.maximum([bo.max.X, bo.max.Y, bo.max.Z], [br.max.X, br.max.Y, br.max.Z])
    pts = np.random.default_rng(seed).uniform(lo, hi, size=(n, 3))
    a, b = inside(orig, pts), inside(reg, pts)
    u, i = int((a | b).sum()), int((a & b).sum())
    if u == 0:
        return 0.0, 0.0
    p = i / u
    return p, 1.96 * math.sqrt(max(p * (1 - p), 1e-12) / u)   # 95% binomial half-width

res = {"part": os.path.basename(path)}
spec, rep = sr.recognize(path)
res["status"] = "VERIFIED" if rep.get("verified") else "PARTIAL"
out = b3d_emit.emit(spec)
rec = whole(out[0] if isinstance(out, tuple) else out)
orig = whole(import_step(path))

if harness_rot is not None:
    p, ci = mc_iou(orig, register(rec, orig, harness_rot), n_fine, 1)
    res["at_harness_rot"] = {"rot": harness_rot, "iou_pct": 100 * p, "ci_pct": 100 * ci}
    print("@@PROG@@" + json.dumps(res), flush=True)

best = None
for rot in itertools.product((0, 90, 180, 270), repeat=3):
    p, _ = mc_iou(orig, register(rec, orig, rot), n_coarse, 2)
    if best is None or p > best[1]:
        best = (list(rot), p)
p, ci = mc_iou(orig, register(rec, orig, best[0]), n_fine, 3)
res["best"] = {"rot": best[0], "iou_pct": 100 * p, "ci_pct": 100 * ci}
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

            ah, bm = row.get("at_harness_rot") or {}, row.get("best") or {}
            bo = row["boolean_iou_pct"]
            agree = (bo is not None and ah.get("iou_pct") is not None
                     and abs(bo - ah["iou_pct"]) <= max(3 * ah["ci_pct"], 0.5))
            row["boolean_agrees"] = agree
            f = lambda d: f"{d['iou_pct']:6.2f}±{d['ci_pct']:.2f}" if d.get("iou_pct") is not None else "   --   "
            print(f"  {fn[5:11]:<7} {row.get('status','?'):<9} boolean={bo if bo is None else round(bo,2)!s:>7}  "
                  f"MC@same-rot={f(ah)}  MC-best={f(bm)} rot={bm.get('rot')}  "
                  f"{'OK' if agree else '** DISAGREES **'}", flush=True)

    json.dump({"results": rows}, open(OUT, "w"), indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
