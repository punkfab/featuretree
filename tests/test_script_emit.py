"""Tests for the Fusion / SolidWorks script backends.

Neither program runs here, so these check everything short of the vendor API calls:
  * the generated scripts are valid Python carrying the IR and the per-feature reference volumes;
  * the shared geometry the scripts draw from (targets/_geom.py: loops, arc mid-points, nesting,
    sketch frames, the polar-pocket placement) is REPLAYED with build123d, independently of
    b3d_emit's own sketch code, and must reproduce b3d_emit's volume after every feature.
What stays unverified until a real Fusion / SolidWorks run: API signatures, extrude direction and
taper sign conventions, profile selection. cad_verify.py checks those from the exported STEP.
"""
import json
import math
import sys
from pathlib import Path

import pytest
from build123d import (Axis, Edge, Face, Plane, Vector, Wire, extrude, revolve)

import b3d_emit
import ir as IR
import script_emit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "targets"))
import _geom as G  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


# -- a build123d "target" driven only by _geom, mirroring the runtimes' control flow ----------

def _face(fr, loop):
    segs = loop["segments"]
    if segs[0][0] == "circle":
        _, c, r = segs[0]
        pl = Plane(origin=G.to_world(fr, *c), x_dir=fr[1], z_dir=fr[3])
        return Face(Wire([Edge.make_circle(r, pl)]))
    edges = []
    for s in segs:
        pts = [Vector(*G.to_world(fr, *p)) for p in s[1:]]
        edges.append(Edge.make_line(*pts) if s[0] == "line" else Edge.make_three_point_arc(*pts))
    return Face(Wire(edges))


def _region(fr, loops):
    """Union of material loops minus holes, taking loops outermost-first (the nesting rule)."""
    faces = sorted(((_face(fr, lp), lp["include"]) for lp in loops), key=lambda t: -t[0].area)
    reg = None
    for f, inc in faces:
        reg = f if reg is None else (reg + f if inc else reg - f)
    return reg


def replay(spec):
    part, sk, vols = None, {}, []
    for f in spec["features"]:
        k = f["kind"]
        if k == "sketch":
            on = f.get("on")
            if on:
                bb = part.bounding_box()
                z0 = bb.max.Z if on.get("side", "top") == "top" else bb.min.Z
                fr, side = G.offset_xy(z0), on.get("side", "top")
            else:
                z0, side = 0.0, None
                fr = G.XZ if f.get("plane") == "XZ" else G.XY
            loops = G.sketch_loops(f.get("circles", []), f.get("rects", []), f.get("polys", []))
            sk[f["name"]] = (fr, loops, z0, side)
        elif k in ("pad", "pocket"):
            fr, loops, z0, side = sk[f["sketch"]]
            reg = _region(fr, loops)
            if k == "pad":
                d = (0, 0, -1) if side == "bottom" else (0, 0, 1)
                s = (extrude(reg, amount=f["length"] / 2, both=True) if f.get("symmetric")
                     else extrude(reg, amount=f["length"], dir=d, taper=f.get("taper", 0.0)))
                part = s if part is None else part + s
            elif f["through"]:
                part = part - extrude(reg, amount=1e4, both=True)
            else:
                d = (0, 0, -1) if z0 >= part.bounding_box().max.Z - 1e-6 else (0, 0, 1)
                part = part - extrude(reg, amount=f["length"], dir=d, taper=f.get("taper", 0.0))
        elif k == "revolve":
            fr, loops, _, _ = sk[f["sketch"]]
            s = revolve(_region(fr, loops), Axis.Z, revolution_arc=f.get("angle", 360.0))
            part = s if part is None else part + s
        elif k in ("prism_cut", "polar_pocket"):
            cuts = G.polar_cuts(f) if k == "polar_pocket" else [
                (G.frame(f["origin"], f["normal"], f["xdir"]), G.sketch_loops(polys=f["polys"]), f["depth"])]
            for fr, loops, depth in cuts:
                part = part - extrude(_region(fr, loops), amount=depth, dir=fr[3], taper=f.get("taper", 0.0))
        else:
            raise AssertionError(f"replay does not cover {k}")
        vols.append(None if part is None else part.volume)
    return vols


