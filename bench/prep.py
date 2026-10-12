#!/usr/bin/env python3
"""Prepare benchmark inputs: one STEP per test part, scaled so its largest extent is 100 mm.

  deepcad   cad_json/<id>.json  -> solids rebuilt with DeepCAD's own cadlib semantics (ported from
            pythonocc to OCP; DeepCAD/cadlib/visualize.py), test ids from train_val_test_split.json
  fusion360 the dataset's own <id>.step (final design), test ids from train_test.json

Scaling: featuretree's tolerances are absolute millimetres, and these corpora are in arbitrary
units (DeepCAD is unitless, Fusion is cm). IoU is scale invariant.

    python prep.py deepcad|fusion360 [--jobs N]
"""
import argparse, json, os, sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
TARGET = 100.0


def _scale_write(shape, dst):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Trsf, gp_Pnt
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCP.Interface import Interface_Static
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepCheck import BRepCheck_Analyzer
    box = Bnd_Box(); BRepBndLib.AddOptimal_s(shape, box, False, False)
    if box.IsVoid():
        raise ValueError("void bbox")
    a, b = box.CornerMin(), box.CornerMax()
    x0, y0, z0, x1, y1, z1 = a.X(), a.Y(), a.Z(), b.X(), b.Y(), b.Z()
    ext = max(x1 - x0, y1 - y0, z1 - z0)
    if ext <= 0:
        raise ValueError("zero extent")
    t = gp_Trsf(); t.SetScale(gp_Pnt(x0, y0, z0), TARGET / ext)
    shape = BRepBuilderAPI_Transform(shape, t, True).Shape()
    n = 0
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        n += 1; ex.Next()
    if n == 0:
        raise ValueError("no solid")
    g = GProp_GProps(); BRepGProp.VolumeProperties_s(shape, g)
    if g.Mass() <= 1e-6:
        raise ValueError("zero volume")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    w = STEPControl_Writer(); w.Transfer(shape, STEPControl_AsIs)
    if w.Write(dst) != 1:
        raise ValueError("step write failed")
    return {"solids": n, "volume": g.Mass(), "valid": bool(BRepCheck_Analyzer(shape).IsValid())}


def _deepcad_one(a):
    did, src, dst = a
    if os.path.exists(dst):
        return did, {"cached": True}
    try:
        sys.path.insert(0, os.path.join(ROOT, "deepcad_src"))
        import numpy as np
        from copy import copy
        _cross = getattr(np, '_orig_cross', np.cross); np._orig_cross = _cross
        def cross2(a, b, *k, **kw):      # numpy 2 dropped 2D cross; cadlib relies on it
            a, b = np.asarray(a), np.asarray(b)
            if a.shape[-1] == 2 and b.shape[-1] == 2:
                return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]
            return _cross(a, b, *k, **kw)
        np.cross = cross2
        from cadlib.extrude import CADSequence
        from cadlib.macro import EXTRUDE_OPERATIONS, EXTENT_TYPE
        from cadlib.curves import Line, Circle, Arc
        from OCP.gp import gp_Pnt, gp_Dir, gp_Circ, gp_Pln, gp_Vec, gp_Ax3, gp_Ax2
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
        from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse, BRepAlgoAPI_Common
        from OCP.GC import GC_MakeArcOfCircle
        from OCP.TopoDS import TopoDS

        def l2g(p, pl):
            g = p[0] * pl.x_axis + p[1] * pl.y_axis + pl.origin
            return gp_Pnt(*[float(v) for v in g])

        def edge(c, pl):
            if isinstance(c, Line):
                if np.allclose(c.start_point, c.end_point):
                    return None
                return BRepBuilderAPI_MakeEdge(l2g(c.start_point, pl), l2g(c.end_point, pl)).Edge()
            if isinstance(c, Circle):
                ax = gp_Dir(*[float(v) for v in pl.normal])
                return BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(l2g(c.center, pl), ax), abs(float(c.radius)))).Edge()
            if isinstance(c, Arc):
                arc = GC_MakeArcOfCircle(l2g(c.start_point, pl), l2g(c.mid_point, pl), l2g(c.end_point, pl)).Value()
                return BRepBuilderAPI_MakeEdge(arc).Edge()
            raise NotImplementedError(type(c))

        def loop(lp, pl):
            w = BRepBuilderAPI_MakeWire()
            for c in lp.children:
                e = edge(c, pl)
                if e is not None:
                    w.Add(e)
            return w.Wire()

        def face(profile, pl):
            f3 = gp_Pln(gp_Ax3(gp_Pnt(*[float(v) for v in pl.origin]), gp_Dir(*[float(v) for v in pl.normal]),
                               gp_Dir(*[float(v) for v in pl.x_axis])))
            loops = [loop(l, pl) for l in profile.children]
            mf = BRepBuilderAPI_MakeFace(f3, loops[0])
            for l in loops[1:]:
                mf.Add((TopoDS.Wire_s if hasattr(TopoDS, 'Wire_s') else TopoDS.Wire)(l.Reversed()))
            return mf.Face()

        def by_extrude(op):
            profile = copy(op.profile); profile.denormalize(op.sketch_size)
            pl = copy(op.sketch_plane); pl.origin = op.sketch_pos
            f = face(profile, pl)
            nrm = gp_Dir(*[float(v) for v in op.sketch_plane.normal])
            v = gp_Vec(nrm).Multiplied(float(op.extent_one))
            body = BRepPrimAPI_MakePrism(f, v).Shape()
            if op.extent_type == EXTENT_TYPE.index("SymmetricFeatureExtentType"):
                body = BRepAlgoAPI_Fuse(body, BRepPrimAPI_MakePrism(f, v.Reversed()).Shape()).Shape()
            if op.extent_type == EXTENT_TYPE.index("TwoSidesFeatureExtentType"):
                v2 = gp_Vec(nrm.Reversed()).Multiplied(float(op.extent_two))
                body = BRepAlgoAPI_Fuse(body, BRepPrimAPI_MakePrism(f, v2).Shape()).Shape()
            return body

        seq = CADSequence.from_dict(json.load(open(src)))
        seq.normalize()
        body = by_extrude(seq.seq[0])
        for op in seq.seq[1:]:
            nb = by_extrude(op)
            if op.operation in (EXTRUDE_OPERATIONS.index("NewBodyFeatureOperation"),
                                EXTRUDE_OPERATIONS.index("JoinFeatureOperation")):
                body = BRepAlgoAPI_Fuse(body, nb).Shape()
            elif op.operation == EXTRUDE_OPERATIONS.index("CutFeatureOperation"):
                body = BRepAlgoAPI_Cut(body, nb).Shape()
            elif op.operation == EXTRUDE_OPERATIONS.index("IntersectFeatureOperation"):
                body = BRepAlgoAPI_Common(body, nb).Shape()
        info = _scale_write(body, dst)
        info["gt_ops"] = len(seq.seq)
        return did, info
    except Exception as e:
        return did, {"error": f"{type(e).__name__}: {e}"[:200]}


