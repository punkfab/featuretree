#!/usr/bin/env python3
"""mesh_check.py — is a rebuilt solid ONE closed body, the way a mesh consumer will see it?

Volume, extents and overlap can all pass on a solid that is still unusable downstream. Scoring
our NIST recoveries with another project's metric code (which, like a slicer or a mesher, starts
from a triangle mesh) turned up three such defects that none of our own checks reported:

  - CTC-02 and CTC-05 rebuild to solids the kernel calls valid, with the right volume, whose
    tessellation has open edges at every tolerance tried;
  - CTC-04 holds 30 enclosed voids that are not in the original;
  - CTC-03 comes back as five separate solids where the original is one.

`check(shape)` reports all three: how many solids, how many enclosed voids (inner shells), and
whether the tessellation is closed (every mesh edge shared by exactly two triangles).
`problems(rebuilt, original)` turns that into the list of ways the rebuild differs from its input.

    python mesh_check.py part.step
"""
import sys

import numpy as np

REL_DEFLECTION = 0.001      # linear deflection as a fraction of the bounding-box diagonal
ANG_DEFLECTION = 0.3        # radians


def tessellate(shape, rel=REL_DEFLECTION, ang=ANG_DEFLECTION):
    """(vertices, triangles) of `shape`, with vertices that coincide welded. Faces are meshed by
    OpenCASCADE one at a time; neighbours share an edge's nodes exactly when they share the edge,
    so welding on coordinates closes a sound solid and leaves a gap wherever the faces do not
    really meet."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from build123d.topology import downcast

    wrapped = shape.wrapped
    diag = shape.bounding_box().diagonal
    BRepTools.Clean_s(wrapped)                   # a stale coarser mesh would be reused otherwise
    BRepMesh_IncrementalMesh(wrapped, rel * diag, False, ang, True)
    verts, tris, off = [], [], 0
    ex = TopExp_Explorer(wrapped, TopAbs_FACE)
    while ex.More():
        face = downcast(ex.Current())
        ex.Next()
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            continue
        tr = loc.Transformation()
        n = tri.NbNodes()
        verts.extend(tri.Node(i).Transformed(tr).Coord() for i in range(1, n + 1))
        rev = face.Orientation() == TopAbs_REVERSED
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            tris.append((a - 1 + off, c - 1 + off, b - 1 + off) if rev else (a - 1 + off, b - 1 + off, c - 1 + off))
        off += n
    if not tris:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=int)
    v = np.asarray(verts, dtype=float)
    # weld at a billionth of the part's size: far below any real gap, above float noise
    _, first, inverse = np.unique(np.round(v / (1e-9 * max(diag, 1e-9))).astype(np.int64), axis=0,
                                  return_index=True, return_inverse=True)
    t = inverse.reshape(-1)[np.asarray(tris)]
    t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])]   # collapsed by the weld
    return v[first], t


def edge_counts(tris):
    """(open, non_manifold): mesh edges used by one triangle, and by more than two."""
    if len(tris) == 0:
        return 0, 0
    e = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
    _, n = np.unique(e, axis=0, return_counts=True)
    return int((n == 1).sum()), int((n > 2).sum())


def check(shape, rel=REL_DEFLECTION, ang=ANG_DEFLECTION):
    """{"solids", "voids", "triangles", "open_edges", "nonmanifold_edges", "closed"} for a shape.

    "voids" counts enclosed cavities: shells beyond one outer shell per solid. "closed" is the
    watertight test a mesh consumer applies: at least one triangle and no open or over-shared
    edge."""
    solids = list(shape.solids()) if hasattr(shape, "solids") else []
    shells = list(shape.shells()) if hasattr(shape, "shells") else []
    _, tris = tessellate(shape, rel, ang)
    n_open, n_nm = edge_counts(tris)
    return {"solids": len(solids), "voids": max(len(shells) - len(solids), 0), "triangles": int(len(tris)),
            "open_edges": n_open, "nonmanifold_edges": n_nm,
            "closed": bool(len(tris) and n_open == 0 and n_nm == 0)}


def problems(rebuilt, original=None):
    """Ways `rebuilt` (a check() result) fails as a body, as short strings; [] when it is sound.

    With `original` (the input's check() result) the solid and void counts are compared to it, so
    a part that really is two bodies, or really has a sealed cavity, is not blamed for it. An
    input whose own tessellation is not closed cannot hold the rebuild to that standard."""
    want_solids = original["solids"] if original else 1
    want_voids = original["voids"] if original else 0
    out = []
    if rebuilt["solids"] != want_solids:
        out.append(f"{rebuilt['solids']} separate solid(s) where the input has {want_solids}")
    if rebuilt["voids"] != want_voids:
        out.append(f"{rebuilt['voids']} enclosed void(s) where the input has {want_voids}")
    if not rebuilt["closed"] and (original is None or original["closed"]):
        out.append(f"tessellation is not closed: {rebuilt['open_edges']} open and "
                   f"{rebuilt['nonmanifold_edges']} over-shared edge(s)")
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 0
    from build123d import import_step
    import iou_check
    r = check(iou_check.solid_part(import_step(sys.argv[1])))
    print(f"{sys.argv[1]}: {r['solids']} solid(s), {r['voids']} void(s), {r['triangles']} triangles, "
          f"{r['open_edges']} open / {r['nonmanifold_edges']} over-shared edge(s) -> "
          f"{'closed' if r['closed'] else 'NOT closed'}")
    return 0 if r["closed"] else 1


if __name__ == "__main__":
    sys.exit(main())