def _close(a, b):
    return (a is None and b is None) or abs(a - b) <= max(1e-3, 1e-4 * abs(b))


def every_kind():
    """One IR touching every path: arcs, a hole with an island, a face-attached blind pocket, an XZ
    revolve, a cross-axis prism_cut with arcs, and a polar pocket ring."""
    outer = [(-30, -20), (30, -20, 0.4142), (30, 20), (-30, 20)]
    hole = [(-12, -8), (12, -8), (12, 8), (-12, 8)]
    island = [(-4, -3), (4, -3), (4, 3), (-4, 3)]
    slot = [(-3, -2), (3, -2, 1.0), (3, 2), (-3, 2, 1.0)]       # a stadium: two semicircle ends
    return IR.part(
        "every_kind",
        IR.sketch("base_sk", polys=[outer, hole, island]),
        IR.pad("base", "base_sk", 12),
        IR.sketch("top_sk", circles=[(20, 0, 3)], rects=[(6, 4, -20, 12)], on={"face_of": "base", "side": "top"}),
        IR.pocket("top_pk", "top_sk", through=False, length=5),
        IR.sketch("hub_sk", "XZ", polys=[[(0, 12), (9, 12), (9, 22), (0, 22)]]),
        IR.revolve("hub", "hub_sk"),
        IR.prism_cut("side_slot", origin=(-40, 0, 6), normal=(1, 0, 0), xdir=(0, 1, 0), depth=25, polys=[slot]),
        IR.polar_pocket("ring", radius=1.5, length=8, mount_r=6, z=18, count=5, phase=10),
        IR.sketch("thru_sk", circles=[(-20, -10, 2)]),
        IR.pocket("thru", "thru_sk", through=True),
    )


# -- tests ------------------------------------------------------------------------------------

def test_poly_depths_hole_and_island():
    sq = lambda s: [(-s, -s), (s, -s), (s, s), (-s, s)]
    assert G.poly_depths([sq(10), sq(5), sq(2), [(20, 20), (22, 20), (22, 22)]]) == [0, 1, 2, 0]


def test_arc_mid_point_matches_the_other_backends():
    """The bulge's arc mid-point sits on the chord's LEFT normal, as in fc_build and build123d's
    SagittaArc (the reference). Pinned here so the scripts cannot drift from the other backends."""
    from build123d import BuildLine, SagittaArc
    (_, p1, mid, p2), = [s for s in G.poly_segments([(1, 0, 1.0), (-1, 0, 0.0)]) if s[0] == "arc"]
    with BuildLine():
        ref = SagittaArc((1, 0), (-1, 0), 1.0).position_at(0.5)
    assert mid == pytest.approx((ref.X, ref.Y))


def test_frame_matches_build123d_plane():
    fr = G.frame((1, 2, 3), (1, 0, 0), (0, 0, 1))
    pl = Plane(origin=(1, 2, 3), x_dir=(0, 0, 1), z_dir=(1, 0, 0))
    assert fr[2] == pytest.approx(tuple(pl.y_dir))
    assert G.XZ[2] == pytest.approx(tuple(Plane.XZ.y_dir))


@pytest.mark.parametrize("make", [IR.sample_plate, IR.sample_poly, every_kind])
def test_geometry_replay_matches_reference_per_feature(make):
    spec = make()
    ref = b3d_emit.emit(spec)[1]["volumes"]
    got = replay(spec)
    for f, a, b in zip(spec["features"], got, ref):
        assert _close(a, b), f"{f['name']} ({f['kind']}): replay {a} vs reference {b}"


