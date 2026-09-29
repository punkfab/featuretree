"""Open-shell recognition (boxes, cups, enclosures) and exact registration.

A molded box is not a prism along any axis: across the opening you slice two stray walls, and
along it the drafted walls change with depth. Recognition has to look at it from several
aspects — along the opening axis the slices are rings — and recover it as a designer would:
a drafted pad and a drafted cavity pocket. (NIST FTC-07 is this part: ~1 deg draft inside and
out; it went from "two walls, 63% short" to a drafted box at ~95% IoU.)
"""
import pytest
from build123d import Plane, Pos, Rectangle, Rot, extrude

import b3d_emit
import iou_check
import step_recognize as sr
from _helpers import part_step


def _drafted_box(draft=1.0, floor=5.0, H=40.0):
    outer = extrude(Rectangle(100, 60), amount=H, taper=-draft)           # widens upward
    cavity = extrude(Plane.XY.offset(H) * Rectangle(92, 52), amount=H - floor,
                     dir=(0, 0, -1), taper=draft)                         # narrows going down
    return outer - cavity


def test_drafted_open_box_is_recovered_as_a_drafted_shell(tmp_path):
    spec, rep = sr.recognize(part_step(_drafted_box(), tmp_path))
    kinds = [(f["kind"], f.get("taper", 0.0)) for f in spec["features"]]
    assert any(k == "pad" and t < 0 for k, t in kinds), kinds          # drafted outward
    assert any(k == "pocket" and t > 0 for k, t in kinds), kinds       # cavity narrows inward
    assert any("open shell" in w for w in rep["warnings"])
    assert rep["verified"], rep


def test_draft_angle_is_measured(tmp_path):
    _, rep = sr.recognize(part_step(_drafted_box(draft=2.0), tmp_path))
    w = next(w for w in rep["warnings"] if "draft" in w)
    assert "2.00 deg outside" in w and "2.00 deg inside" in w, w


def test_prismatic_plate_is_not_mistaken_for_a_shell(tmp_path):
    plate = extrude(Rectangle(100, 60), amount=8) - extrude(Rectangle(10, 10), amount=8)
    _, rep = sr.recognize(part_step(plate, tmp_path))
    assert rep["verified"] and not any("open shell" in w for w in rep["warnings"])


def test_exact_registration_of_a_rotated_recovery(tmp_path):
    """A part extruded along Y is recognised in a frame rotated onto Z; input_frame must undo
    that exactly, so the measured IoU is ~1 with no orientation search."""
    part = Rot(90, 0, 0) * (extrude(Rectangle(80, 30), amount=12) - Pos(20, 0, 0) * extrude(Rectangle(8, 8), amount=12))
    path = part_step(part, tmp_path)
    spec, rep = sr.recognize(path)
    assert rep["verified"]
    from build123d import import_step
    orig = import_step(path)
    place, point, direction = sr.input_frame(orig, rep)
    p, ci = iou_check.iou(orig, place(b3d_emit.emit(spec)[0]), n=20000)
    assert p > 0.995, (p, ci)
