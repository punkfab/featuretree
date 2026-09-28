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

CAVEAT on the fallback path. When the prefilter matches nothing (every PARTIAL, whose bbox is wrong
by construction) we score all 24 orientations under the SAME bbox-min-corner alignment. That is one
particular registration, not an optimal one, so the IoU reported for a PARTIAL is a LOWER BOUND:
the true best-aligned overlap can only be higher. It is still the right number for the paper, since
it cannot flatter the recogniser.

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

    # A PARTIAL reconstruction has the WRONG bounding box by construction (material is missing or
    # over-cut), so the cheap extent prefilter rejects all 24 orientations and leaves the part with
    # no IoU at all -- which is exactly the case we most want a number for. Fall back to scoring
    # every orientation. Costs 24 unions instead of ~8, and only on parts the prefilter emptied.
    res["prefilter_empty"] = not cands
    if not cands:
        cands = [(rx, ry, rz, Rot(rx, ry, rz) * rec0)
                 for rx, ry, rz in itertools.product((0, 90, 180, 270), repeat=3)]
    # OCCT will occasionally throw (or hard-crash) on a union for one particular orientation of a
    # malformed PARTIAL solid. Score each orientation independently so a single bad boolean costs
    # that orientation, not the whole part -- which is how FTC-06 and FTC-10 were lost previously.
    best = None
    n_failed = 0
    for rx, ry, rz, r in cands:
        try:
            br = r.bounding_box()
            r2 = Pos(bo.min.X - br.min.X, bo.min.Y - br.min.Y, bo.min.Z - br.min.Z) * r
            B = r2.volume
            u = orig + r2
            U = sum(s.volume for s in u.solids()) if u.solids() else u.volume
            # SANITY GATE on the boolean. A sound union contains BOTH operands, so U >= max(A, B)
            # and IoU lands in [0, 1]. OCCT sometimes returns a degenerate union whose volume is far
            # too small, which drives inter = A + B - U wildly positive -- FTC-10 scored an
            # impossible IoU of 501x this way. Treat any violation as a failed orientation, not data.
            if not U or B <= 0 or U < max(A, B) * (1 - 1e-6):
                n_failed += 1
                continue
            inter = A + B - U
            iou = inter / U
            if not (0.0 <= iou <= 1.0 + 1e-9):
                n_failed += 1
                continue
        except Exception:
            n_failed += 1
            continue
        if best is None or iou > best["iou"]:
            best = {"iou": iou, "rot": [rx, ry, rz], "vol_rec": B,
                    "union": U, "inter": inter,
                    "overcut": U - B, "uncut": U - A, "symdiff": (U - B) + (U - A)}
            # Checkpoint. A bad orientation can take OCCT down with a HARD crash, which no
            # try/except can catch, so stream the best-so-far: the parent falls back to the last
            # checkpoint and the part survives with a (still valid) lower bound.
            ck = dict(best); ck["symdiff_pct"] = 100.0*ck["symdiff"]/A; ck["iou_pct"] = 100.0*ck["iou"]
            print("@@BEST@@" + json.dumps({**res, "best": ck, "vol_orig": A,
                                           "checkpoint": True}), flush=True)
    res["n_orientations_failed"] = n_failed
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
            lines = p.stdout.splitlines()
            row = next((json.loads(l[len("@@JSON@@"):])
                        for l in lines if l.startswith("@@JSON@@")), None)
            if row is None:   # worker died mid-sweep -- keep the last checkpoint if there is one
                cks = [l for l in lines if l.startswith("@@BEST@@")]
                row = json.loads(cks[-1][len("@@BEST@@"):]) if cks else {
                    "part": os.path.basename(f), "status": "ERROR",
                    "error": (p.stderr.strip().splitlines() or ["no output"])[-1][:200]}
        except subprocess.TimeoutExpired:
            row = {"part": os.path.basename(f), "status": "TIMEOUT"}
        rows.append(row)
        b = row.get("best") or {}
        print(f"  {row.get('status','?'):<9} {row['part']:<34} "
              f"dvol={str(row.get('dvol_pct','--')):>7}  "
              f"IoU={(f'{b[chr(105)+chr(111)+chr(117)+chr(95)+chr(112)+chr(99)+chr(116)]:.2f}%' if b.get('iou_pct') is not None else '--'):>9}  "
              f"symdiff={(f'{b[chr(115)+chr(121)+chr(109)+chr(100)+chr(105)+chr(102)+chr(102)+chr(95)+chr(112)+chr(99)+chr(116)]:.2f}%' if b.get('symdiff_pct') is not None else '--'):>9}  "
              f"rot={b.get('rot','--')!s:<16} nfit={row.get('n_orientations_matching_bbox','--')}"
              f"{'  (lower bound)' if row.get('prefilter_empty') else ''}")

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
