#!/usr/bin/env python3
"""cell_recognize.py — feature recognition by CELL DECOMPOSITION (prototype).

step_recognize looks for a build direction, slices the part into cross-sections along it and
traces their loops. That depends on the 2D loops being well behaved. This module never traces a
section of the part. It works on volumes:

  1. STOCK   the part's bounding box.
  2. CELLS   for each candidate axis, the surfaces of the part that a prism along that axis can
             have (planes normal or parallel to it, cylinders parallel to it), extended to the
             whole box, split the box into cells. Every cell is a prism along the axis: it has a
             footprint and lies in one slab between two consecutive cap planes.
  3. LABEL   a cell is EMPTY when none of it is inside the part: interior points of the cell and
             a cloud of points sampled through the box, all classified against the part, agree.
             (A cell that a feature on another axis passes through is mixed, and is left alone.)
  4. MERGE   empty cells whose footprints stay empty over a range of consecutive slabs, and that
             touch, merge into one candidate feature: a profile cut over that range. Candidates
             are maximal (the range cannot grow without the footprint shrinking).
  5. COVER   the candidates of all axes compete: greedily pick the one that removes the most
             not-yet-removed empty space (counted on the point cloud) until nothing is gained.
             Cuts may overlap. Empty space no candidate reaches is reported.
  6. EMIT    stock pad + one prism_cut per chosen candidate, as a featuretree IR.

The result is a "stock minus cuts" tree — how a machinist would describe the part, not
necessarily how its designer built it (a boss is what is left after cutting around it).
The rebuilt IR is compared with the input by volume and a Boolean-free IoU; nothing is called
verified without that.

Scope of the prototype: planes and cylinders only. A part with cones, tori or freeform faces is
reported as unsupported surfaces and its result is whatever the remaining surfaces explain.

    python3 cell_recognize.py part.step [--emit out.ir.json] [--max-cells N]
    from cell_recognize import recognize;  spec, report = recognize("part.step")
"""
import json
import math
import sys
import time
from pathlib import Path

from build123d import Face, GeomType, Plane, Vector, import_step

import numpy as np

import ir as IR

TOL = 1e-4          # mm: two levels / offsets / radii are the same
ANG = 1e-6          # 1 - |cos|: two directions are parallel
MAX_CELLS = 20000      # per axis
MAX_AXES = 6
N_CLOUD = 30000


def _canon(v):
    """A direction with its dominant component positive, rounded — one key per line direction."""
    t = [0.0 if abs(c) < 1e-9 else c for c in v]
    i = max(range(3), key=lambda k: abs(t[k]))
    s = 1.0 if t[i] >= 0 else -1.0
    return tuple(round(s * c, 6) for c in t)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _frame(d):
    """Orthonormal (x, y, d) with y = d × x — the prism_cut / build123d Plane convention."""
    seed = min(((1, 0, 0), (0, 1, 0), (0, 0, 1)), key=lambda e: abs(_dot(e, d)))
    k = _dot(seed, d)
    x = [seed[i] - k * d[i] for i in range(3)]
    n = math.sqrt(_dot(x, x))
    x = tuple(c / n for c in x)
    y = (d[1] * x[2] - d[2] * x[1], d[2] * x[0] - d[0] * x[2], d[0] * x[1] - d[1] * x[0])
    return x, y


