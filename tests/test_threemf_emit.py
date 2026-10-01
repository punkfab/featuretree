"""3MF emit: an assembly IR -> 3MF package (hierarchy + materials + embedded IR), round-tripped
through lib3mf's own reader — at the authored pose and at a solved closed-loop pose."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("lib3mf")
import assembly_kin as K
import b3d_emit
import threemf_emit as E
from test_assembly_loops import fourbar_asm, TH0, fourbar


def _local(occ):
    solid, _ = b3d_emit.emit(occ["part"])
    v, _ = solid.tessellate(0.05)
    return np.array([(p.X, p.Y, p.Z) for p in v], float)


@pytest.mark.parametrize("pose", [None, {"crank": 90.0}])
def test_roundtrip_places_every_occurrence(tmp_path, pose):
    asm = fourbar_asm()
    f = str(tmp_path / "fb.3mf")
    r = E.emit_assembly(asm, f, pose=pose)
    assert r == {"objects": 4, "components": 4}
    back = dict(E.read_assembly(f))
    T = K.solve(asm, pose)[1] if pose else K.posed(asm, {})
    for occ in asm["occurrences"]:
        v = _local(occ)
        want = (T[occ["id"]][:3, :3] @ v.T).T + T[occ["id"]][:3, 3]
        assert np.abs(back[occ["label"]] - want).max() < 1e-2          # float32 in the package


def test_posed_package_keeps_the_loop_closed(tmp_path):
    asm = fourbar_asm()
    f = str(tmp_path / "fb.3mf")
    E.emit_assembly(asm, f, pose={"crank": 90.0})
    rk = dict(E.read_assembly(f))["rocker"]
    # the rocker still pivots on the ground's O4 = (d, 0): its end nearest O4 is within the bar's half-width
    from test_assembly_loops import d
    assert np.min(np.linalg.norm(rk[:, :2] - [d, 0.0], axis=1)) < 4.5


def test_ir_travels_inside_the_package(tmp_path):
    asm = fourbar_asm()
    f = str(tmp_path / "fb.3mf")
    E.emit_assembly(asm, f)
    ir = E.read_embedded_ir(f)
    assert ir["closures"][0]["name"] == "rocker_pivot" and len(ir["mates"]) == 3
