#!/usr/bin/env python3
"""Tessellate the 11 NIST AP203 STEP files to watertight STL (run with cf_env python).

- STEP read with cadquery/OCP 7.7.2. Three files (ctc_02/04/05) carry one stray single-face open
  shell next to the closed main shell; only the largest closed shell is meshed (recorded per part).
- OCC BRepMesh_IncrementalMesh, ABSOLUTE linear deflection = REL * bbox diagonal (default 0.001),
  angular deflection 0.3 rad. Triangles are taken straight from the per-face triangulations (float64).
- The OCC mesh is combinatorially closed but has zero-area triangles at T-junctions. It is passed
  through manifold3d (Manifold(Mesh64) -> to_mesh64), which collapses them while keeping the mesh
  2-manifold. No remeshing/decimation otherwise.
- The result is verified watertight after the float32 binary-STL round trip, loaded the way CADFather
  loads it (trimesh.load(process=True)).
Writes cf_nist/stl/<part>.stl and cf_nist/stl/tessellation.json.
"""
import json, sys, time
from pathlib import Path
import numpy as np, trimesh, manifold3d
import cadquery as cq
from OCP.BRepTools import BRepTools
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
from OCP.TopAbs import TopAbs_REVERSED

SRC = Path("/Users/dannewcome/sandbox/punkfab/featuretree-bench/data/nist/NIST-PMI-STEP-Files/AP203 geometry only")
OUT = Path(__file__).resolve().parent / "stl"
OUT.mkdir(exist_ok=True)
REL = float(sys.argv[1]) if len(sys.argv) > 1 else 0.001
ANG = 0.3


def edge_counts(m):
    _, c = np.unique(m.edges_sorted, axis=0, return_counts=True)
    return int((c == 1).sum()), int((c > 2).sum())


def occ_mesh(shape, lin, ang):
    BRepTools.Clean_s(shape.wrapped)
    BRepMesh_IncrementalMesh(shape.wrapped, lin, False, ang, True)
    V, T, off = [], [], 0
    for f in shape.Faces():
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f.wrapped, loc)
        if tri is None:
            continue
        tr = loc.Transformation()
        k = tri.NbNodes()
        V.extend(tri.Node(i).Transformed(tr).Coord() for i in range(1, k + 1))
        rev = f.wrapped.Orientation() == TopAbs_REVERSED
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            T.append((a - 1 + off, c - 1 + off, b - 1 + off) if rev else (a - 1 + off, b - 1 + off, c - 1 + off))
        off += k
    m = trimesh.Trimesh(np.array(V, dtype=np.float64), np.array(T), process=False)
    m.merge_vertices()
    return m


info = {}
for stp in sorted(SRC.glob("*.stp")):
    name = "_".join(stp.stem.split("_")[:3])
    t = time.time()
    shape = cq.importers.importStep(str(stp)).val()
    shells = sorted(shape.Shells(), key=lambda s: -len(s.Faces()))
    dropped = [dict(faces=len(s.Faces()), area=float(s.Area()), closed=bool(s.wrapped.Closed())) for s in shells[1:]]
    solid = cq.Solid.makeSolid(shells[0]) if len(shells) > 1 else shape
    bb = solid.BoundingBox()
    diag = float(bb.DiagonalLength)
    lin = REL * diag
    raw = occ_mesh(solid, lin, ANG)
    raw_open, raw_nm = edge_counts(raw)
    raw_degenerate = int((~raw.nondegenerate_faces(height=1e-9)).sum())
    man = manifold3d.Manifold(manifold3d.Mesh64(vert_properties=np.asarray(raw.vertices, dtype=np.float64),
                                                tri_verts=np.asarray(raw.faces, dtype=np.uint64)))
    status = str(man.status())
    info[name] = dict(step=stp.name, n_shells_in_step=len(shells), dropped_shells=dropped,
                      bbox_size=[bb.xlen, bb.ylen, bb.zlen], bbox_diag=diag,
                      linear_deflection_abs=lin, linear_deflection_rel_diag=REL, angular_deflection_rad=ANG,
                      faces_raw=int(len(raw.faces)), raw_open_edges=raw_open, raw_nonmanifold_edges=raw_nm,
                      raw_degenerate_faces=raw_degenerate, manifold_status=status,
                      volume_brep=float(solid.Volume()))
    if "NoError" in status and not man.is_empty():
        mm = man.to_mesh64()
        clean = trimesh.Trimesh(np.asarray(mm.vert_properties)[:, :3], np.asarray(mm.tri_verts), process=False)
    else:
        clean = raw
    out = OUT / f"{name}.stl"
    clean.export(out)
    r = trimesh.load(out, process=True)
    o, nm = edge_counts(r)
    info[name].update(faces=int(len(r.faces)), open_edges=o, nonmanifold_edges=nm,
                      degenerate_faces=int((~r.nondegenerate_faces(height=1e-9)).sum()),
                      watertight=bool(r.is_watertight), is_volume=bool(r.is_volume),
                      bodies=int(r.body_count), volume_mesh=float(r.volume),
                      volume_rel_err=float(abs(r.volume - solid.Volume()) / solid.Volume()),
                      sec=round(time.time() - t, 1))
    i = info[name]
    print(name, {k: i[k] for k in ("faces_raw", "raw_open_edges", "raw_nonmanifold_edges", "raw_degenerate_faces", "manifold_status", "faces", "open_edges", "nonmanifold_edges", "degenerate_faces", "watertight", "is_volume", "bodies", "volume_rel_err", "linear_deflection_abs", "n_shells_in_step")}, flush=True)
(OUT / "tessellation.json").write_text(json.dumps(info, indent=2))
