"""Tests for intent.py: re-expressing a recovered tree the way a designer would have drawn it.

Synthetic cases pin each inference against a known answer; the CTC-01 case runs the whole chain
on the NIST part vendored in tests/step. Scoring against the designer's own PMI needs the AP242
files, which are not vendored — that is paper/figures/intent_eval.py.
"""
import math
from pathlib import Path

import pytest

import intent
import ir as IR
import step_recognize as sr


def _hole(x, y, d=6.35, kind="through"):
    return intent.Hole(d, (x, y, 0.0), (0.0, 0.0, 1.0), kind, None, "t")


# --------------------------------------------------------------------------- circles from arcs

def test_two_semicircle_poly_is_a_circle():
    # how the recogniser writes a through-hole: two 180-degree arcs (bulge 1)
    cx, cy, d = intent.circle_of([[-3.0, 5.0, 1.0], [3.0, 5.0, 1.0]])
    assert (round(cx, 6), round(cy, 6), round(d, 6)) == (0.0, 5.0, 6.0)


def test_polygon_with_a_straight_edge_is_not_a_circle():
    assert intent.circle_of([[0, 0, 1.0], [6, 0, 0.0], [6, 6, 0.0]]) is None


# --------------------------------------------------------------------------- sizes and units

@pytest.mark.parametrize("d_mm, units, want", [
    (6.35, "inch", '1/4"'),
    (3.969, "inch", '5/32"'),
    (19.05, "inch", '3/4"'),
    (5.944, "inch", "letter A"),     # closest wins: 15/64" is 0.009 mm off, letter A 0.0004 mm
    (7.137, "inch", "letter K"),
    (5.613, "inch", "#2"),
    (8.0, "metric", "8 mm"),
    (6.6, "metric", "6.6 mm"),
])
def test_nominal_sizes(d_mm, units, want):
    assert intent.nominal(d_mm, units).startswith(want)


def test_off_grid_size_has_no_nominal():
    assert intent.nominal(6.4213, "metric") is None


def test_units_inch_vs_metric():
    assert intent.infer_units([6.35, 9.525, 19.05, 25.4, 76.2])[0] == "inch"
    assert intent.infer_units([6.6, 20.0, 35.0, 60.0, 150.0])[0] == "metric"


# --------------------------------------------------------------------------- patterns

def _types(pats):
    return sorted((p["type"], len(p["holes"])) for p in pats)


def test_linear_array():
    pats = intent.patterns([_hole(10 * i, 0) for i in range(5)])
    assert _types(pats) == [("linear", 5)] and abs(pats[0]["pitch"] - 10) < 1e-9


def test_bolt_circle():
    pats = intent.patterns([_hole(40 * math.cos(a), 40 * math.sin(a))
                            for a in (2 * math.pi * k / 6 for k in range(6))])
    assert _types(pats) == [("polar", 6)] and abs(pats[0]["pcd"] - 80) < 1e-6


def test_rotated_rectangle():
    c, s = math.cos(0.3), math.sin(0.3)
    corners = [(0, 0), (30, 0), (30, 20), (0, 20)]
    pats = intent.patterns([_hole(x * c - y * s, x * s + y * c) for x, y in corners])
    assert _types(pats) == [("rectangle", 4)]


def test_different_diameters_never_share_a_pattern():
    hs = [_hole(10 * i, 0, d=6.35) for i in range(3)] + [_hole(10 * i, 0, d=8.0) for i in range(3, 6)]
    assert _types(intent.patterns(hs)) == [("linear", 3), ("linear", 3)]


# --------------------------------------------------------------------------- from a real tree

def test_counterbore_is_one_hole():
    hs = [_hole(0, 0, d=6.6), intent.Hole(11.0, (0.0, 0.0, 5.0), (0.0, 0.0, 1.0), "blind", 6.0, "cb")]
    (thru, bore), = intent.counterbores(hs)
    assert thru.diameter == 6.6 and bore.diameter == 11.0


def test_revolve_bore_and_outer_diameter():
    spec = IR.part("ring",
                   IR.sketch("section", "XZ", polys=[[(16, -1.5), (16, 1.5), (31.5, 1.5), (31.5, -1.5)]]),
                   IR.revolve("body", "section"))
    kinds = sorted((h.kind, round(h.diameter, 3)) for h in intent.holes(spec))
    assert kinds == [("bore", 32.0), ("outer", 63.0)]


def test_nist_ctc01_holes_units_and_nominals():
    """CTC-01 is a metric part whose drawing calls out 20, 25 and 35 mm holes."""
    spec, rep = sr.recognize(str(Path(__file__).parent / "step" / "nist_ctc_01_asme1_rd.stp"))
    assert rep["verified"]
    d = intent.describe(spec, extents=(800.0, 450.0, 150.0))
    assert d["units"] == "metric"
    labels = set(d["nominals"].values())
    assert {"20 mm", "25 mm", "35 mm"} <= labels
