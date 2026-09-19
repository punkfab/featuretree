#!/usr/bin/env python3
"""Rotation-aware reconstruction scoring: IoU + symmetric difference per part.

WHY THIS REPLACES THE NAIVE DECOMPOSITION. step_recognize works in the part's
own frame: it rotates the recognised axis onto Z. So the recovered solid is
generally ROTATED relative to the input, and a translation-only alignment
compares two different orientations and reports them as near-disjoint. An
earlier version of this analysis did exactly that and produced a spurious
"1036x cancellation" on ftc_09. Co-registration must undo the rotation first.

METHOD. Try the 24 axis-aligned orientations; keep only those whose bounding-box
EXTENTS match the original (cheap, no booleans). For each survivor, translate by
the bbox min corner and compute IoU via the union (inclusion-exclusion):

    |A n B| = |A| + |B| - |A u B|,   IoU = |A n B| / |A u B|

Direct OCCT difference/intersection is unreliable on these operands, so
everything is derived from the union. Report the best-IoU orientation.

WHY IoU. (1) It is the metric the CAD-program-inference literature reports
(CSGNet, InverseCSG, BSP-Net, CAPRI-Net), so it makes this work comparable.
(2) Unlike a scalar volume difference, it is two-sided: over-cut and uncut
material cannot cancel. It is therefore both the comparable metric AND the
sound acceptance criterion.

Usage (from the REPO ROOT):
    python3 paper/figures/iou_corpus.py [--corpus DIR] [--timeout SEC]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

DEFAULT_CORPUS = os.path.expanduser(
    "~/Downloads/NIST-PMI-STEP-Files/AP203 geometry only"
)
OUT_JSON = os.path.join("paper", "figures", "iou_results.json")

WORKER = r'''
import json, os, sys, time, itertools
sys.path.insert(0, os.getcwd())
path = sys.argv[1]
res = {"part": os.path.basename(path)}
t0 = time.time()
try:
    import b3d_emit, step_recognize as sr
    from build123d import Pos, Rot, import_step

    def one(o):
        s = o.solids() if hasattr(o, "solids") else []
        return s[0] if s else o

    spec, rep = sr.recognize(path)
    res.update(status="VERIFIED" if rep.get("verified") else "PARTIAL",
               dvol_pct=rep.get("dvol_pct"), features=len(spec.get("features", [])),
               axis=list(rep.get("extrude_axis") or []), method=rep.get("method"))

    orig = one(import_step(path))
    out = b3d_emit.emit(spec)
    rec0 = one(out[0] if isinstance(out, tuple) else out)
    A = orig.volume
    bo = orig.bounding_box()
    tgt = (round(bo.size.X, 3), round(bo.size.Y, 3), round(bo.size.Z, 3))

    # 24 axis-aligned orientations as (rx, ry, rz) multiples of 90 degrees.
    cands = []
    for rx, ry, rz in itertools.product((0, 90, 180, 270), repeat=3):
        r = Rot(rx, ry, rz) * rec0
        b = r.bounding_box()
        got = (round(b.size.X, 3), round(b.size.Y, 3), round(b.size.Z, 3))
        if all(abs(g - t) < 0.05 for g, t in zip(got, tgt)):
            cands.append((rx, ry, rz, r))

    res["n_orientations_matching_bbox"] = len(cands)
    best = None
    for rx, ry, rz, r in cands:
        br = r.bounding_box()
        r2 = Pos(bo.min.X - br.min.X, bo.min.Y - br.min.Y, bo.min.Z - br.min.Z) * r
        B = r2.volume
        u = orig + r2
        U = sum(s.volume for s in u.solids()) if u.solids() else u.volume
        inter = A + B - U
        iou = inter / U if U else 0.0
        if best is None or iou > best["iou"]:
            best = {"iou": iou, "rot": [rx, ry, rz], "vol_rec": B,
                    "union": U, "inter": inter,
                    "overcut": U - B, "uncut": U - A, "symdiff": (U - B) + (U - A)}
    if best:
        best["symdiff_pct"] = 100.0 * best["symdiff"] / A
        best["iou_pct"] = 100.0 * best["iou"]
        res["best"] = best
        res["vol_orig"] = A
except Exception as exc:
    res.update(status=res.get("status", "ERROR"),
               error=f"{type(exc).__name__}: {exc}"[:300])
res["seconds"] = round(time.time() - t0, 2)
print("@@JSON@@" + json.dumps(res))
'''


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=DEFAULT_CORPUS)
    ap.add_argument("--timeout", type=int, default=1800)
    args = ap.parse_args()

    files = sorted(os.path.join(args.corpus, f) for f in os.listdir(args.corpus)
                   if f.lower().endswith((".stp", ".step")))
    rows = []
    for f in files:
        try:
            p = subprocess.run([sys.executable, "-c", WORKER, f],
                               capture_output=True, text=True, timeout=args.timeout)
            row = next((json.loads(l[len("@@JSON@@"):])
                        for l in p.stdout.splitlines() if l.startswith("@@JSON@@")),
                       {"part": os.path.basename(f), "status": "ERROR",
                        "error": (p.stderr.strip().splitlines() or ["no output"])[-1][:200]})
        except subprocess.TimeoutExpired:
            row = {"part": os.path.basename(f), "status": "TIMEOUT"}
        rows.append(row)
        b = row.get("best") or {}
        print(f"  {row.get('status','?'):<9} {row['part']:<34} "
              f"dvol={str(row.get('dvol_pct','--')):>7}  "
              f"IoU={(f'{b[chr(105)+chr(111)+chr(117)+chr(95)+chr(112)+chr(99)+chr(116)]:.2f}%' if b.get('iou_pct') is not None else '--'):>9}  "
              f"symdiff={(f'{b[chr(115)+chr(121)+chr(109)+chr(100)+chr(105)+chr(102)+chr(102)+chr(95)+chr(112)+chr(99)+chr(116)]:.2f}%' if b.get('symdiff_pct') is not None else '--'):>9}  "
              f"rot={b.get('rot','--')!s:<16} nfit={row.get('n_orientations_matching_bbox','--')}")

    with open(OUT_JSON, "w") as fh:
        json.dump({"corpus": args.corpus, "results": rows}, fh, indent=2)
    print(f"\nwrote {OUT_JSON}")

    ver = [r for r in rows if r.get("status") == "VERIFIED" and (r.get("best") or {}).get("iou_pct") is not None]
    if ver:
        print("\nVERIFIED parts, by reconstruction IoU:")
        for r in sorted(ver, key=lambda r: -r["best"]["iou_pct"]):
            print(f"  {r['part']:<34} dvol={r['dvol_pct']}%  IoU={r['best']['iou_pct']:.3f}%"
                  f"  symdiff={r['best']['symdiff_pct']:.3f}%")
        worst = min(ver, key=lambda r: r["best"]["iou_pct"])
        if worst["best"]["iou_pct"] < 99.0:
            print(f"\n  !! FALSE ACCEPT: {worst['part']} passed volume verification "
                  f"(dvol={worst['dvol_pct']}%) at IoU={worst['best']['iou_pct']:.2f}%")


if __name__ == "__main__":
    main()
