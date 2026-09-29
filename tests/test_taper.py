"""Tapered (drafted) pads and pockets: the sign convention, and parity between backends.

IR convention (build123d's): a POSITIVE taper shrinks the profile along the extrusion. The
FreeCAD emitter maps it onto PartDesign's TaperAngle with FC_TAPER_SIGN; the parity test builds
the same tapered IR in both backends and requires equal volumes, which is what pins that sign.
"""
import math
import shutil

import pytest

import b3d_emit
import ir as IR


def _prism(taper, L=40.0, a=100.0):
    return IR.part("t", IR.sketch("s", polys=[[(0, 0), (a, 0), (a, a), (0, a)]]),
                   IR.pad("p", "s", length=L, taper=taper))


def _frustum(a, L, taper_deg):
    """Volume of a square frustum: side a at the base, shrinking by 2 L tan(taper) over L."""
    b = a - 2 * L * math.tan(math.radians(taper_deg))
    return L / 3 * (a * a + a * b + b * b)


@pytest.mark.parametrize("taper", [2.0, -2.0, 0.5])
def test_pad_taper_sign_and_volume(taper):
    part, res = b3d_emit.emit(_prism(taper))
    assert abs(res["volume"] - _frustum(100, 40, taper)) < 1e-3 * _frustum(100, 40, taper)


def test_untapered_ir_is_unchanged():
    assert "taper" not in IR.pad("p", "s", length=5)
    assert "taper" not in IR.pocket("k", "s", through=False, length=5)


def test_tapered_through_pocket_is_rejected():
    with pytest.raises(ValueError):
        IR.pocket("k", "s", through=True, taper=1.0)


def test_drafted_cavity_pocket_shrinks_going_in():
    spec = IR.part("box",
                   IR.sketch("o", polys=[[(0, 0), (100, 0), (100, 100), (0, 100)]]),
                   IR.pad("body", "o", length=50),
                   IR.sketch("c", polys=[[(10, 10), (90, 10), (90, 90), (10, 90)]],
                             on={"face_of": "body", "side": "top"}),
                   IR.pocket("cav", "c", through=False, length=40, taper=2.0))
    _, res = b3d_emit.emit(spec)
    # the cavity is an 80x80 opening narrowing going down: a frustum 40 deep
    assert abs(res["volume"] - (100 * 100 * 50 - _frustum(80, 40, 2.0))) < 1.0


@pytest.mark.skipif(shutil.which("xvfb-run") is None, reason="FreeCAD parity needs the AppImage")
def test_freecad_taper_matches_build123d(tmp_path):
    """Pins FC_TAPER_SIGN: the same tapered IR must give the same volume in FreeCAD."""
    import gen
    spec = IR.part("box",
                   IR.sketch("o", polys=[[(0, 0), (100, 0), (100, 100), (0, 100)]]),
                   IR.pad("body", "o", length=50, taper=-1.5),
                   IR.sketch("c", polys=[[(10, 10), (90, 10), (90, 90), (10, 90)]],
                             on={"face_of": "body", "side": "top"}),
                   IR.pocket("cav", "c", through=False, length=40, taper=1.0))
    _, b3d = b3d_emit.emit(spec)
    fc = gen.emit(spec, str(tmp_path / "t.FCStd"))
    assert abs(fc["volume"] - b3d["volume"]) < 1e-4 * b3d["volume"], (fc["volume"], b3d["volume"])


def test_tapered_prism_cut_volume():
    """A drafted cavity cut from the top: an 80x80 opening narrowing 2 deg over 40 mm."""
    spec = IR.part("b", IR.sketch("o", polys=[[(0, 0), (100, 0), (100, 100), (0, 100)]]),
                   IR.pad("body", "o", length=50),
                   IR.prism_cut("c", origin=(0, 0, 50), normal=(0, 0, -1), xdir=(1, 0, 0), depth=40,
                                polys=[[(10, -10), (90, -10), (90, -90), (10, -90)]], taper=2.0))
    _, res = b3d_emit.emit(spec)
    assert abs(res["volume"] - (100 * 100 * 50 - _frustum(80, 40, 2.0))) < 1.0


@pytest.mark.skipif(shutil.which("xvfb-run") is None, reason="FreeCAD parity needs the AppImage")
def test_freecad_tapered_prism_cut_matches_build123d(tmp_path):
    """Pins FC_PRISM_TAPER_SIGN (prism_cut is a REVERSED Pocket in FreeCAD). Checked to fail with
    the sign flipped (FreeCAD 234956 vs build123d 252836 mm^3)."""
    import gen
    spec = IR.part("b", IR.sketch("o", polys=[[(0, 0), (100, 0), (100, 100), (0, 100)]]),
                   IR.pad("body", "o", length=50),
                   IR.prism_cut("c", origin=(0, 0, 50), normal=(0, 0, -1), xdir=(1, 0, 0), depth=40,
                                polys=[[(10, -10), (90, -10), (90, -90), (10, -90)]], taper=2.0))
    _, b3d = b3d_emit.emit(spec)
    fc = gen.emit(spec, str(tmp_path / "t.FCStd"))
    assert abs(fc["volume"] - b3d["volume"]) < 1e-4 * b3d["volume"], (fc["volume"], b3d["volume"])