def _surfaces(solid, bb):
    """Distinct planes and cylinders of the part: ({(normal, offset)}, {(axis, point, radius)}),
    with planes lying on the bounding box dropped. Also the count of faces of any other type."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    planes, cyls, other = {}, {}, 0
    lo, hi = (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)
    for f in solid.faces():
        a = BRepAdaptor_Surface(f.wrapped)
        if f.geom_type == GeomType.PLANE:
            ax = a.Plane().Axis()
            n = _canon((ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()))
            p = ax.Location()
            off = round(_dot(n, (p.X(), p.Y(), p.Z())), 5)
            on_box = any(abs(abs(n[i]) - 1) < ANG and (abs(off - lo[i]) < TOL or abs(off - hi[i]) < TOL)
                         for i in range(3))
            if not on_box:
                planes[(n, off)] = True
        elif f.geom_type == GeomType.CYLINDER:
            c = a.Cylinder()
            ax = c.Axis()
            d = _canon((ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()))
            p = (ax.Location().X(), ax.Location().Y(), ax.Location().Z())
            k = _dot(p, d)
            foot = tuple(round(p[i] - k * d[i], 4) for i in range(3))      # axis point nearest origin
            cyls[(d, foot, round(c.Radius(), 5))] = True
        else:
            other += 1
    return list(planes), list(cyls), other


def _split(bb, planes, cyls):
    """The bounding box split by every extended surface -> (compound of cells, list of cell solids)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Ax3, gp_Cylinder, gp_Dir, gp_Pln, gp_Pnt
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_ListOfShape

    L = 4 * math.dist((bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)) + 10
    box = BRepPrimAPI_MakeBox(gp_Pnt(bb.min.X, bb.min.Y, bb.min.Z), gp_Pnt(bb.max.X, bb.max.Y, bb.max.Z)).Shape()
    args, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
    args.Append(box)
    for n, off in planes:
        pln = gp_Pln(gp_Pnt(n[0] * off, n[1] * off, n[2] * off), gp_Dir(*n))
        tools.Append(BRepBuilderAPI_MakeFace(pln, -L, L, -L, L).Face())
    for d, foot, r in cyls:
        cyl = gp_Cylinder(gp_Ax3(gp_Pnt(*foot), gp_Dir(*d)), r)
        tools.Append(BRepBuilderAPI_MakeFace(cyl, 0.0, 2 * math.pi, -L, L).Face())
    sp = BRepAlgoAPI_Splitter()
    sp.SetArguments(args)
    sp.SetTools(tools)
    sp.SetRunParallel(True)
    sp.Build()
    if not sp.IsDone():
        raise RuntimeError("the kernel could not split the stock")
    shape = sp.Shape()
    cells = []
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        cells.append(TopoDS.Solid_s(ex.Current()))
        ex.Next()
    return shape, cells


def _interior_points(cell, want=3):
    """Up to `want` points strictly inside a cell, and its volume. More than one because a single
    point can sit on a line of symmetry of the part (a bore's axis), where the kernel's ray-casting
    classifier gave the wrong answer; the label is a majority vote."""
    from build123d import Solid
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(cell, g)
    c = g.CentreOfMass()
    c = (c.X(), c.Y(), c.Z())
    pts = []
    inside = BRepClass3d_SolidClassifier(cell)
    # points part-way from each face's centre towards the centroid, off any symmetry line
    for k, f in enumerate(sorted(Solid(cell).faces(), key=lambda f: -f.area)):
        p = f.center()
        for t in (0.37, 0.19, 0.61):
            q = (p.X + t * (c[0] - p.X) + 1e-3 * (k + 1), p.Y + t * (c[1] - p.Y) + 7e-4 * (k + 1),
                 p.Z + t * (c[2] - p.Z) + 3e-4 * (k + 1))
            inside.Perform(gp_Pnt(*q), 1e-7)
            if inside.State() == TopAbs_IN:
                pts.append(q)
                break
        if len(pts) >= want:
            break
    return (pts or [c]), g.Mass()


def _adjacency(shape, cells):
    """{cell index: set of cell indices sharing a face}."""
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape, TopTools_IndexedMapOfShape
    idx = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_SOLID, idx)
    order = {idx.FindIndex(c): i for i, c in enumerate(cells)}
    m = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_FACE, TopAbs_SOLID, m)
    adj = {i: set() for i in range(len(cells))}
    for k in range(1, m.Extent() + 1):
        owners = [order[idx.FindIndex(s)] for s in m.FindFromIndex(k)]
        if len(owners) == 2 and owners[0] != owners[1]:
            adj[owners[0]].add(owners[1])
            adj[owners[1]].add(owners[0])
    return adj


def _prism(cell, d):
    """If the cell is a prism along d: (lo, hi, footprint key, bottom cap faces); else None.
    A prism has only caps (planes normal to d) and walls (planes or cylinders parallel to d)."""
    from build123d import Solid
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    x, y = _frame(d)
    caps = {}
    for f in Solid(cell).faces():
        a = BRepAdaptor_Surface(f.wrapped)
        if f.geom_type == GeomType.PLANE:
            n = a.Plane().Axis().Direction()
            c = abs(_dot((n.X(), n.Y(), n.Z()), d))
            if c > 1 - ANG:
                p = f.center()
                caps.setdefault(round(_dot((p.X, p.Y, p.Z), d), 4), []).append(f)
            elif c > 1e-6:
                return None
        elif f.geom_type == GeomType.CYLINDER:
            n = a.Cylinder().Axis().Direction()
            if abs(_dot((n.X(), n.Y(), n.Z()), d)) < 1 - ANG:
                return None
        else:
            return None
    if len(caps) != 2:
        return None
    lo, hi = sorted(caps)
    area = sum(f.area for f in caps[lo])
    cx = sum(f.area * _dot(tuple(f.center()), x) for f in caps[lo]) / area
    cy = sum(f.area * _dot(tuple(f.center()), y) for f in caps[lo]) / area
    return lo, hi, (round(cx, 3), round(cy, 3), round(area, 3)), caps[lo]


