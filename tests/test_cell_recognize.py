"""Cell-decomposition recognition (cell_recognize.py) and the loop fixes found on the same part.

The part is a flange coupling built here with build123d: a rounded plate, a hub, a through bore,
four counterbored bolt holes, a ring groove under the hub, and a key slot that only just reaches
the bore (it meets it at one point). That last detail is what broke loop tracing: the bore and the
slot form one outline that touches itself."""
import math
import sys
from pathlib import Path

import pytest
from build123d import Box, Cylinder, Pos, RectangleRounded, export_step, extrude

import b3d_emit
import ir as IR

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "targets"))
import _geom as G  # noqa: E402


def flange():
    part = extrude(RectangleRounded(60, 60, 8), 8) + Pos(0, 0, 19) * Cylinder(14, 22)
    part -= Pos(0, 0, 15) * Cylinder(8, 30)                                   # bore
    part -= Pos(9.5, 0, 18) * Box(3, 5, 24)                                   # key slot, x 8..11: tangent to the bore
    ring = Pos(0, 0, 7.5) * Cylinder(15, 1) + Pos(0, 0, 8.5) * Cylinder(14, 1)
    part -= ring - Pos(0, 0, 8) * Cylinder(13, 2)                             # groove under the hub
    for sx in (-1, 1):
        for sy in (-1, 1):
            part -= Pos(20 * sx, 20 * sy, 4) * Cylinder(3, 8) + Pos(20 * sx, 20 * sy, 6.5) * Cylinder(5, 3)
    return part


@pytest.fixture(scope="module")
def flange_step(tmp_path_factory):
    p = tmp_path_factory.mktemp("cells") / "flange.step"
    export_step(flange(), str(p))
    return p


def test_cells_recover_the_flange(flange_step):
    import cell_recognize
    spec, rep = cell_recognize.recognize(flange_step)
    assert rep["verified"], rep
    assert rep["iou_pct"] >= 99.5 and rep["dvol_pct"] <= 0.5
    assert IR.validate(spec) == []
    assert rep["unsupported_faces"] == 0 and not rep["warnings"]


def test_a_pinched_loop_splits_into_its_simple_loops():
    import step_recognize as R
    # bore (two arcs through (8, 0)) + a slot that starts at (8, 0): one loop through that point twice
    loop = [[0.0, 8.0, -2.414214], [8.0, 0.0, 0.0], [8.0, 2.5, 0.0], [11.0, 2.5, 0.0], [11.0, -2.5, 0.0],
            [8.0, -2.5, 0.0], [8.0, 0.0, -0.414214]]
    parts = R._split_pinched(loop)
    assert sorted(len(p) for p in parts) == [2, 5]
    assert R._split_pinched([[0, 0, 0], [4, 0, 0], [4, 3, 0]]) == [[[0, 0, 0], [4, 0, 0], [4, 3, 0]]]


def test_nesting_sees_a_circle_drawn_as_two_arcs():
    """A two-arc circle has two vertices; as a bare vertex polygon it has no area and contains
    nothing, so a hole inside a round boss was not cut."""
    boss, hole = [(14, 0, 1.0), (-14, 0, 1.0)], [(8, 0, 1.0), (-8, 0, 1.0)]
    assert G.poly_depths([boss, hole]) == [0, 1]
    spec = IR.part("ring", IR.sketch("s", polys=[boss, hole]), IR.pad("b", "s", 10))
    assert b3d_emit.emit(spec)[1]["volume"] == pytest.approx(math.pi * (14 ** 2 - 8 ** 2) * 10, rel=1e-4)
