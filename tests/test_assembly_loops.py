"""Loop closures in the assembly IR: validation, mobility, the pose solver and the MJCF emitter —
all checked against the CLOSED-FORM four-bar (ground truth), not against themselves."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import assembly_ir as A
import assembly_kin as K
import ir

# Grashof crank-rocker: shortest link (crank) + longest <= sum of the other two -> crank fully rotates
a, b, c, d = 20.0, 60.0, 45.0, 50.0
TH0 = 60.0                     # authored crank angle, degrees


def fourbar(theta_deg):
    """Closed form: joint points A (crank tip) and B (coupler/rocker), open (upper) branch."""
    th = math.radians(theta_deg)
    Ax, Ay = a * math.cos(th), a * math.sin(th)
    dx, dy = d - Ax, -Ay
    L = math.hypot(dx, dy)
    k = (b * b - c * c + L * L) / (2 * L)
    h = math.sqrt(b * b - k * k)
    Bx, By = Ax + (k * dx - h * dy) / L, Ay + (k * dy + h * dx) / L
    if By < 0:                                             # keep the upper (open) branch
        Bx, By = Ax + (k * dx + h * dy) / L, Ay + (k * dy - h * dx) / L
    return (Ax, Ay), (Bx, By)


def rocker_deg(theta_deg):
    _, (Bx, By) = fourbar(theta_deg)
    return math.degrees(math.atan2(By, Bx - d))


def _bar(name, L):
    return ir.part(name, ir.sketch("s", rects=[(L + 6.0, 6.0, L / 2, 0.0)]), ir.pad("p", "s", 3.0))


def _place(ang_deg, x, y, z):
    t = math.radians(ang_deg)
    return [math.cos(t), -math.sin(t), 0, x, math.sin(t), math.cos(t), 0, y, 0, 0, 1, z]


def fourbar_asm():
    (Ax, Ay), (Bx, By) = fourbar(TH0)
    phi = math.degrees(math.atan2(By - Ay, Bx - Ax))
    psi = math.degrees(math.atan2(By, Bx - d))
    Z = [0, 0, 1]
    occs = [A.occurrence("o1", "ground", _bar("ground", d), _place(0, 0, 0, 0)),
            A.occurrence("o2", "crank", _bar("crank", a), _place(TH0, 0, 0, 3)),
            A.occurrence("o3", "coupler", _bar("coupler", b), _place(phi, Ax, Ay, 6)),
            A.occurrence("o4", "rocker", _bar("rocker", c), _place(psi, d, 0, 9))]
    mates = [A.mate("crank", "revolute", "ground", "crank", axis={"origin": [0, 0, 0], "dir": Z}),
             A.mate("knee", "revolute", "crank", "coupler", axis={"origin": [Ax, Ay, 0], "dir": Z}),
             A.mate("elbow", "revolute", "coupler", "rocker", axis={"origin": [Bx, By, 0], "dir": Z})]
    closures = [A.closure("rocker_pivot", "revolute", "rocker", "ground", axis={"origin": [d, 0, 0], "dir": Z})]
    return A.assembly("fourbar", occs, mates=mates, closures=closures)


def _angle(T):
    return math.degrees(math.atan2(T[1, 0], T[0, 0]))


def _wrap(x):
    return (x + 180.0) % 360.0 - 180.0


# --- IR ----------------------------------------------------------------------------------------
def test_fourbar_is_wellformed_with_one_dof():
    asm = fourbar_asm()
    assert A.mate_tree_problems(asm) == []          # the mates are still a TREE (cadgen-safe)
    assert A.closure_problems(asm) == []
    mob = A.mobility(asm)
    assert mob["mobility"] == 1 and mob["planar_closures"] == ["rocker_pivot"]


def test_closure_rules():
    asm = fourbar_asm()
    asm["closures"].append(A.closure("self", "spherical", "rocker", "rocker", axis={"origin": [0, 0, 0]}))
    asm["occurrences"].append(A.occurrence("o9", "loose"))
    asm["closures"].append(A.closure("apart", "spherical", "rocker", "loose", axis={"origin": [0, 0, 0]}))
    probs = " | ".join(A.closure_problems(asm))
    assert "on itself" in probs and "separate trees" in probs
    with pytest.raises(ValueError):
        A.closure("x", "magnetic", "a", "b")


def test_spatial_count_would_overconstrain_a_planar_loop():
    asm = fourbar_asm()
    asm["closures"][0]["axis"]["dir"] = [1, 0, 0]    # not parallel to the loop's revolutes
    assert A.mobility(asm)["mobility"] == 3 - 5


# --- pose solver -------------------------------------------------------------------------------
def test_authored_pose_is_closed():
    asm = fourbar_asm()
    assert np.linalg.norm(K.closure_residual(asm, {})) < 1e-9


@pytest.mark.parametrize("dtheta", [15.0, 45.0, -40.0, 120.0])
def test_solver_matches_closed_form(dtheta):
    asm = fourbar_asm()
    q, T = K.solve(asm, {"crank": dtheta}, steps=max(6, int(abs(dtheta) / 5)))
    assert np.linalg.norm(K.closure_residual(asm, q)) < 1e-5
    assert abs(_wrap(_angle(T["o4"]) - rocker_deg(TH0 + dtheta))) < 1e-3


def test_crank_rotates_fully_on_one_branch():
    asm = fourbar_asm()
    q, T = K.solve(asm, {"crank": 350.0}, steps=70)
    assert abs(_wrap(_angle(T["o4"]) - rocker_deg(TH0 + 350.0))) < 1e-3


# --- MJCF --------------------------------------------------------------------------------------
def test_mjcf_fourbar_tracks_closed_form(tmp_path):
    mujoco = pytest.importorskip("mujoco")
    import mjcf_emit as M
    asm = fourbar_asm()
    xml = M.emit(asm, str(tmp_path), {"collision": {k: "none" for k in ("ground", "crank", "coupler", "rocker")},
                                      "actuators": [{"mate": "crank", "kind": "position", "kp": 0.05, "kv": 0.001}]})
    assert "<connect" in xml and xml.count("<connect") == 1          # planar loop -> one connect
    m = mujoco.MjModel.from_xml_string(xml)
    dat = mujoco.MjData(m)
    for target in (20.0, 60.0):
        dat.ctrl[0] = math.radians(target)      # actuator setpoints are radians (compiler angle= only parses XML)
        for _ in range(4000):
            mujoco.mj_step(m, dat)
        rocker = m.body("rocker").id
        R = dat.xmat[rocker].reshape(3, 3)
        dpsi = math.degrees(math.atan2(R[1, 0], R[0, 0]))    # body frames are world-aligned AT THE
        assert abs(_wrap(dpsi - (rocker_deg(TH0 + target) - rocker_deg(TH0)))) < 0.5   # authored pose
        # the loop is closed: the rocker's copy of O4 sits on the ground's O4
        (_, _), (Bx, By) = fourbar(TH0)                 # rocker body origin = its joint point B (authored)
        anchor_world = dat.xpos[rocker] + R @ ((np.array([d, 0, 0]) - np.array([Bx, By, 0])) * 1e-3)
        assert np.linalg.norm(anchor_world - np.array([d, 0, 0]) * 1e-3) < 2e-4   # < 0.2 mm


def test_mjcf_rejects_a_closure_inside_one_rigid_group(tmp_path):
    import mjcf_emit as M
    asm = fourbar_asm()
    asm["mates"][2]["kind"] = "fastened"                              # rocker welded to coupler...
    asm["mates"][2]["axis"] = None
    asm["closures"][0].update(a="rocker", b="coupler")                # ...then "closed" to it
    with pytest.raises(ValueError):
        M.emit(asm, str(tmp_path))