def _candidates(d, cells_info, empty, adj):
    """Maximal empty prisms along d: [(volume, cells, lo, hi, bottom caps)]."""
    prisms = {}
    for i in empty:
        pr = cells_info[i]["prism"].get(d)
        if pr is not None:
            prisms[i] = pr
    if not prisms:
        return []
    levels = sorted({v for pr in prisms.values() for v in pr[:2]})
    lev = {v: k for k, v in enumerate(levels)}
    col = {}                                             # footprint -> {slab: cell}
    for i, (lo, hi, key, _) in prisms.items():
        if lev[hi] == lev[lo] + 1:
            col.setdefault(key, {})[lev[lo]] = i
    out = []
    n = len(levels) - 1
    for a in range(n):
        for b in range(a, n):
            F = [k for k, slabs in col.items() if all(s in slabs for s in range(a, b + 1))]
            if not F:
                continue
            cell_at = {col[k][a]: k for k in F}
            seen = set()
            for start in cell_at:
                if start in seen:
                    continue
                comp, todo = [], [start]
                seen.add(start)
                while todo:
                    c = todo.pop()
                    comp.append(cell_at[c])
                    for nb in adj[c]:
                        if nb in cell_at and nb not in seen:
                            seen.add(nb)
                            todo.append(nb)
                # maximal: the whole component cannot also be empty one slab lower or higher
                if a > 0 and all((a - 1) in col[k] for k in comp):
                    continue
                if b < n - 1 and all((b + 1) in col[k] for k in comp):
                    continue
                members = [col[k][s] for k in comp for s in range(a, b + 1)]
                caps = [f for k in comp for f in prisms[col[k][a]][3]]
                out.append((sum(cells_info[m]["vol"] for m in members), members, levels[a], levels[b + 1], caps))
    return out


def _profile(caps, d):
    """The union of the bottom caps as IR loops in the (x, y = d × x) frame, with its origin on
    the cap plane: [poly, ...] (outer loops and holes; the IR nests them)."""
    import step_recognize as R
    x, _ = _frame(d)
    pl = Plane(origin=(0, 0, 0), x_dir=x, z_dir=d)
    local = [pl.to_local_coords(f) for f in caps]
    shape = local[0] if len(local) == 1 else local[0].fuse(*local[1:]).clean()
    polys = []
    for f in (shape.faces() if hasattr(shape, "faces") else [shape]):
        for w in [f.outer_wire()] + list(f.inner_wires()):
            polys += R._split_pinched(R._approx_poly(w))
    return polys