def _fusion_one(a):
    did, src, dst = a
    if os.path.exists(dst):
        return did, {"cached": True}
    try:
        from OCP.STEPControl import STEPControl_Reader
        r = STEPControl_Reader()
        if r.ReadFile(src) != 1:
            raise ValueError("step read failed")
        r.TransferRoots()
        return did, _scale_write(r.OneShape(), dst)
    except Exception as e:
        return did, {"error": f"{type(e).__name__}: {e}"[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", choices=["deepcad", "fusion360"])
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    out = os.path.join(ROOT, "data", a.dataset, "norm"); os.makedirs(out, exist_ok=True)
    if a.dataset == "deepcad":
        ids = json.load(open(os.path.join(ROOT, "data/deepcad/train_val_test_split.json")))["test"]
        jobs = [(i, os.path.join(ROOT, "data/deepcad/cad_json", i + ".json"),
                 os.path.join(out, i.split("/")[-1] + ".step")) for i in ids]
        fn = _deepcad_one
    else:
        ids = json.load(open(os.path.join(ROOT, "data/fusion360/train_test.json")))["test"]
        jobs = [(i, os.path.join(ROOT, "data/fusion360/step", i + ".step"), os.path.join(out, i + ".step")) for i in ids]
        fn = _fusion_one
    if a.limit:
        jobs = jobs[:a.limit]
    meta_p = os.path.join(ROOT, "data", a.dataset, "prep.json")
    meta = json.load(open(meta_p)) if os.path.exists(meta_p) else {}
    with ProcessPoolExecutor(a.jobs) as ex:
        for k, (did, info) in enumerate(ex.map(fn, jobs, chunksize=8)):
            if not info.get("cached"):
                meta[did] = info
            if k % 500 == 0:
                print(k, flush=True)
    json.dump(meta, open(meta_p, "w"))
    bad = {k: v for k, v in meta.items() if "error" in v}
    print(f"{a.dataset}: {len(jobs)} ids, {len(jobs) - len(bad)} written, {len(bad)} failed")
    from collections import Counter
    print(Counter(v["error"].split(":")[0] for v in bad.values()).most_common(8))


if __name__ == "__main__":
    main()
