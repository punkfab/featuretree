#!/usr/bin/env python3
"""Render ORIGINAL STEP vs RECOVERED-IR solids side by side, for the blog/paper.

For each part: import the STEP, recover the tree with step_recognize, re-emit the
recovered IR through b3d_emit, and shade both solids from the same camera so the
comparison is honest -- same view, same scale, same tessellation tolerance.

The parts are chosen to tell the story rather than to flatter:
  CTC-01  the clean VERIFIED recovery
  FTC-10  a threaded part the old 40% axis gate rejected outright; now PARTIAL
  FTC-07  an open-sided enclosure, previously refused. The multi-region path
          recovers its two side walls as two pads and nothing else -- a valid but
          poor decomposition, which the verifier correctly labels PARTIAL. It is
          here BECAUSE it is a bad recovery: the picture shows what PARTIAL means.

CO-REGISTRATION. The recogniser works in the part's own frame (it rotates the
extrude axis onto Z), so a raw side-by-side compares different orientations. Each
recovery is therefore placed with the rotation + bbox-corner alignment chosen by
the BOOLEAN-FREE check (paper/figures/iou_mc_check.py), read from
iou_mc_results.json, and labelled with that check's IoU. The boolean harness's
own registration is not used: on PARTIAL parts its unions were shown to be
unreliable (FTC-10 was published at 74.35% for a rotation that scores 1.3%).

Run from the REPO ROOT:
    python3 paper/figures/iou_corpus.py      # writes iou_results.json
    python3 paper/figures/iou_mc_check.py    # writes iou_mc_results.json
    python3 paper/figures/render_recovered.py

Writes: paper/figures/recovered_parts.png
"""
from __future__ import annotations

import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

sys.path.insert(0, os.getcwd())

CORPUS = os.path.expanduser("~/Downloads/NIST-PMI-STEP-Files/AP203 geometry only")
OUT = os.path.join("paper", "figures", "recovered_parts.png")
IOU = os.path.join("paper", "figures", "iou_mc_results.json")

# part file, display label, the one-line "what this part is here to show"
# part file, label, camera (elev, azim) chosen so the input's structure is readable
PARTS = [
    ("nist_ctc_01_asme1_rd.stp", "CTC-01", (28, -58)),
    ("nist_ftc_10_asme1_rb.stp", "FTC-10", (24, -62)),
    ("nist_ftc_07_asme1_rd.stp", "FTC-07", (24, 120)),
]

C_ORIG = np.array([0.42, 0.45, 0.50])   # neutral grey -- the input
C_REC = np.array([0.16, 0.44, 0.59])    # teal -- the reconstruction
TOL = 0.35                              # linear tessellation tolerance (mm)


def tri_mesh(solids, tol=TOL):
    """list of build123d solids -> (Nx3x3) triangle vertex array."""
    out = []
    for solid in solids:
        verts, faces = solid.tessellate(tol)
        v = np.array([(p.X, p.Y, p.Z) for p in verts])
        out.append(v[np.array(faces)])
    return np.concatenate(out)


def shade(tris, base):
    """Lambertian shading from a fixed key light, so both panels light identically."""
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 0)
    light = np.array([0.45, -0.75, 0.50])
    light = light / np.linalg.norm(light)
    lam = np.abs(n @ light)
    f = 0.42 + 0.58 * lam                      # ambient floor + diffuse
    return np.clip(base[None, :] * f[:, None], 0, 1)


def draw(ax, solids, base, title, view, frame=None):
    tris = tri_mesh(solids)
    pc = Poly3DCollection(tris, facecolors=shade(tris, base), linewidths=0)
    ax.add_collection3d(pc)

    lo, hi = frame if frame is not None else (tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0))
    ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1]); ax.set_zlim(lo[2], hi[2])
    ax.set_box_aspect(np.maximum(hi - lo, 1e-6), zoom=1.05)
    ax.view_init(elev=view[0], azim=view[1])
    ax.set_axis_off()
    ax.set_title(title, fontsize=10.5, pad=0, linespacing=1.35)


def main():
    import json
    import b3d_emit
    import step_recognize as sr
    from build123d import Compound, Pos, Rot, import_step

    iou = {r["part"]: r for r in json.load(open(IOU))["results"]}

    def whole(o):
        """ALL solids. A multi-region recovery emits one solid per region; drawing
        solids()[0] would silently show half the reconstruction."""
        s = o.solids() if hasattr(o, "solids") else []
        return list(s) if s else [o]

    rows = []
    for fn, label, view in PARTS:
        path = os.path.join(CORPUS, fn)
        print(f"  {label}: recovering ...", flush=True)
        spec, rep = sr.recognize(path)
        out = b3d_emit.emit(spec)
        rec = whole(out[0] if isinstance(out, tuple) else out)
        orig = whole(import_step(path))

        # same registration as the IoU harness: rotate, then align bbox-min corners
        r_ = iou.get(fn) or {}
        # "best" is absent if the 24-orientation search crashed; the fixed-rotation
        # measurement is then the only boolean-free number, and it is still valid.
        best = r_.get("best") or r_.get("at_harness_rot") or {}
        rx, ry, rz = best.get("rot", (0, 0, 0))
        rc = Rot(rx, ry, rz) * Compound(rec)
        bo, br = Compound(orig).bounding_box(), rc.bounding_box()
        rc = Pos(bo.min.X - br.min.X, bo.min.Y - br.min.Y, bo.min.Z - br.min.Z) * rc
        rec = list(rc.solids())
        iou_pct = best.get("iou_pct")
        iou_ci = best.get("ci_pct")
        verdict = "VERIFIED" if rep.get("verified") else "PARTIAL"
        rows.append((label, view, orig, rec, verdict, rep.get("dvol_pct"),
                     len(spec.get("features", [])), iou_pct, iou_ci))
        print(f"    {verdict}  dvol={rep.get('dvol_pct')}%  "
              f"features={len(spec.get('features', []))}", flush=True)

    fig = plt.figure(figsize=(9.0, 3.3 * len(rows)))
    for i, (label, view, orig, rec, verdict, dvol, nfeat, iou_pct, iou_ci) in enumerate(rows):
        a1 = fig.add_subplot(len(rows), 2, 2 * i + 1, projection="3d")
        a2 = fig.add_subplot(len(rows), 2, 2 * i + 2, projection="3d")
        t = np.concatenate([tri_mesh(orig).reshape(-1, 3), tri_mesh(rec).reshape(-1, 3)])
        frame = (t.min(0), t.max(0))          # one box for both, so scale is honest
        # VERIFIED parts are effectively exact; a PARTIAL's IoU is a floor, so say so
        iou_txt = (f"IoU {iou_pct:.1f}±{iou_ci:.1f}%" if verdict == "VERIFIED"
                   else f"IoU ≥ {iou_pct:.0f}%") if iou_pct is not None else ""
        draw(a1, orig, C_ORIG, f"{label}  ·  original STEP", view, frame)
        draw(a2, rec, C_REC, f"{label}  ·  recovered, {nfeat} features\n"
                             f"{verdict}  ·  Δvol {dvol}%  ·  {iou_txt}", view, frame)

    fig.subplots_adjust(left=0.0, right=1.0, top=0.965, bottom=0.0,
                        wspace=0.0, hspace=0.12)
    fig.savefig(OUT, dpi=170, facecolor="white")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
