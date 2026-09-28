"""Tests for iou_check: Boolean-free IoU by point classification.

The analytic cases pin the estimator against exact answers. The NIST test guards the
paper's headline claim — a VERIFIED recovery really overlaps its input — with a
measurement that shares no failure modes with the OpenCASCADE Booleans that
mis-scored four PARTIAL parts in preprint v2.
"""
from pathlib import Path

from build123d import Box, Pos, Rot

import b3d_emit
import iou_check
import step_recognize as sr


def _within(p, ci, expected):
    """Estimate agrees with the exact value to within 3 half-widths (plus a hair)."""
    return abs(p - expected) <= 3 * ci + 1e-3


def test_identical_solids_iou_is_one():
    p, ci = iou_check.iou(Box(10, 20, 30), Box(10, 20, 30), n=20000)
    assert _within(p, ci, 1.0)


def test_half_overlap_is_one_third():
    # Two unit cubes offset by half a side: |A∩B| = 0.5, |A∪B| = 1.5  =>  IoU = 1/3 exactly.
    p, ci = iou_check.iou(Box(10, 10, 10), Pos(5, 0, 0) * Box(10, 10, 10), n=40000)
    assert _within(p, ci, 1 / 3)


def test_disjoint_solids_iou_is_zero():
    p, _ = iou_check.iou(Box(10, 10, 10), Pos(50, 0, 0) * Box(10, 10, 10), n=20000)
    assert p == 0.0


def test_multi_solid_shapes_count_every_solid():
    # A two-solid reconstruction must be scored whole. Scoring only the first solid is the
    # bug that under-scored CTC-02 / FTC-07 / FTC-08.
    two = [Box(10, 10, 10), Pos(30, 0, 0) * Box(10, 10, 10)]
    from build123d import Compound
    p, ci = iou_check.iou(Compound(two), Compound(two), n=20000)
    assert _within(p, ci, 1.0)


def test_exactly_24_distinct_rotations():
    assert len(iou_check.ROTATIONS) == 24


def test_registered_iou_undoes_an_axis_rotation():
    # A 10x20x40 slab rotated 90 deg about X, then translated: registration must find it again.
    orig = Box(10, 20, 40)
    moved = Pos(100, -50, 7) * (Rot(90, 0, 0) * Box(10, 20, 40))
    r = iou_check.registered_iou(orig, moved, n=20000, n_search=2000)
    assert r["lower_bound"] is True
    assert _within(r["iou"], r["ci"], 1.0)


def test_nist_ctc01_verified_recovery_overlaps_input():
    """Guards the paper: VERIFIED must mean the geometry is really there, measured without
    Booleans. CTC-01 recovers at ~99.8% IoU; 99.5% leaves margin for sampling noise."""
    path = Path(__file__).parent / "step" / "nist_ctc_01_asme1_rd.stp"
    spec, rep = sr.recognize(str(path))
    assert rep["verified"]
    from build123d import import_step
    orig = import_step(str(path)).solids()[0]
    rec, _ = b3d_emit.emit(spec)
    r = iou_check.registered_iou(orig, rec, n=30000, n_search=1500)
    assert r["iou"] >= 0.995, r


def test_stray_non_solid_geometry_is_ignored():
    """Regression: NIST STEP imports carry free wires/points outside the solid. Passing the raw
    import must give the same answer as passing the solid (it once gave 20% for a 99.8% part)."""
    from build123d import Compound, Edge
    solid = Box(10, 10, 10)
    with_junk = Compound([solid, Edge.make_line((0, 0, 0), (200, 0, 0))])  # bbox 20x wider
    r = iou_check.registered_iou(with_junk, Box(10, 10, 10), n=10000, n_search=1000)
    assert _within(r["iou"], r["ci"], 1.0)
