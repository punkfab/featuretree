"""mesh_compare on meshes exported from known trees (so the right answer is known)."""
import pytest

import ir as IR
import mesh_compare as MC
from test_edge_breaks import _bushing


@pytest.fixture(scope="module")
def chamfered():
    return _bushing(IR.chamfer("rim", 2, {"edges_of": "boss", "side": "top"}))


def test_measure_finds_levels_hex_holes_and_the_chamfer(chamfered):
    m = MC.measure(MC.spec_mesh(chamfered))
    flange, boss = m["levels"]
    assert flange["outer_diameter"] == pytest.approx(100, abs=0.3) and flange["height"] == pytest.approx(30, abs=0.5)
    assert boss["outer_diameter"] == pytest.approx(70, abs=0.3) and boss["height"] == pytest.approx(90, abs=0.5)
    hexes = [h for h in flange["holes"] if h.get("sides") == 6]
    assert len(hexes) == 1 and hexes[0]["across_flats"] == pytest.approx(40, abs=0.2)
    assert hexes[0]["across_corners"] == pytest.approx(hexes[0]["ideal_across_corners"], abs=0.2)
    rounds = [h for h in flange["holes"] if h["shape"] == "round"]
    assert len(rounds) == 4 and all(h["diameter"] == pytest.approx(10, abs=0.2) for h in rounds)
    assert boss["top_break"]["height"] == pytest.approx(2, abs=0.15)          # the 2 mm chamfer
    assert boss["top_break"]["radius_lost"] == pytest.approx(2, abs=0.15)
    assert flange["top_break"] == {"height": 0.0, "radius_lost": 0.0}          # a sharp rim


def test_compare_scores_the_same_tree_high_and_a_wrong_one_lower(chamfered):
    mesh = MC.spec_mesh(chamfered)
    same = MC.compare(chamfered, mesh)
    assert same["iou_pct"] > 99.5 and abs(same["dvol_pct"]) < 0.2
    wrong = _bushing()
    wrong["features"][4]["ngons"] = [[0, 0, 50, 6, 0]]             # a 50 mm hex instead of 40
    assert MC.compare(wrong, mesh)["iou_pct"] < same["iou_pct"] - 2


def test_compare_finds_spin_and_scale(chamfered):
    import image_recognize as IM
    mesh = MC.spec_mesh(chamfered)
    mesh.apply_transform([[0.5, -0.8660254, 0, 0], [0.8660254, 0.5, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])  # 60 deg
    mesh.apply_translation([7, -3, 11])
    r = MC.compare(IM.scale_spec(chamfered, 0.5), mesh, scale=True)
    assert r["scale"] == pytest.approx(2, rel=0.01)
    assert r["iou_pct"] > 99


def test_tree_from_a_mesh_gives_one_size_per_shape(chamfered):
    mesh = MC.spec_mesh(chamfered)
    spec, notes = MC.tree(MC.measure(mesh))
    f = {x["name"]: x for x in spec["features"]}
    assert f["bore_profile"]["ngons"][0][2:4] == [40.0, 6]             # a hexagon, by one number
    assert f["step1_outline"]["circles"] == [[0, 0, 50.0]] and f["step1"]["length"] == 30.0
    assert f["step2_outline"]["circles"] == [[0, 0, 35.0]] and f["step2"]["length"] == 90.0
    holes = f["bolt_circle"]["circles"]
    assert len(holes) == 4 and {h[2] for h in holes} == {5.0}
    assert all((h[0] ** 2 + h[1] ** 2) ** 0.5 == pytest.approx(42, abs=0.01) for h in holes)
    assert any("one pattern" in n for n in notes)
    assert any("top break" in n for n in notes)                       # the chamfer is reported, not modelled
    assert not IR.validate(spec)
    assert MC.compare(spec, mesh)["iou_pct"] > 99.3


def test_tree_refuses_to_call_a_lopsided_hexagon_regular():
    spec = _bushing()
    hexagon = IR.ngon_poly(0, 0, 40, 6, 0)
    hexagon[1][1] += 1.5                                                # push one corner out
    spec["features"][4] = IR.sketch("hex_profile", polys=[hexagon])
    made, notes = MC.tree(MC.measure(MC.spec_mesh(spec)))
    assert any("not regular" in n for n in notes)
    assert not any(f.get("ngons") for f in made["features"])
