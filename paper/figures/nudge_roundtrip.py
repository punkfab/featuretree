#!/usr/bin/env python3
"""nudge_roundtrip.py — a human edit in FreeCAD, read back into the IR, rebuilt by the reference.

The loop the IR exists for: someone changes one dimension in a CAD system's tree; the change is
read back BY FEATURE NAME into the IR; every other backend rebuilds from the IR. For each part,
and for up to N editable features of it (pad / blind pocket / placed cut length, fillet radius,
first circle of a sketch), one at a time on a fresh copy of the emitted .FCStd:

  1. set the dimension to 1.1x in FreeCAD (headless), recompute, save      -> V_fc
  2. read every parameter back and apply it with ir.update_from_params
  3. rebuild the updated IR with build123d                                -> V_ref

and record: whether the edit reached the IR, whether only that parameter changed, and whether
|V_fc - V_ref| / V_ref <= 0.5%. Cached per part in paper/figures/nudge/<part>.json; --fresh reruns.

    python3 paper/figures/nudge_roundtrip.py [--fresh] [-n 6] [part-substring ...]
"""
import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import b3d_emit  # noqa: E402
import gen  # noqa: E402
import ir as IR  # noqa: E402
from runner import run_in_freecad  # noqa: E402

FIG = Path(__file__).resolve().parent
OUT = FIG / "nudge"
SKIP = ("ctc_02", "ctc_04")          # 12- and 2.5-minute FreeCAD builds; one edit each would take hours
TOL = 0.5


def fc_edit(fcstd, edits):
    proc = run_in_freecad(str(ROOT / "fc_read.py"), {"FC_IN": fcstd, "FC_EDIT": json.dumps(edits),
                                                     "FC_LIBDIR": ROOT})
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT:")), None)
    if line is None:
        raise RuntimeError((proc.stdout or "")[-300:] + (proc.stderr or "")[-300:])
    return json.loads(line[len("RESULT:"):])


def editable(spec):
    """(feature, edit key in FreeCAD, IR key, current value) for every dimension FreeCAD can drive."""
    out = []
    for f in spec["features"]:
        k = f["kind"]
        if k == "pad" or (k == "pocket" and f.get("length") is not None):
            out.append((f, "length", "length", f["length"]))
        elif k == "prism_cut":
            out.append((f, "length", "depth", f["depth"]))
        elif k == "fillet":
            out.append((f, "radius", "radius", f["radius"]))
        elif k == "sketch" and f.get("circles"):
            out.append((f, "radius", "circles[0].r", f["circles"][0][2]))
    return out


def ir_value(spec, name, key):
    f = next(x for x in spec["features"] if x["name"] == name)
    return f["circles"][0][2] if key == "circles[0].r" else f[key]


def run(name, spec, fcstd, n):
    v0 = b3d_emit.emit(copy.deepcopy(spec))[1]["volume"]
    cands = editable(spec)
    step = max(1, len(cands) // n)
    rows = []
    for f, fc_key, ir_key, old in cands[::step][:n]:
        new = round(old * 1.1, 4)
        row = {"feature": f["name"], "kind": f["kind"], "param": ir_key, "old": old, "new": new}
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "edit.FCStd"
            shutil.copy(fcstd, work)
            try:
                res = fc_edit(work, {f["name"]: {fc_key: new}})
            except RuntimeError as e:
                rows.append({**row, "outcome": "FreeCAD rebuild failed", "detail": str(e)[-200:]})
                continue
        edited = IR.update_from_params(copy.deepcopy(spec), res["params"])
        got = ir_value(edited, f["name"], ir_key)
        row["read_back"] = got
        others = [(g["name"], k) for g, _, k, was in cands
                  if g["name"] != f["name"] and abs(ir_value(edited, g["name"], k) - was) > 1e-3]
        row["v_fc"] = res["volume"]
        if abs(got - new) > 1e-3:
            rows.append({**row, "outcome": "edit did not reach the IR"})
            continue
        if others:
            rows.append({**row, "outcome": "other parameters changed", "detail": others[:5]})
            continue
        try:
            v_ref = b3d_emit.emit(edited)[1]["volume"]
        except Exception as e:                                       # noqa: BLE001
            rows.append({**row, "outcome": "reference rebuild failed", "detail": str(e)[-200:]})
            continue
        if v_ref <= 0:
            rows.append({**row, "outcome": "reference rebuild failed", "detail": "no solid"})
            continue
        d = 100 * abs(res["volume"] - v_ref) / v_ref
        row.update(v_ref=round(v_ref, 1), dvol_pct=round(d, 4),
                   moved_pct=round(100 * (v_ref - v0) / v0, 4))
        rows.append({**row, "outcome": "agree" if d <= TOL else "volumes differ"})
    return {"part": name, "editable": len(cands), "v0": round(v0, 1), "edits": rows}


def main():
    OUT.mkdir(exist_ok=True)
    a = sys.argv[1:]
    fresh = "--fresh" in a
    n = int(a[a.index("-n") + 1]) if "-n" in a else 6
    pick = [x for i, x in enumerate(a) if not x.startswith("-") and (i == 0 or a[i - 1] != "-n")]
    jobs = []
    for sname, make in (("sample_plate", IR.sample_plate), ("sample_poly", IR.sample_poly)):
        jobs.append((sname, make(), None))
    for p in sorted((FIG / "recovered").glob("*.stp.json")):
        name = p.name.split(".")[0]
        if any(s in name for s in SKIP) or not (FIG / "freecad" / f"{name}.FCStd").exists():
            continue
        jobs.append((name, json.loads(p.read_text())["spec"], FIG / "freecad" / f"{name}.FCStd"))
    for name, spec, fcstd in jobs:
        if pick and not any(k in name for k in pick):
            continue
        cache = OUT / f"{name}.json"
        if cache.exists() and not fresh:
            r = json.loads(cache.read_text())
        else:
            with tempfile.TemporaryDirectory() as td:
                if fcstd is None:
                    fcstd = Path(td) / f"{name}.FCStd"
                    gen.emit(copy.deepcopy(spec), str(fcstd))
                r = run(name, spec, fcstd, n)
            cache.write_text(json.dumps(r, indent=1))
        tally = {}
        for e in r["edits"]:
            tally[e["outcome"]] = tally.get(e["outcome"], 0) + 1
        print(json.dumps({"part": name, "editable": r["editable"], "tried": len(r["edits"]), **tally}), flush=True)


if __name__ == "__main__":
    main()
