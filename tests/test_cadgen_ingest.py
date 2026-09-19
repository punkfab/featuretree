"""Tests for cadgen_ingest — against REAL cadgen output (tests/fixtures/cadgen) plus a synthetic
end-to-end STEP+sidecar. Nothing here touches the existing single-part flows."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import assembly_ir as A
import cadgen_ingest as CI

FIX = Path(__file__).resolve().parent / "fixtures" / "cadgen"
SIDECAR = FIX / "planetary_gear_assembly.step.json"
PACKAGE_JSON = FIX / "planetary_assembly.json"


# --- the real sidecar --------------------------------------------------------------------------
def test_real_sidecar_parses_full_kinematics():
    s = CI.read_sidecar(SIDECAR)
    assert s["schema_version"] == 9
    assert len(s["mates"]) == 8
    kinds = sorted(m["kind"] for m in s["mates"])
    assert kinds == ["fastened"] * 3 + ["revolute"] * 5
    assert [c["name"] for c in s["couplings"]] == ["drive"]
    assert set(s["poses"]) == {"half_cycle", "quarter_cycle"}


def test_real_sidecar_mate_fields():
    s = CI.read_sidecar(SIDECAR)
    by = {m["name"]: m for m in s["mates"]}
    sun = by["sun"]
    assert sun["parent"] == "ring_gear_60_internal_teeth" and sun["parent_id"] == "o1.2"   # '#' stripped
    assert sun["child"] == "sun_gear_24_teeth" and sun["child_id"] == "o1.3"
    assert sun["axis"] == {"origin": [0.0, 0.0, 0.0], "dir": [0.0, 0.0, 1.0]}
    assert sun["limits"] == {"value": [-1260.0, 1260.0]}
    pin = by["pin1"]
    assert pin["kind"] == "fastened" and pin["axis"] is None and pin["limits"] == {}
    drive = s["couplings"][0]
    assert drive["gears"]["sun"] == 1.0 and abs(drive["gears"]["carrier"] - 24 / 84) < 1e-9
    assert drive["limits"] == [0.0, 1260.0]


def test_unknown_mate_kind_is_an_error(tmp_path):
    bad = {"schemaVersion": 9, "kinematics": {"mates": [
        {"name": "x", "kind": "magnetic", "parent": "#a", "child": "#b", "axis": {}, "limits": {}}]}}
    p = tmp_path / "bad.step.json"
    p.write_text(json.dumps(bad))
    try:
        CI.read_sidecar(p)
    except ValueError as e:
        assert "magnetic" in str(e)
    else:
        raise AssertionError("an unknown mate kind must not be silently accepted")


# --- the real package tree + the join, on real data ----------------------------------------------
def _planetary_package(tmp_path):
    pkg = tmp_path / "planetary"
    pkg.mkdir()
    (pkg / "assembly.json").write_text(PACKAGE_JSON.read_text())
    return pkg


def test_real_package_occurrence_tree(tmp_path):
    occs, root = CI.read_package(_planetary_package(tmp_path))
    assert root == "simplified_planetary_gear_assembly"
    assert [o["id"] for o in occs] == [f"o1.{i}" for i in range(1, 10)]
    assert occs[0]["label"] == "carrier_plate" and len(occs[0]["transform"]) == 12
    assert all(o["geometry"] == "surface-only" for o in occs)     # docs hero ships no .brep -> reported


def test_real_sidecar_joins_real_tree_by_id_and_label_agrees(tmp_path):
    """Every mate's parentId/childId names a real occurrence AND the sidecar '#label' matches the
    tree's part name — the cross-check, on genuine cadgen output."""
    occs, _ = CI.read_package(_planetary_package(tmp_path))
    side = CI.read_sidecar(SIDECAR)
    mates, problems = CI.join_mates(occs, side["mates"])
    assert problems == [], problems
    assert len(mates) == 8
    by_id = {o["id"]: o["label"] for o in occs}
    for m in mates:
        assert by_id[m["parent_id"]] == m["parent"] and by_id[m["child_id"]] == m["child"]


