"""Tests for mesh_check: is a rebuilt solid one closed body?

The analytic cases pin each of the three defects it reports. The NIST tests record where the
recovered trees stand: the VERIFIED part is clean, and the defects found by scoring our output
with a mesh-based metric (open tessellation, enclosed voids, split solids) are reported, not missed.
"""
import json
from pathlib import Path

import numpy as np
import pytest
from build123d import Box, Compound, Cylinder, Pos, Shell, Sphere

import b3d_emit
import ir as IR
import mesh_check
import step_recognize as sr

RECOVERED = Path(__file__).resolve().parent.parent / "paper" / "figures" / "recovered"


def test_box_is_one_closed_body():
    r = mesh_check.check(Box(10, 20, 30))
    assert (r["solids"], r["voids"], r["closed"]) == (1, 0, True)
    assert r["triangles"] == 12 and r["open_edges"] == 0 and r["nonmanifold_edges"] == 0
    assert mesh_check.problems(r) == []


def test_curved_solid_with_a_through_hole_is_closed():
    r = mesh_check.check(Cylinder(10, 20) - Cylinder(3, 20))
    assert (r["solids"], r["voids"], r["closed"]) == (1, 0, True)


def test_separate_solids_are_counted():
    r = mesh_check.check(Compound([Box(10, 10, 10), Pos(30, 0, 0) * Box(10, 10, 10)]))
    assert r["solids"] == 2 and r["closed"]
    assert mesh_check.problems(r) == ["2 separate solid(s) where the input has 1"]
    assert mesh_check.problems(r, original=r) == []          # the input really is two bodies


def test_enclosed_void_is_counted():
    hollow = Box(20, 20, 20) - Sphere(5)
    r = mesh_check.check(hollow)
    assert (r["solids"], r["voids"], r["closed"]) == (1, 1, True)
    assert mesh_check.problems(r) == ["1 enclosed void(s) where the input has 0"]


def test_open_tessellation_is_reported():
    # A box with one face removed: five faces, four free edges.
    box = Box(10, 10, 10)
    lid = box.faces().sort_by()[-1]
    r = mesh_check.check(Shell([f for f in box.faces() if not f.is_same(lid)]))
    assert not r["closed"] and r["open_edges"] == 4
    assert any("not closed" in p for p in mesh_check.problems(r))


def test_edge_counts_on_a_bare_triangle_and_a_fan():
    assert mesh_check.edge_counts(np.array([[0, 1, 2]])) == (3, 0)
    fan = np.array([[0, 1, 2], [0, 1, 3], [0, 1, 4]])        # three triangles on edge 0-1
    assert mesh_check.edge_counts(fan) == (6, 1)


def test_verify_reports_the_body_and_keeps_a_sound_part_verified(tmp_path):
    from _helpers import emit_step
    spec, rep = sr.recognize(emit_step(IR.SAMPLES["plate"](), tmp_path))
    assert rep["verified"]
    assert rep["body"]["closed"] and rep["body_problems"] == []


def test_verify_demotes_a_tree_that_is_not_one_body():
    # Two pads that do not touch, against a one-solid frame with the same volume (2000) and the
    # same extents (40 x 10 x 10). Volume and extents pass; the body test must not.
    spec = IR.part("two",
                   IR.sketch("a", "XY", rects=[(10, 10, -15, 0)]), IR.pad("pa", "a", length=10),
                   IR.sketch("b", "XY", rects=[(10, 10, 15, 0)]), IR.pad("pb", "b", length=10))
    frame = Box(40, 10, 10) - Box(25, 8, 10)
    rep = sr._verify(spec, frame)
    assert rep["dvol_pct"] < 0.5 and rep["dsize_mm"] < 0.05
    assert rep["verified"] is False
    assert rep["body_problems"] == ["2 separate solid(s) where the input has 1"]
    assert "not one closed body" in rep["reason"]


def _recovered(part):
    fn = RECOVERED / f"{part}.json"
    if not fn.exists():
        pytest.skip("recovered tree not present")
    spec = json.loads(fn.read_text())["spec"]
    return b3d_emit.emit(spec)[0]


def test_nist_ctc01_verified_recovery_is_one_closed_body():
    r = mesh_check.check(_recovered("nist_ctc_01_asme1_rd.stp"))
    assert mesh_check.problems(r) == [], r


def test_layers_that_almost_coincide_leave_no_sliver_face():
    """Two stacked discs whose radii differ by 0.06 um (what a fitted arc is off by). Exact
    Booleans keep that as a ring-shaped ledge 0.06 um wide; on NIST CTC-05 the mesher could not
    triangulate such faces and the solid tessellated open. The emitter's tolerant Booleans treat
    the two edges as one, so no such face exists."""
    spec = IR.part("ledge",
                   IR.sketch("a", "XY", circles=[(0, 0, 152.4)]), IR.pad("pa", "a", length=10),
                   IR.sketch("b", circles=[(0, 0, 152.40006)], on={"face_of": "pa", "side": "top"}),
                   IR.pad("pb", "b", length=10))
    part, res = b3d_emit.emit(spec)
    assert res["booleans"] == "tolerant"
    assert min(f.area for f in part.faces()) > 1.0           # the ledge would be 0.06 mm^2
    assert mesh_check.problems(mesh_check.check(part)) == []


@pytest.mark.parametrize("part", ["nist_ctc_05_asme1_rd.stp", "nist_ftc_06_asme1_rd.stp",
                                  "nist_ftc_07_asme1_rd.stp"])
def test_nist_recoveries_that_were_open_or_hollow_are_now_one_closed_body(part):
    assert mesh_check.problems(mesh_check.check(_recovered(part))) == []


# Known defects in the persisted PARTIAL recoveries. Each is xfail(strict): when the recogniser
# is fixed the test passes, strict turns that into a failure, and the marker has to come off.
@pytest.mark.xfail(strict=True, reason="CTC-03 rebuilds as five solids")
def test_nist_ctc03_recovery_is_one_closed_body():
    assert mesh_check.problems(mesh_check.check(_recovered("nist_ctc_03_asme1_rc.stp"))) == []


@pytest.mark.xfail(strict=True, reason="CTC-04 rebuilds with two detached feet")
def test_nist_ctc04_recovery_is_one_closed_body():
    assert mesh_check.problems(mesh_check.check(_recovered("nist_ctc_04_asme1_rd.stp"))) == []


@pytest.mark.xfail(strict=True, reason="CTC-02 rebuild holds sixteen sealed hole segments")
def test_nist_ctc02_recovery_is_one_closed_body():
    assert mesh_check.problems(mesh_check.check(_recovered("nist_ctc_02_asme1_rc.stp"))) == []
