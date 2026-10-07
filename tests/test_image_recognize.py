"""image_recognize: pose, dimension fit and bookkeeping, on pictures rendered from known trees.
No model is called; the proposal is passed in with --spec's code path."""
import copy

import cv2
import pytest

import image_recognize as IM
import ir


def _stepped():
    return ir.part(
        "stepped",
        ir.sketch("base_outline", circles=[(0, 0, 30)]),
        ir.pad("base", "base_outline", 12),
        ir.sketch("boss_outline", circles=[(0, 0, 16)], on={"face_of": "base", "side": "top"}),
        ir.pad("boss", "boss_outline", 30),
        ir.sketch("holes", circles=[(23, 0, 2.5), (-23, 0, 2.5), (0, 23, 2.5), (0, -23, 2.5)]),
        ir.pocket("bolt_holes", "holes", through=True),
    )


def _picture(spec, tmp_path, cam=(40.0, 30.0, 0.0, 1.0, 0.0, 0.0)):
    mesh, _, problems = IM.build(spec)
    assert not problems
    p = tmp_path / "part.png"
    cv2.imwrite(str(p), IM.render(mesh, cam, 400))
    return str(p)


def test_pose_recovers_the_view_of_the_same_tree(tmp_path):
    r = IM.recognize(_picture(_stepped(), tmp_path), spec=_stepped())
    assert r["status"] == "ROUGH"
    assert r["silhouette_iou"] > 98
    assert abs(r["camera"]["elevation"] - 30) < 3
    assert any("size is a guess" in w for w in r["warnings"])
    assert any("bolt_holes" in w for w in r["warnings"])


def test_fit_corrects_proportions_and_carries_the_holes_along(tmp_path):
    guess = copy.deepcopy(_stepped())
    f = {x["name"]: x for x in guess["features"]}
    f["boss"]["length"] = 20                      # true 30
    f["base_outline"]["circles"][0][2] = 36       # true 30
    f["holes"]["circles"] = [[c[0] * 1.2, c[1] * 1.2, c[2]] for c in f["holes"]["circles"]]
    image = _picture(_stepped(), tmp_path)
    before = IM.recognize(image, spec=guess)
    after = IM.recognize(image, spec=guess, fit=True, size=60)
    assert after["silhouette_iou"] > before["silhouette_iou"] + 3
    assert after["silhouette_iou"] > 98
    g = {x["name"]: x for x in after["spec"]["features"]}
    assert max(after["extents_mm"]) == pytest.approx(60, abs=0.01)       # --size pins the diameter
    k = 1.0
    assert g["boss"]["length"] == pytest.approx(30 * k, rel=0.08)
    assert g["base_outline"]["circles"][0][2] == pytest.approx(30 * k, rel=0.08)
    # the hole circle is invisible in the outline: it must follow the base it sits in
    assert g["holes"]["circles"][0][0] == pytest.approx(23 * k, rel=0.08)
    assert not ir.validate(after["spec"])


def test_scale_spec_scales_lengths_only():
    s = IM.scale_spec(ir.part("p", ir.prism_cut("c", (1, 2, 3), (0, 0, 1), (1, 0, 0), 4,
                                              polys=[[(0, 0, 0.5), (2, 0), (2, 2)]])), 2)
    c = s["features"][0]
    assert c["origin"] == [2, 4, 6] and c["depth"] == 8 and c["normal"] == [0, 0, 1]
    assert c["polys"][0][0] == [0, 0, 0.5] and c["polys"][0][1] == [4, 0]


def test_scale_spec_keeps_a_hexagon_a_hexagon_and_scales_a_chamfer():
    s = IM.scale_spec(ir.part("p", ir.sketch("h", ngons=[(1, 2, 40, 6, 15)]),
                              ir.chamfer("c", 2, {"circles": "top_outer"})), 0.5)
    assert s["features"][0]["ngons"] == [[0.5, 1.0, 20.0, 6, 15]]
    assert s["features"][1]["distance"] == 1.0


def test_reply_parsing_and_prompt():
    spec, assumed = IM._parse('```json\n{"name": "x", "features": [], "assumptions": ["a"]}\n```')
    assert spec == {"name": "x", "features": []} and assumed == ["a"]
    with pytest.raises(ValueError):
        IM._parse("I cannot tell.")
    prompt = IM.system_prompt()
    for kind in ("sketch(", "pad(", "pocket(", "prism_cut(", "polar_pocket(", "chamfer(", "ngons"):
        assert kind in prompt


def test_unbuildable_spec_is_reported(tmp_path):
    bad = ir.part("bad", ir.pad("body", "missing", 5))
    with pytest.raises(ValueError, match="does not build"):
        IM.recognize(_picture(_stepped(), tmp_path), spec=bad)