def test_join_reports_label_disagreement_and_missing():
    occs = [{"id": "o1.1", "label": "plate"}, {"id": "o1.2", "label": "peg"}]
    mates = [A.mate("m1", "fastened", "plate", "bolt", parent_id="o1.1", child_id="o1.2"),
             A.mate("m2", "revolute", "plate", "ghost", parent_id="o1.1", child_id="o1.9")]
    _, problems = CI.join_mates(occs, mates)
    assert any("says 'bolt'" in p for p in problems)             # id o1.2 is 'peg', sidecar says 'bolt'
    assert any("'ghost'" in p and "not an occurrence" in p for p in problems)


def test_package_ingest_end_to_end_structure_only(tmp_path):
    pkg = _planetary_package(tmp_path)
    (tmp_path / "planetary.step.json").write_text(SIDECAR.read_text())
    asm, rep = CI.ingest(package_dir=pkg, sidecar_path=tmp_path / "planetary.step.json")
    assert asm["kind"] == "assembly" and rep["n_occurrences"] == 9 and rep["n_mates"] == 8
    assert rep["ok"] and rep["mate_tree_problems"] == []
    assert rep["parts_recognized"] == 0                          # no geometry in a surface-only package
    assert asm["provenance"]["tool"].startswith("cadgen")


# --- mate-tree rules ------------------------------------------------------------------------------
def test_mate_tree_rules():
    good = A.assembly("a", [], mates=[A.mate("m", "fastened", "x", "y")])
    assert A.mate_tree_problems(good) == []
    two_parents = A.assembly("b", [], mates=[A.mate("m1", "fastened", "x", "y"),
                                             A.mate("m2", "revolute", "z", "y")])
    assert any("more than one parent" in p for p in A.mate_tree_problems(two_parents))
    cyc = A.assembly("c", [], mates=[A.mate("m1", "revolute", "x", "y"), A.mate("m2", "revolute", "y", "x")])
    assert any("cycle" in p for p in A.mate_tree_problems(cyc))


# --- the geometry path, end to end (labels survive STEP, parts get editable trees) ----------------
def test_step_assembly_read_preserves_labels_and_order(tmp_path):
    from build123d import Box, Compound, Cylinder, Pos, export_step
    a = Box(20, 20, 5); a.label = "base_plate"
    b = Pos(0, 0, 10) * Cylinder(4, 12); b.label = "peg_post"
    asm = Compound(children=[a, b]); asm.label = "t"
    export_step(asm, str(tmp_path / "t.step"))
    occs, root = CI.read_step_assembly(tmp_path / "t.step")
    assert root == "t"
    assert [(o["id"], o["label"], o["n_solids"]) for o in occs] == [("o1.1", "base_plate", 1), ("o1.2", "peg_post", 1)]


def test_full_ingest_gives_editable_tree_per_part_and_keeps_mates(tmp_path):
    step = CI._make_fixture(tmp_path)
    asm, rep = CI.ingest(step)
    assert rep["ok"], rep
    assert [o["label"] for o in asm["occurrences"]] == ["base_plate", "peg"]
    assert rep["parts_verified"] == 2, rep["part_reports"]
    assert asm["parts"]["base_plate"]["features"]                 # a real named feature tree
    m = asm["mates"][0]
    assert (m["kind"], m["parent_id"], m["child_id"]) == ("revolute", "o1.1", "o1.2")
    assert asm["poses"] == {"quarter": {"peg_spin": 90.0}}
    # parts are recognized in their OWN frame; the occurrence carries the placement back to world
    peg = next(o for o in asm["occurrences"] if o["label"] == "peg")
    assert abs(peg["transform"][11] - 15.0) < 1e-3                # Pos(0,0,15)*Cylinder -> centre z=15
    assert all(r["placement_verified"] for r in rep["part_reports"].values()), rep["part_reports"]
    # the assembly IR is plain JSON (crosses into FreeCAD's Python like the part IR does)
    json.dumps(asm)


def test_single_solid_step_is_one_occurrence(tmp_path):
    from build123d import Box, export_step
    b = Box(10, 10, 10); b.label = "lone"
    export_step(b, str(tmp_path / "lone.step"))
    occs, _ = CI.read_step_assembly(tmp_path / "lone.step")
    assert len(occs) == 1 and occs[0]["id"] == "o1" and occs[0]["n_solids"] == 1
