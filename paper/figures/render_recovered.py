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

    python3 paper/figures/render_recovered.py --all   # every evaluated part

Writes: paper/figures/recovered_parts.png  (or recovered_all.png with --all)
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


def draw(ax, tris, base, title, view, frame=None, fontsize=10.5):
    pc = Poly3DCollection(tris, facecolors=shade(tris, base), linewidths=0)
    ax.add_collection3d(pc)

    lo, hi = frame if frame is not None else (tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0))
    ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1]); ax.set_zlim(lo[2], hi[2])
    ax.set_box_aspect(np.maximum(hi - lo, 1e-6), zoom=1.05)
    ax.view_init(elev=view[0], azim=view[1])
    ax.set_axis_off()
    ax.set_title(title, fontsize=fontsize, pad=0, linespacing=1.35)


ALL_PARTS = [
    ("nist_ctc_01_asme1_rd.stp", "CTC-01", (28, -58)),
    ("nist_ctc_02_asme1_rc.stp", "CTC-02", (26, -58)),
    ("nist_ctc_03_asme1_rc.stp", "CTC-03", (26, -58)),
    ("nist_ctc_04_asme1_rd.stp", "CTC-04", (30, -58)),
    ("nist_ctc_05_asme1_rd.stp", "CTC-05", (28, -58)),
    ("nist_ftc_06_asme1_rd.stp", "FTC-06", (26, -58)),
    ("nist_ftc_07_asme1_rd.stp", "FTC-07", (24, 120)),
    ("nist_ftc_08_asme1_rc.stp", "FTC-08", (26, -58)),
    ("nist_ftc_09_asme1_rd.stp", "FTC-09", (30, -58)),
    ("nist_ftc_10_asme1_rb.stp", "FTC-10", (24, -62)),
    ("nist_ftc_11_asme1_rb.stp", "FTC-11", (26, -58)),
]


def prepare(fn, out_npz):
    """WORKER (runs in its own process): recover one part, register the recovery with the
    Boolean-free check's rotation, tessellate both, and save the meshes. OpenCASCADE can
    segfault on these parts (CTC-02 did, in-process), so each part is isolated exactly as
    the corpus harnesses isolate theirs."""
    import json
    import b3d_emit
    import step_recognize as sr
    from build123d import Compound, Pos, Rot, import_step

    def whole(o):
        """ALL solids. A multi-region recovery emits one solid per region; drawing
        solids()[0] would silently show half the reconstruction."""
        s_ = o.solids() if hasattr(o, "solids") else []
        return list(s_) if s_ else [o]

    path = os.path.join(CORPUS, fn)
    spec, rep = sr.recognize(path)
    out = b3d_emit.emit(spec)
    rec = whole(out[0] if isinstance(out, tuple) else out)
    orig = whole(import_step(path))

    r_ = {r["part"]: r for r in json.load(open(IOU))["results"]}.get(fn) or {}
    # "best" is absent if the 24-orientation search crashed; the fixed-rotation
    # measurement is then the only Boolean-free number, and it is still valid.
    best = r_.get("best") or r_.get("at_harness_rot") or {}
    rc = Rot(*best.get("rot", (0, 0, 0))) * Compound(rec)
    bo, br = Compound(orig).bounding_box(), rc.bounding_box()
    rc = Pos(bo.min.X - br.min.X, bo.min.Y - br.min.Y, bo.min.Z - br.min.Z) * rc
    np.savez_compressed(
        out_npz, orig=tri_mesh(orig), rec=tri_mesh(list(rc.solids())),
        meta=json.dumps({"verdict": "VERIFIED" if rep.get("verified") else "PARTIAL",
                         "dvol": rep.get("dvol_pct"), "nfeat": len(spec.get("features", [])),
                         "iou": best.get("iou_pct"), "ci": best.get("ci_pct")}))


def main():
    import argparse
    import json
    import subprocess
    import tempfile
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="every evaluated part, compact grid")
    ap.add_argument("--worker", nargs=2, metavar=("PART", "OUT_NPZ"), help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.worker:
        return prepare(*args.worker)

    parts = ALL_PARTS if args.all else PARTS
    out_path = OUT.replace("recovered_parts", "recovered_all") if args.all else OUT
    tmp = tempfile.mkdtemp(prefix="ft_render_")
    rows = []
    for fn, label, view in parts:
        npz = os.path.join(tmp, fn + ".npz")
        print(f"  {label}: recovering ...", flush=True)
        for attempt in (1, 2):           # an OCCT crash is occasionally non-deterministic
            p = subprocess.run([sys.executable, os.path.abspath(__file__), "--worker", fn, npz],
                               capture_output=True, text=True, timeout=1800)
            if os.path.exists(npz):
                break
            print(f"    worker exited {p.returncode} (attempt {attempt})", flush=True)
        if not os.path.exists(npz):
            sys.exit(f"could not render {label}")
        d = np.load(npz)
        m = json.loads(str(d["meta"]))
        rows.append((label, view, d["orig"], d["rec"], m["verdict"], m["dvol"], m["nfeat"],
                     m["iou"], m["ci"]))
        print(f"    {m['verdict']}  dvol={m['dvol']}%  features={m['nfeat']}", flush=True)

    per_row = 2 if args.all else 1                       # part-pairs per figure row
    nrows = -(-len(rows) // per_row)
    ncols = 2 * per_row
    fig = plt.figure(figsize=(4.5 * ncols, (3.0 if args.all else 3.3) * nrows))
    for i, (label, view, orig, rec, verdict, dvol, nfeat, iou_pct, iou_ci) in enumerate(rows):
        a1 = fig.add_subplot(nrows, ncols, 2 * i + 1, projection="3d")
        a2 = fig.add_subplot(nrows, ncols, 2 * i + 2, projection="3d")
        t = np.concatenate([orig.reshape(-1, 3), rec.reshape(-1, 3)])
        frame = (t.min(0), t.max(0))          # one box for both, so scale is honest
        # VERIFIED parts are effectively exact; a PARTIAL's IoU is a floor, so say so
        iou_txt = (f"IoU {iou_pct:.2f}±{iou_ci:.2f}%" if verdict == "VERIFIED"
                   else f"IoU ≥ {iou_pct:.0f}%") if iou_pct is not None else ""
        fs = 17 if args.all else 10.5     # the gallery is shown at ~1/4 size in a blog column
        draw(a1, orig, C_ORIG, f"{label}  ·  original" if args.all else f"{label}  ·  original STEP",
             view, frame, fs)
        if args.all:   # short labels: the gallery sits under the full table, which has the rest
            title = f"{label}  ·  {nfeat} features\n{verdict}  ·  {iou_txt}"
        else:
            title = f"{label}  ·  recovered, {nfeat} features\n{verdict}  ·  Δvol {dvol}%  ·  {iou_txt}"
        draw(a2, rec, C_REC, title, view, frame, fs)

    if args.all:
        fig.subplots_adjust(left=0.0, right=1.0, top=0.955, bottom=0.0, wspace=0.0, hspace=0.18)
    else:
        fig.subplots_adjust(left=0.0, right=1.0, top=0.965, bottom=0.0, wspace=0.0, hspace=0.12)
    fig.savefig(out_path, dpi=150 if args.all else 170, facecolor="white")
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