def _footprint(caps, x, y):
    """The bottom caps of a cell as a shapely polygon in the (x, y) frame (arcs sampled finely)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    import step_recognize as R
    polys = []
    for f in caps:
        rings = []
        for w in [f.outer_wire()] + list(f.inner_wires()):
            pts = []
            for e, rev in R._ordered_edges(w):
                n = 1 if e.geom_type == GeomType.LINE else 72
                ts = [k / n for k in range(n)]
                for t in (ts if not rev else [1 - t for t in ts]):
                    q = e @ t
                    pts.append((q.X * x[0] + q.Y * x[1] + q.Z * x[2], q.X * y[0] + q.Y * y[1] + q.Z * y[2]))
            rings.append(pts)
        if len(rings[0]) >= 3:
            polys.append(Polygon(rings[0], [r for r in rings[1:] if len(r) >= 3]).buffer(0))
    return unary_union(polys) if polys else None


def _axis_cells(orig, bb, d, planes, cyls, cloud, cloud_in, max_cells):
    """Split the box by the surfaces a prism along d can have; label the cells; return the
    candidates of this axis as [(point indices, volume, lo, hi, caps)] plus counts."""
    import shapely
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN
    pl = [(n, o) for n, o in planes if abs(_dot(n, d)) > 1 - ANG or abs(_dot(n, d)) < 1e-6]
    cy = [(a, f, r) for a, f, r in cyls if abs(_dot(a, d)) > 1 - ANG]
    shape, cells = _split(bb, pl, cy)
    if len(cells) > max_cells:
        raise ValueError(f"{len(cells)} cells along {d} (limit {max_cells})")
    x, y = _frame(d)
    u, v, w = cloud @ np.array(x), cloud @ np.array(y), cloud @ np.array(d)
    adj = _adjacency(shape, cells)
    clf = BRepClass3d_SolidClassifier(orig.wrapped)
    masks, info, empty = {}, [], []
    for i, c in enumerate(cells):
        pr = _prism(c, d)
        rec = {"vol": 0.0, "prism": {d: pr}, "pts": np.empty(0, dtype=int)}
        info.append(rec)
        if pr is None:
            continue
        lo, hi, key, caps = pr
        if key not in masks:
            fp = _footprint(caps, x, y)
            if fp is None or fp.is_empty:
                masks[key] = np.zeros(len(cloud), dtype=bool)
            else:
                x0, y0, x1, y1 = fp.bounds
                m = (u >= x0) & (u <= x1) & (v >= y0) & (v <= y1)
                idx = np.nonzero(m)[0]
                m2 = np.zeros(len(cloud), dtype=bool)
                if len(idx):
                    m2[idx] = shapely.contains_xy(fp, u[idx], v[idx])
                masks[key] = m2
        rec["pts"] = np.nonzero(masks[key] & (w > lo) & (w < hi))[0]
        n_in = int(cloud_in[rec["pts"]].sum())
        if n_in > max(1, 0.02 * len(rec["pts"])):       # 1: a point on a sampled-arc boundary
            continue                                         # part of this cell is material
        pts, vol = _interior_points(c)
        rec["vol"] = vol
        votes = 0
        for q in pts:
            clf.Perform(gp_Pnt(*q), 1e-7)
            votes += clf.State() == TopAbs_IN
        if votes == 0:
            empty.append(i)
            rec["own"] = pts
    cands = _candidates(d, info, empty, adj)
    return cands, info, {"cells": len(cells), "empty": len(empty)}


def recognize(step_path, name=None, max_cells=MAX_CELLS, verify=True, samples=20000, n_cloud=N_CLOUD):
    from iou_check import _inside
    t0 = time.time()
    orig = import_step(str(step_path))
    orig = orig.solid() if hasattr(orig, "solid") and orig.solid() is not None else orig
    name = name or Path(step_path).stem
    bb = orig.bounding_box()
    planes, cyls, other = _surfaces(orig, bb)
    report = {"name": name, "method": "cells", "planes": len(planes), "cylinders": len(cyls),
              "unsupported_faces": other, "warnings": [], "per_axis": {}}
    if other:
        report["warnings"].append(f"{other} face(s) are not planes or cylinders and were not used to split")

    # candidate axes: directions that planes face or cylinders run along, most surfaces first
    score = {}
    for n, _ in planes:
        score[n] = score.get(n, 0) + 1
    for a, _, _ in cyls:
        score[a] = score.get(a, 0) + 1
    for e in ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)):
        score.setdefault(e, 0)
    axes = sorted(score, key=lambda a: (-score[a], a))[:MAX_AXES]
    if len(score) > len(axes):
        report["warnings"].append(f"{len(score) - len(axes)} further direction(s) not tried as cut axes")

    lo = np.array([bb.min.X, bb.min.Y, bb.min.Z])
    hi = np.array([bb.max.X, bb.max.Y, bb.max.Z])
    cloud = np.random.default_rng(1).uniform(lo, hi, size=(n_cloud, 3))
    cloud_in = _inside(orig, cloud)
    box_vol = float(np.prod(hi - lo))
    w_pt = box_vol / n_cloud

    # every candidate of every axis, with the cloud points it removes
    cands = []
    for d in axes:
        try:
            cs, info, counts = _axis_cells(orig, bb, d, planes, cyls, cloud, cloud_in, max_cells)
        except (ValueError, RuntimeError) as e:
            report["warnings"].append(f"axis {d}: {e}")
            continue
        report["per_axis"][str(d)] = {**counts, "candidates": len(cs)}
        for vol, members, a, b, caps in cs:
            pts = np.unique(np.concatenate([info[m]["pts"] for m in members])) if members else np.empty(0, int)
            own = [q for m in members for q in info[m].get("own", [])]
            cands.append({"d": d, "vol": vol, "lo": a, "hi": b, "caps": caps, "pts": pts, "own": own})
    report["candidates"] = len(cands)
    report["cells"] = sum(v["cells"] for v in report["per_axis"].values())

    # Cover. Empty space is measured on the cloud; each empty cell's own interior points are added
    # as extra, nearly weightless targets so that a cell too thin to catch a cloud point still
    # gets cut by something. Whether a candidate contains another axis's cell point is a geometric
    # test in that candidate's frame.
    extra = np.array([q for c in cands for q in c["own"]]) if cands else np.empty((0, 3))
    extra = np.unique(np.round(extra, 6), axis=0) if len(extra) else extra
    polys_cache = {}

    def extra_hits(k):
        if k not in polys_cache:
            import shapely
            c = cands[k]
            x, y = _frame(c["d"])
            fp = _footprint(c["caps"], x, y)
            if fp is None or not len(extra):
                polys_cache[k] = np.empty(0, int)
            else:
                ww = extra @ np.array(c["d"])
                m = (ww > c["lo"]) & (ww < c["hi"])
                idx = np.nonzero(m)[0]
                ok = shapely.contains_xy(fp, extra[idx] @ np.array(x), extra[idx] @ np.array(y)) if len(idx) else []
                polys_cache[k] = idx[np.array(ok, dtype=bool)] if len(idx) else idx
        return polys_cache[k]

    need = ~cloud_in
    need_extra = np.ones(len(extra), dtype=bool)
    eps = 1e-6 * w_pt
    chosen = []
    live = set(range(len(cands)))
    while live:
        best, gain = None, 0.0
        for k in live:
            g = w_pt * int(need[cands[k]["pts"]].sum())
            if g + eps * len(cands[k]["own"]) + 1e-12 <= gain:
                continue                                     # cannot beat the best even with its extras
            g += eps * int(need_extra[extra_hits(k)].sum())
            if g > gain:
                best, gain = k, g
        if best is None or gain <= 0:
            break
        chosen.append(best)
        live.discard(best)
        need[cands[best]["pts"]] = False
        need_extra[extra_hits(best)] = False
    left = int(need.sum())
    report["uncut_pct_of_part"] = round(100 * left * w_pt / orig.volume, 3)
    if report["uncut_pct_of_part"] > 0.05:                   # below that it is arc-sampling noise
        report["warnings"].append(f"{report['uncut_pct_of_part']}% of the part's volume in empty space that "
                                  "no candidate cut reaches (cones, freeform faces, oblique features)")

    # stock pad from z = 0; everything is shifted so the box's bottom is at z = 0
    zmin = bb.min.Z
    sx, sy, sz = (hi - lo).tolist()
    feats = [IR.sketch("stock_sk", "XY", rects=[(round(sx, 5), round(sy, 5),
                                                round((bb.min.X + bb.max.X) / 2, 5), round((bb.min.Y + bb.max.Y) / 2, 5))]),
             IR.pad("stock", "stock_sk", length=round(sz, 5))]
    chosen.sort(key=lambda k: -cands[k]["vol"])
    for n_cut, k in enumerate(chosen):
        c = cands[k]
        d = c["d"]
        try:
            polys = _profile(c["caps"], d)
        except Exception as e:                                             # noqa: BLE001
            report["warnings"].append(f"cut{n_cut}: profile failed ({type(e).__name__}: {e})"[:200])
            continue
        if not polys:
            report["warnings"].append(f"cut{n_cut}: empty profile")
            continue
        x, _ = _frame(d)
        o = (d[0] * c["lo"], d[1] * c["lo"], d[2] * c["lo"] - zmin)
        feats.append(IR.prism_cut(f"cut{n_cut}", origin=tuple(round(q, 5) for q in o), normal=d, xdir=x,
                                  depth=round(c["hi"] - c["lo"], 5), polys=polys))
    spec = IR.part(name, *feats)
    report.update(features=len(feats), cuts=len(feats) - 2, invalid=IR.validate(spec)[:5],
                  recognise_s=round(time.time() - t0, 1))
    if verify:
        import b3d_emit
        from build123d import Pos
        from iou_check import iou
        try:
            part, res = b3d_emit.emit(json.loads(json.dumps(spec)))
            p, ci = iou(orig, Pos(0, 0, zmin) * part, n=samples)
            dv = 100 * abs(res["volume"] - orig.volume) / orig.volume
            report.update(vol_orig=round(orig.volume, 1), vol_ir=round(res["volume"], 1), dvol_pct=round(dv, 3),
                          iou_pct=round(100 * p, 2), verified=bool(p >= 0.995 and dv <= 0.5))
        except Exception as e:                                             # noqa: BLE001
            report.update(verified=False, reason=f"re-emit failed: {type(e).__name__}: {e}"[:300])
    report["total_s"] = round(time.time() - t0, 1)
    return spec, report


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 0
    mc = int(a[a.index("--max-cells") + 1]) if "--max-cells" in a else MAX_CELLS
    spec, rep = recognize(a[0], max_cells=mc)
    print(json.dumps(rep, indent=1))
    for f in spec["features"][2:]:
        print(f"  {f['name']:8} along {tuple(f['normal'])} from {tuple(f['origin'])} depth {f['depth']}: "
              f"{len(f['polys'])} loop(s)")
    if "--emit" in a:
        Path(a[a.index("--emit") + 1]).write_text(json.dumps({"spec": spec, "report": rep}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