def test_geometry_replay_on_recovered_nist_part():
    spec = json.loads((ROOT / "out" / "demo" / "nist_recovered.ir.json").read_text())
    ref = b3d_emit.emit(spec)[1]["volumes"]
    assert _close(replay(spec)[-1], ref[-1])


@pytest.mark.parametrize("target", ["fusion", "solidworks"])
def test_generated_script_is_python_and_carries_the_ir(target, tmp_path):
    spec = every_kind()
    path = script_emit.emit(target, spec, tmp_path)
    src = path.read_text()
    compile(src, str(path), "exec")
    ns = {}
    exec(src.split("# ---- featuretree shared geometry")[0], ns)   # header only: no vendor imports
    assert ns["SPEC"] == json.loads(json.dumps(spec))
    ref = b3d_emit.emit(spec)[1]["volumes"]
    assert ns["EXPECTED"] == pytest.approx(ref)
    if target == "fusion":
        man = json.loads(path.with_suffix(".manifest").read_text())
        assert man["type"] == "script"
        assert (tmp_path / "featuretree_fusion_read" / "featuretree_fusion_read.py").exists()


def test_update_from_params_round_trip():
    spec = every_kind()
    IR.update_from_params(spec, {"base": {"length": 15}, "top_pk": {"length": 2},
                                 "hub": {"angle": 180}, "side_slot": {"depth": 30}})
    by = {f["name"]: f for f in spec["features"]}
    assert (by["base"]["length"], by["top_pk"]["length"], by["hub"]["angle"], by["side_slot"]["depth"]) \
        == (15, 2, 180, 30)


def test_param_name_is_an_identifier():
    assert G.param_name("3 hole-set", "length").isidentifier()


# -- cad_verify's native-tree check, on cadmpeg's neutral feature records -----------------------

def _ext(name, op, length=None, through=False, symmetric=False):
    term = {"kind": "through_all"} if through else {"kind": "blind", "length": length}
    extent = ({"kind": "two_sided", "first": {"termination": term}, "second": {"termination": term}}
              if through else {"kind": "symmetric" if symmetric else "one_sided", "side": {"termination": term}})
    return {"name": name, "definition": {"definition": "extrude", "extent": extent, "op": op}}


def test_tree_check_matches_by_name_kind_and_value():
    import cad_verify as V
    spec = IR.part("p", IR.sketch("o", rects=[(40, 30, 0, 0)]), IR.pad("body", "o", 10),
                   IR.sketch("h", circles=[(0, 0, 4)]), IR.pocket("hole", "h", through=True),
                   IR.pocket("blind", "h", through=False, length=3),
                   IR.fillet("round", 1.5, {"circles": "top_outer"}),
                   IR.polar_pocket("ring", 1, 5, 6, count=2))
    feats = [_ext("body", "new_body", 10), _ext("hole", "cut", through=True),
             _ext("blind", "cut", 3.5),                                   # wrong depth
             {"name": "round", "definition": {"definition": "fillet",
                                              "groups": [{"radius": {"kind": "constant", "radius": 1.5}}]}},
             _ext("ring_0", "cut", 5)]                                    # ring_1 missing
    got = {r["name"]: r["status"] for r in V.tree_check(spec, feats)}
    assert got == {"body": "OK", "hole": "OK", "blind": "WRONG", "round": "OK",
                   "ring_0": "OK", "ring_1": "MISSING"}


def test_tree_check_accepts_any_same_named_candidate():
    """Native files repeat names across components; one right candidate is enough."""
    import cad_verify as V
    spec = IR.part("p", IR.sketch("o", rects=[(4, 3, 0, 0)]), IR.pad("Extrude 1", "o", 6.5))
    feats = [{"name": "Extrude 1", "definition": {"definition": "native"}}, _ext("Extrude 1", "join", 6.5)]
    assert [r["status"] for r in V.tree_check(spec, feats)] == ["OK"]
