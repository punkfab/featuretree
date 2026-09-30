"""Offline tests for the Onshape backend's geometry (no network): the arc conversion to Onshape's
centre/angle form, the interior points that pick sketch regions, and the reference backend's rule
for pads on a bottom face. The live conventions (draft pull direction, plane frames) were pinned
against Onshape on 2026-09-29 by building tapered parts and matching build123d's volume after
every feature; see paper/figures/onshape_corpus.py for the corpus run."""
import math
import sys
from pathlib import Path

import pytest

import b3d_emit
import ir as IR

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "targets"))
import _geom as G  # noqa: E402

onshape_emit = pytest.importorskip("onshape_emit")


def test_arc_centre_radius_and_sweep_pass_through_mid():
    c, r, a1, sweep = onshape_emit._arc((1, 0), (0, 1), (-1, 0))
    assert c == pytest.approx((0, 0)) and r == pytest.approx(1)
    assert a1 == pytest.approx(0) and sweep == pytest.approx(math.pi)          # CCW through (0, 1)
    c, r, a1, sweep = onshape_emit._arc((1, 0), (0, -1), (-1, 0))
    assert sweep == pytest.approx(-math.pi)                                     # CW through (0, -1)


def test_interior_points_skip_holes_and_land_in_islands():
    from shapely.geometry import Point, Polygon
    sq = lambda s: [(-s, -s), (s, -s), (s, s), (-s, s)]                          # noqa: E731
    loops = G.sketch_loops(polys=[sq(10), sq(5), sq(2)])
    pts = onshape_emit._interior_points(G.XY, loops)
    assert len(pts) == 2                                                        # outer band + island
    band = Polygon(sq(10)).difference(Polygon(sq(5)))
    assert band.contains(Point(pts[0][:2])) and Polygon(sq(2)).contains(Point(pts[1][:2]))


def test_pad_on_a_bottom_face_at_z0_grows_down():
    """A bottom-face pad grows outward (-Z) even when the bottom face is at z = 0. Before the fix,
    b3d_emit decided 'bottom' by z < 0 and padded UP into the part here."""
    spec = IR.part("p", IR.sketch("b", rects=[(40, 30, 0, 0)]), IR.pad("base", "b", 10),
                   IR.sketch("d", circles=[(0, 0, 4)], on={"face_of": "base", "side": "bottom"}),
                   IR.pad("boss", "d", 5))
    part, res = b3d_emit.emit(spec)
    assert res["volume"] == pytest.approx(12000 + math.pi * 16 * 5, rel=1e-4)
    assert part.bounding_box().min.Z == pytest.approx(-5)


# -- ir.validate: the spec's well-formedness rules -------------------------------------------------

def test_validate_accepts_the_samples_and_a_two_arc_slot():
    assert IR.validate(IR.sample_plate()) == [] and IR.validate(IR.sample_poly()) == []
    slot = [(-3, -2), (3, -2, 1.0), (3, 2), (-3, 2, 1.0)]
    circle_as_two_arcs = [(2, 0, 1.0), (-2, 0, 1.0)]
    spec = IR.part("p", IR.sketch("s", polys=[[(-10, -10), (10, -10), (10, 10), (-10, 10)], slot]),
                   IR.pad("b", "s", 5), IR.sketch("h", polys=[circle_as_two_arcs]), IR.pocket("c", "h", through=True))
    assert IR.validate(spec) == []


def test_validate_flags_touching_loops_bad_refs_and_duplicates():
    a = [(0, 0), (10, 0), (10, 10), (0, 10)]
    b = [(10, 0), (20, 0), (20, 10), (10, 10)]                      # shares an edge with a
    spec = IR.part("p", IR.sketch("s", polys=[a, b]), IR.pad("x", "s", 5), IR.pad("x", "nope", 5))
    probs = IR.validate(spec)
    assert any("touch or cross" in p for p in probs)
    assert any("duplicate" in p for p in probs) and any("not an earlier sketch" in p for p in probs)
