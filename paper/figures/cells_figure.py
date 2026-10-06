#!/usr/bin/env python3
"""cells_figure.py — picture of the cell decomposition of the test flange (tests/test_cell_recognize.py).

Four slabs of the split along Z, seen from above: every cell's footprint, filled where the cell is
material and left pale where it is empty. Writes paper/figures/cells_flange.png.

    python3 paper/figures/cells_figure.py
"""
import sys
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from build123d import export_step, import_step
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_IN

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
import cell_recognize as C  # noqa: E402
from test_cell_recognize import flange  # noqa: E402

D = (0.0, 0.0, 1.0)
SOLID, EMPTY, EDGE = "#2f6f73", "#eef1f2", "#8a9499"


def main():
    with tempfile.TemporaryDirectory() as td:
        export_step(flange(), td + "/f.step")
        orig = import_step(td + "/f.step").solid()
    bb = orig.bounding_box()
    planes, cyls, _ = C._surfaces(orig, bb)
    _, cells = C._split(bb, planes, [c for c in cyls if abs(C._dot(c[0], D)) > 0.999])
    x, y = C._frame(D)
    clf = BRepClass3d_SolidClassifier(orig.wrapped)
    slabs = {}
    for c in cells:
        pr = C._prism(c, D)
        if pr is None:
            continue
        lo, hi, _, caps = pr
        pts, _ = C._interior_points(c)
        votes = 0
        for q in pts:
            clf.Perform(gp_Pnt(*q), 1e-7)
            votes += clf.State() == TopAbs_IN
        slabs.setdefault((lo, hi), []).append((C._footprint(caps, x, y), 2 * votes > len(pts)))
    show = [k for k in sorted(slabs) if k[0] in (0.0, 5.0, 7.0, 9.0)]
    fig, axes = plt.subplots(1, len(show), figsize=(12, 4.0), dpi=200)
    for ax, k in zip(axes, show):
        for fp, solid in slabs[k]:
            for g in getattr(fp, "geoms", [fp]):
                xs, ys = g.exterior.xy
                ax.fill(xs, ys, facecolor=SOLID if solid else EMPTY, edgecolor=EDGE, linewidth=0.5)
                for h in g.interiors:
                    hx, hy = h.xy
                    ax.fill(hx, hy, facecolor="white", edgecolor=EDGE, linewidth=0.5)
        n_e = sum(1 for _, s in slabs[k] if not s)
        ax.set_title(f"z = {k[0]:g} to {k[1]:g} mm\n{len(slabs[k])} cells, {n_e} empty", fontsize=9)
        ax.set_aspect("equal")
        ax.axis("off")
    fig.suptitle(f"The stock split into {len(cells)} cells by the part's own planes and cylinders "
                 "(material filled, empty pale)", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out = Path(__file__).with_name("cells_flange.png")
    fig.savefig(out, facecolor="white")
    print(out)


if __name__ == "__main__":
    main()
