"""Chamfers, edge queries by feature ({"edges_of": ...}) and regular-polygon sketches."""
import math
import shutil

import pytest

import b3d_emit
import ir as IR


def _bushing(*extra):
    return IR.part(
        "bushing",
        IR.sketch("flange_outline", circles=[(0, 0, 50)]),
        IR.pad("flange", "flange_outline", 30),
        IR.sketch("boss_outline", circles=[(0, 0, 35)], on={"face_of": "flange", "side": "top"}),
        IR.pad("boss", "boss_outline", 90),
        IR.sketch("hex_profile", ngons=[(0, 0, 40, 6, 0)]),
        IR.pocket("hex", "hex_profile"),
        IR.sketch("bolt_circle", circles=[(42, 0, 5), (-42, 0, 5), (0, 42, 5), (0, -42, 5)]),
        IR.pocket("bolt_holes", "bolt_circle"),
        *extra,
    )


def test_ngon_is_regular_and_lowers_to_a_poly():
    pts = IR.ngon_poly(3, -2, 40, 6, 15)
    assert len(pts) == 6
    for i, (x, y) in enumerate(pts):
        assert math.hypot(x - 3, y + 2) == pytest.approx(20 / math.cos(math.pi / 6))
        assert math.degrees(math.atan2(y + 2, x - 3)) % 360 == pytest.approx(15 + 60 * i)
    low = IR.lower(_bushing())
    hexs = next(f for f in low["features"] if f["name"] == "hex_profile")
    assert "ngons" not in hexs and len(hexs["polys"]) == 1 and len(hexs["polys"][0]) == 6
    assert IR.lower(low) == low                               # idempotent
    assert "ngons" in next(f for f in _bushing()["features"] if f["name"] == "hex_profile")


def test_hex_pocket_volume():
    with_hex = b3d_emit.emit(_bushing())[1]["volumes"]
    area = 6 * 20 * 20 * math.tan(math.pi / 6)                # regular hexagon, apothem 20
    assert with_hex[4] - with_hex[5] == pytest.approx(area * 120, rel=1e-6)


def test_edge_queries_resolve_to_points_on_the_right_edges():
    low = IR.lower(_bushing(IR.chamfer("a", 2, {"edges_of": "boss", "side": "top"}),
                            IR.chamfer("b", 2, {"edges_of": "flange", "side": "top"}),
                            IR.chamfer("c", 1, {"edges_of": "hex", "side": "top"}),
                            IR.chamfer("d", 1, {"edges_of": "bolt_holes", "side": "top"}),
                            IR.chamfer("e", 1, {"edges_of": "hex", "side": "bottom"})))
    picks = {f["name"]: f["picks"] for f in low["features"] if "picks" in f}
    assert {p[2] for p in picks["a"]} == {120} and math.hypot(*picks["a"][0][:2]) == pytest.approx(35)
    assert {p[2] for p in picks["b"]} == {30}
    assert len(picks["c"]) == 6 and {p[2] for p in picks["c"]} == {120}     # the socket's mouth
    assert len(picks["d"]) == 4 and {p[2] for p in picks["d"]} == {30}      # holes open on the flange
    assert {p[2] for p in picks["e"]} == {0}


def test_chamfer_volumes():
    v = b3d_emit.emit(_bushing(IR.chamfer("rim", 2, {"edges_of": "boss", "side": "top"}),
                               IR.chamfer("mouth", 1, {"edges_of": "hex", "side": "top"}),
                               IR.fillet("root", 1.5, {"edges_of": "boss", "side": "bottom"})))[1]
    vols = v["volumes"]
    ring = math.pi * (35 ** 2 * 2 - (35 ** 3 - 33 ** 3) / 3)   # a 2 x 2 triangle swept round r = 35
    assert vols[7] - vols[8] == pytest.approx(ring, rel=1e-4)
    assert vols[9] < vols[8]                                   # the hex mouth is broken
    assert vols[10] > vols[9]                                  # a fillet in a concave corner adds
    assert v["params"]["rim"] == {"distance": 2.0}


def test_validate_catches_bad_edge_breaks():
    assert IR.validate(_bushing(IR.chamfer("rim", 2, {"edges_of": "boss", "side": "top"}))) == []
    assert any("positive size" in p for p in IR.validate(_bushing(IR.chamfer("x", 0, {"circles": "top_outer"}))))
    assert any("not an earlier pad or pocket" in p
               for p in IR.validate(_bushing(IR.chamfer("x", 1, {"edges_of": "nope"}))))
    assert any("select needs" in p for p in IR.validate(_bushing(IR.chamfer("x", 1, {}))))
    bad = _bushing()
    bad["features"][4]["ngons"] = [[0, 0, 40, 2, 0]]
    assert any("ngon" in p for p in IR.validate(bad))


def test_a_missing_edge_is_an_error_not_a_guess():
    twice = _bushing(IR.chamfer("rim", 2, {"edges_of": "boss", "side": "top"}),
                     IR.chamfer("again", 1, {"edges_of": "boss", "side": "top"}))   # that edge is gone
    with pytest.raises(ValueError, match="again"):
        b3d_emit.emit(twice)


def test_chamfer_edit_reads_back():
    spec = _bushing(IR.chamfer("rim", 2, {"edges_of": "boss", "side": "top"}))
    IR.update_from_params(spec, {"rim": {"distance": 3.5}})
    assert spec["features"][-1]["distance"] == 3.5


@pytest.mark.skipif(shutil.which("xvfb-run") is None, reason="FreeCAD parity needs the AppImage")
def test_freecad_builds_the_same_edge_breaks(tmp_path):
    import gen
    spec = _bushing(IR.chamfer("rim", 2, {"edges_of": "boss", "side": "top"}),
                    IR.chamfer("flange_rim", 1.5, {"edges_of": "flange", "side": "top"}),
                    IR.chamfer("mouth", 1, {"edges_of": "hex", "side": "top"}),
                    IR.chamfer("hole_mouths", 0.8, {"edges_of": "bolt_holes", "side": "top"}),
                    IR.fillet("root", 1.5, {"edges_of": "boss", "side": "bottom"}))
    ref = b3d_emit.emit(spec)[1]
    fc = gen.emit(spec, str(tmp_path / "b.FCStd"))
    assert fc["volume"] == pytest.approx(ref["volume"], rel=1e-4)
    kinds = [t[1] for t in fc["tree"]]
    assert kinds.count("PartDesign::Chamfer") == 4 and kinds.count("PartDesign::Fillet") == 1
    assert fc["params"]["rim"] == {"distance": 2.0}
