#!/usr/bin/env python3
"""Score inferred design intent against the designer's own semantic PMI.

For each NIST part, recover the tree from the "AP203 geometry only" file (the one the corpus
evaluation uses), read the semantic PMI from the part's AP242 file, infer intent with
intent.describe(), carry the recovered holes into the original frame with the iou_check
registration, and compare. The two files are DIFFERENT EXPORTS of the same design — CTC-01's AP242
file has 117 faces to the geometry file's 139 and 2,000 mm^3 more volume, FTC-11's splits a
six-face ring into 42 faces — so recognising from the AP242 file would change the verdict. They
do share a coordinate frame (identical bounding boxes), which is what lets the PMI score a tree
recovered from the other file.

  holes     each hole a diameter callout references, matched by a recovered hole of the same
            diameter on the same axis line  ->  recall
  sizes     for matched holes, does the inferred NOMINAL agree with the callout's nominal value
            (within 0.01 mm)? e.g. geometry 3.969 mm -> inferred 5/32" vs drawing .156"
  units     inferred inch/metric vs the same grid test applied to the PMI's own nominal values
  grouping  pairwise precision/recall of the inferred pattern partition against the designer's
            callout partition (holes in one callout = one group), over matched holes

A diameter callout whose value is far from its holes' size (FTC-09's 8" dimension on two 8 mm
holes) is a bolt-circle diameter: its holes count as a group, not as a size.

Run from the REPO ROOT:  python3 paper/figures/intent_eval.py
Writes: paper/figures/intent_results.json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.expanduser("~/Downloads/NIST-PMI-STEP-Files")
GEOM = os.path.join(ROOT, "AP203 geometry only")
PARTS = [("nist_ctc_01_asme1_rd.stp", "nist_ctc_01_asme1_ap242-e1.stp"),
         ("nist_ctc_02_asme1_rc.stp", "nist_ctc_02_asme1_ap242-e2.stp"),
         ("nist_ctc_03_asme1_rc.stp", "nist_ctc_03_asme1_ap242-e2.stp"),
         ("nist_ctc_04_asme1_rd.stp", "nist_ctc_04_asme1_ap242-e1.stp"),
         ("nist_ctc_05_asme1_rd.stp", "nist_ctc_05_asme1_ap242-e1.stp"),
         ("nist_ftc_06_asme1_rd.stp", "nist_ftc_06_asme1_ap242-e2.stp"),
         ("nist_ftc_07_asme1_rd.stp", "nist_ftc_07_asme1_ap242-e2.stp"),
         ("nist_ftc_08_asme1_rc.stp", "nist_ftc_08_asme1_ap242-e2.stp"),
         ("nist_ftc_09_asme1_rd.stp", "nist_ftc_09_asme1_ap242-e1.stp"),
         ("nist_ftc_10_asme1_rb.stp", "nist_ftc_10_asme1_ap242-e2.stp"),
         ("nist_ftc_11_asme1_rb.stp", "nist_ftc_11_asme1_ap242-e2.stp")]
OUT = os.path.join("paper", "figures", "intent_results.json")


def score(geom_path, pmi_path):
    import math
    sys.path.insert(0, os.getcwd())
    sys.path.insert(0, os.path.join(os.getcwd(), "paper", "figures"))
    import b3d_emit
    import intent
    import iou_check
    import step_recognize as sr
    from build123d import import_step
    from pmi import hole_callouts, read_pmi

    spec, rep = __import__("_recovered").load(geom_path)
    rec, _ = b3d_emit.emit(spec)
    orig = import_step(geom_path)
    bb = iou_check.solid_part(orig).bounding_box()
    desc = intent.describe(spec, extents=(bb.size.X, bb.size.Y, bb.size.Z))
    _, to_pt, to_dir = sr.input_frame(orig, rep)       # exact: the recogniser's own transform

    pmi = read_pmi(pmi_path)
    callouts = hole_callouts(pmi)
    # distinct PMI holes, each tagged with the callout(s) that reference it
    truth = []
    for ci, c in enumerate(callouts):
        for h in c["holes"]:
            for t in truth:
                if abs(t["d"] - h.diameter) < 0.02 and iou_check_line(t, h) < 0.1:
                    t["callouts"].append(ci)
                    break
            else:
                truth.append({"d": h.diameter, "p": h.point, "a": h.axis, "callouts": [ci]})

    # recovered holes in the original frame, tagged with their inferred pattern
    pat_of = {}
    for pi, p in enumerate(desc["patterns"]):
        for h in p["holes"]:
            pat_of[id(h)] = pi
    recs = []
    for h in desc["holes"]:
        recs.append({"d": h.diameter, "p": to_pt(h.center), "a": to_dir(h.axis),
                     "pattern": pat_of.get(id(h)), "nominal": intent.nominal_value(h.diameter, desc["units"])})

    def line_dist(t, r):
        a = t["a"]
        d = [r["p"][i] - t["p"][i] for i in range(3)]
        s = sum(d[i] * a[i] for i in range(3))
        par = abs(abs(sum(a[i] * r["a"][i] for i in range(3))) - 1) < 1e-4
        return math.sqrt(max(sum(v * v for v in d) - s * s, 0.0)) if par else 1e9

    matches = []
    for ti, t in enumerate(truth):
        best = min(((line_dist(t, r), ri) for ri, r in enumerate(recs)
                    if abs(r["d"] - t["d"]) < 0.02), default=(1e9, None))
        if best[0] < 0.1:
            matches.append((ti, best[1]))

    size_ok = size_n = 0
    for ti, ri in matches:
        for ci in truth[ti]["callouts"]:
            c = callouts[ci]
            if c["bolt_circle"]:
                continue
            size_n += 1
            nv = recs[ri]["nominal"][1]
            size_ok += nv is not None and abs(nv - c["nominal"]) <= 0.01

    # pairwise grouping agreement over matched holes
    tp = fp = fn = 0
    for x in range(len(matches)):
        for y in range(x + 1, len(matches)):
            (tx, rx), (ty, ry) = matches[x], matches[y]
            same_truth = bool(set(truth[tx]["callouts"]) & set(truth[ty]["callouts"]))
            px, py = recs[rx]["pattern"], recs[ry]["pattern"]
            same_ours = px is not None and px == py
            tp += same_truth and same_ours
            fp += same_ours and not same_truth
            fn += same_truth and not same_ours

    pmi_vals = [d["value"] for d in pmi["dimensions"] if d["value"] and d["value"] > 0]
    truth_units, _ = intent.infer_units(pmi_vals)
    return {
        "part": os.path.basename(geom_path), "pmi_file": os.path.basename(pmi_path), "verified": rep["verified"], "dvol_pct": rep.get("dvol_pct"),
        "pmi": {"dimensions": len(pmi["dimensions"]), "tolerances": len(pmi["tolerances"]),
                "datums": pmi["datums"], "hole_callouts": len(callouts), "holes": len(truth)},
        "recovered_holes": len(recs), "counterbores": len(desc["counterbores"]),
        "hole_recall": [len(matches), len(truth)],
        "size_agreement": [size_ok, size_n],
        "units": {"inferred": desc["units"], "pmi": truth_units, "score": desc["unit_score"]},
        "grouping": {"tp": tp, "fp": fp, "fn": fn},
        "patterns": [{"type": p["type"], "d": round(p["diameter"], 3), "n": len(p["holes"])}
                     for p in desc["patterns"]],
        "callouts": [{"nominal": round(c["nominal"], 3), "n": c["count"], "bolt_circle": c["bolt_circle"]}
                     for c in callouts],
        "nominals": {str(k): v for k, v in desc["nominals"].items()},
    }


def iou_check_line(t, h):
    import math
    a = t["a"]
    d = [h.point[i] - t["p"][i] for i in range(3)]
    s = sum(d[i] * a[i] for i in range(3))
    return math.sqrt(max(sum(v * v for v in d) - s * s, 0.0))


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--worker":
        print("@@JSON@@" + json.dumps(score(sys.argv[2], sys.argv[3])))
        return
    rows = []
    for fn, pmi_fn in PARTS:
        p = subprocess.run([sys.executable, os.path.abspath(__file__), "--worker",
                            os.path.join(GEOM, fn), os.path.join(ROOT, pmi_fn)],
                           capture_output=True, text=True, timeout=2400)
        got = [l for l in p.stdout.splitlines() if l.startswith("@@JSON@@")]
        row = json.loads(got[-1][8:]) if got else {"part": fn, "error": (p.stderr.strip().splitlines() or ["?"])[-1][:200]}
        rows.append(row)
        if "error" in row:
            print(f"{fn}: ERROR {row['error']}")
            continue
        g = row["grouping"]
        prec = g["tp"] / (g["tp"] + g["fp"]) if g["tp"] + g["fp"] else float("nan")
        rec_ = g["tp"] / (g["tp"] + g["fn"]) if g["tp"] + g["fn"] else float("nan")
        print(f"{fn[5:11]}  verified={row['verified']}  PMI: {row['pmi']['dimensions']} dims, "
              f"{row['pmi']['hole_callouts']} hole callouts, {row['pmi']['holes']} holes, datums {row['pmi']['datums']}")
        print(f"   holes recovered {row['hole_recall'][0]}/{row['hole_recall'][1]}   "
              f"nominal size agrees {row['size_agreement'][0]}/{row['size_agreement'][1]}   "
              f"units {row['units']['inferred']} (PMI: {row['units']['pmi']})   "
              f"grouping P={prec:.2f} R={rec_:.2f} (tp {g['tp']} fp {g['fp']} fn {g['fn']})")
    json.dump({"results": rows}, open(OUT, "w"), indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
