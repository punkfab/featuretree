#!/usr/bin/env python3
"""The featuretree results report on the NIST MBE PMI test geometry: scorecard, per-part detail
(time, complexity, accuracy, verdict), and the history of how the numbers got here.

Everything is read from files the harness writes, never typed in:
    corpus_results.json    verdict, gate residuals, timing, input/output complexity (run_corpus.py)
    iou_mc_results.json    Boolean-free IoU, exactly registered                        (iou_mc_check.py)
    intent_results.json    inferred intent vs the designer's semantic PMI              (intent_eval.py)
    git history            the same files at earlier commits, for the "how we got here" table

SCORING. NIST does not define a score for feature recognition -- its test cases exist to check how
CAD translators carry PMI. The scorecard below is OURS, and every criterion is stated so anyone can
recompute it:
    coverage      distinct NIST test geometries attempted (CTC-01..05, FTC-06..11)
    verified      the rebuilt tree matches the input on volume (<= 0.5%), extents (<= 0.05 mm) AND
                  two-sided overlap (Boolean-free IoU >= 99.5%)
    soundness     false accepts: VERIFIED parts whose independent, exactly registered IoU is < 99.5%
    fidelity      exactly registered IoU of every part, verified or not
    intent        holes, nominal sizes and units against the designer's semantic PMI

Run from the REPO ROOT after run_corpus.py, iou_mc_check.py and intent_eval.py:
    python3 paper/figures/results_report.py
Writes: paper/figures/results.md, paper/figures/results.json
"""
from __future__ import annotations

import json
import os
import re
import statistics
import subprocess

FIG = os.path.join("paper", "figures")
IOU_TOL = 99.5

# (commit, label) -- milestones in how the evaluation and the recogniser developed
HISTORY = [
    ("e84737c", "First full run (preprint v1)"),
    ("591c757", "Axis prefilter relaxed, multi-region sections"),
    ("2ef8b6a", "Open shells with draft; exact registration"),
    ("0f5162d", "Shell outline layers, floor cutouts"),
    (None, "Layered 2.5D recognition, two-sided (IoU) gate, crash isolation"),
]


def _load(name, commit=None):
    path = os.path.join(FIG, name)
    if commit is None:
        return json.load(open(path)) if os.path.exists(path) else None
    try:
        out = subprocess.run(["git", "show", f"{commit}:{path}"], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)
    except Exception:
        return None


def _label(part):
    m = re.match(r"nist_(ctc|ftc)_(\d+)_", part)
    return f"{m.group(1).upper()}-{m.group(2)}"


def _iou(mc, part):
    r = (mc or {}).get(part) or {}
    b = r.get("best") or r.get("at_harness_rot") or {}
    return b.get("iou_pct"), b.get("ci_pct"), b.get("registration")


def main():
    runs = {r["part"]: r for r in _load("corpus_results.json")["results"]}
    mc = {r["part"]: r for r in (_load("iou_mc_results.json") or {"results": []})["results"]}
    intent = {r["part"]: r for r in (_load("intent_results.json") or {"results": []})["results"]}

    rows = []
    for part in sorted(runs):
        r = runs[part]
        iou, ci, reg = _iou(mc, part)
        it = intent.get(part, {})
        ok = r.get("status") == "VERIFIED"
        rows.append({
            "part": _label(part), "set": "Combined" if "ctc" in part else "Fully-toleranced",
            "verdict": r.get("status", "ERROR"),
            "vol_err_pct": r.get("dvol_pct"), "extent_err_mm": r.get("dsize_mm"),
            "iou_pct": iou, "iou_ci_pct": ci, "registration": reg,
            "gate_iou_pct": r.get("iou_gate_pct"), "reason": r.get("reason"),
            "input_faces": r.get("input_faces"), "input_face_types": r.get("input_face_types"),
            "operations": r.get("operations"), "features": r.get("features"),
            "feature_kinds": r.get("feature_kinds"), "method": r.get("method"),
            "seconds": r.get("recognise_seconds", r.get("seconds")),
            "holes": it.get("hole_recall"), "sizes": it.get("size_agreement"),
            "units_ok": (it.get("units") or {}).get("inferred") == (it.get("units") or {}).get("pmi")
            if it.get("units") else None,
            "false_accept": bool(ok and iou is not None and iou < IOU_TOL),
        })

    n = len(rows)
    ver = [x for x in rows if x["verdict"] == "VERIFIED"]
    measured = [x["iou_pct"] for x in rows if x["iou_pct"] is not None]
    secs = [x["seconds"] for x in rows if x["seconds"] is not None]
    hr = [x["holes"] for x in rows if x["holes"]]
    sz = [x["sizes"] for x in rows if x["sizes"] and x["sizes"][1]]
    un = [x["units_ok"] for x in rows if x["units_ok"] is not None]
    score = {
        "coverage": f"{n}/11",
        "verified": len(ver), "partial": sum(x["verdict"] == "PARTIAL" for x in rows),
        "errors": sum(x["verdict"] not in ("VERIFIED", "PARTIAL") for x in rows),
        "false_accepts": sum(x["false_accept"] for x in rows),
        "iou_mean": round(statistics.mean(measured), 1) if measured else None,
        "iou_min": round(min(measured), 1) if measured else None,
        "parts_ge_95": sum(v >= 95 for v in measured), "parts_ge_99": sum(v >= 99 for v in measured),
        "within_volume_gate": sum((x["vol_err_pct"] or 99) <= 0.5 for x in rows),
        "within_extent_gate": sum((x["extent_err_mm"] if x["extent_err_mm"] is not None else 99) <= 0.05 for x in rows),
        "seconds_total": round(sum(secs), 1) if secs else None,
        "seconds_median": round(statistics.median(secs), 1) if secs else None,
        "seconds_max": round(max(secs), 1) if secs else None,
        "input_faces_total": sum(x["input_faces"] or 0 for x in rows),
        "operations_total": sum(x["operations"] or 0 for x in rows),
        "intent_holes": [sum(h[0] for h in hr), sum(h[1] for h in hr)],
        "intent_sizes": [sum(s[0] for s in sz), sum(s[1] for s in sz)],
        "intent_units": [sum(un), len(un)],
    }

    history = []
    for commit, label in HISTORY:
        cr = _load("corpus_results.json", commit)
        mr = _load("iou_mc_results.json", commit)
        if cr is None:
            continue
        st = [r.get("status") for r in cr["results"]]
        exact = None
        if mr:
            vals = [(_iou({r["part"]: r for r in mr["results"]}, p) or (None,))[0] for p in (r["part"] for r in cr["results"])]
            regs = [(_iou({r["part"]: r for r in mr["results"]}, r["part"]) or (None, None, None))[2] for r in cr["results"]]
            if vals and all(v is not None for v in vals) and all(g == "exact" for g in regs):
                exact = (round(statistics.mean(vals), 1), round(min(vals), 1))
        history.append({"commit": commit or "HEAD", "label": label,
                        "verified": st.count("VERIFIED"), "partial": st.count("PARTIAL"),
                        "refused_or_error": len(st) - st.count("VERIFIED") - st.count("PARTIAL"),
                        "iou_mean_min": exact})


    L = ["# featuretree on the NIST MBE PMI test geometry", "",
         "## Scorecard", "",
         f"- Coverage: **{score['coverage']}** distinct test geometries (all CTC and FTC cases)",
         f"- VERIFIED: **{score['verified']}/{n}** (volume ≤ 0.5%, extents ≤ 0.05 mm, IoU ≥ {IOU_TOL}%); "
         f"PARTIAL {score['partial']}; errors {score['errors']}",
         f"- False accepts (VERIFIED but independent IoU < {IOU_TOL}%): **{score['false_accepts']}**",
         f"- Exactly registered IoU, all parts: mean {score['iou_mean']}%, min {score['iou_min']}%; "
         f"{score['parts_ge_99']}/{n} at ≥ 99%, {score['parts_ge_95']}/{n} at ≥ 95%",
         f"- Within the volume gate: {score['within_volume_gate']}/{n}; within the extent gate: {score['within_extent_gate']}/{n}",
         f"- Recognition time: total {score['seconds_total']} s, median {score['seconds_median']} s, max {score['seconds_max']} s",
         f"- Complexity: {score['input_faces_total']} input B-rep faces → {score['operations_total']} feature operations",
         f"- Intent vs PMI: holes {score['intent_holes'][0]}/{score['intent_holes'][1]}, nominal sizes "
         f"{score['intent_sizes'][0]}/{score['intent_sizes'][1]}, units {score['intent_units'][0]}/{score['intent_units'][1]}",
         "", "## Per part", "",
         "| Part | Verdict | Vol. err | Extent err (mm) | IoU (%) | Input faces | Operations | Time (s) | Holes vs PMI | Sizes | Units |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in rows:
        f = lambda v, d=2: "—" if v is None else f"{v:.{d}f}"
        L.append(f"| {x['part']} | {x['verdict']} | {f(x['vol_err_pct'])}% | {f(x['extent_err_mm'])} | "
                 f"{f(x['iou_pct'])} ± {f(x['iou_ci_pct'])} | {x['input_faces'] or '—'} | {x['operations'] or '—'} | "
                 f"{f(x['seconds'], 1)} | {'/'.join(map(str, x['holes'])) if x['holes'] else '—'} | "
                 f"{'/'.join(map(str, x['sizes'])) if x['sizes'] and x['sizes'][1] else '—'} | "
                 f"{'✓' if x['units_ok'] else ('✗' if x['units_ok'] is False else '—')} |")
    def why(x):
        if x["verdict"] == "ERROR":
            return x["reason"] or "recognition crashed"
        w = []
        if x["vol_err_pct"] is not None and x["vol_err_pct"] > 0.5:
            w.append(f"volume off {x['vol_err_pct']:.2f}%")
        if x["extent_err_mm"] is not None and x["extent_err_mm"] > 0.05:
            w.append(f"extents off {x['extent_err_mm']:.2f} mm")
        if x["iou_pct"] is not None and x["iou_pct"] < IOU_TOL:
            w.append(f"overlap {x['iou_pct']:.1f}%")
        return "; ".join(w) or x["reason"] or "?"
    for x in rows:
        x["why_not_verified"] = None if x["verdict"] == "VERIFIED" else why(x)
    json.dump({"score": score, "parts": rows, "history": history}, open(os.path.join(FIG, "results.json"), "w"), indent=2)
    L += ["", "Why not VERIFIED:", ""] + [f"- {x['part']}: {x['why_not_verified']}" for x in rows if x["verdict"] != "VERIFIED"]
    L += ["", "## History", "", "| Stage | VERIFIED | PARTIAL | Refused/error | IoU mean / min (exact) |", "|---|---|---|---|---|"]
    for h in history:
        L.append(f"| {h['label']} (`{h['commit']}`) | {h['verified']} | {h['partial']} | {h['refused_or_error']} | "
                 f"{'%s / %s' % h['iou_mean_min'] if h['iou_mean_min'] else '—'} |")
    open(os.path.join(FIG, "results.md"), "w").write("\n".join(L) + "\n")

    # the same per-part and history tables as an HTML fragment for the blog post
    def cell(v, d=2, suf=""):
        return "—" if v is None else f"{v:.{d}f}{suf}"
    H = ['<div class="table-wrap"><table>',
         "<thead><tr><th>Part</th><th>Faces in</th><th>Ops out</th><th>Time</th><th>Vol. err</th>"
         "<th>Size err</th><th>Overlap (IoU)</th><th>Verdict</th><th>Holes vs PMI</th></tr></thead><tbody>"]
    for x in rows:
        v = x["verdict"]
        H.append(f"<tr><td>{x['part']}</td><td>{x['input_faces'] or '—'}</td><td>{x['operations'] or '—'}</td>"
                 f"<td>{cell(x['seconds'], 0, ' s')}</td><td>{cell(x['vol_err_pct'], 2, '%')}</td>"
                 f"<td>{cell(x['extent_err_mm'], 2, ' mm')}</td><td>{cell(x['iou_pct'], 1, '%')}</td>"
                 f"<td>{'<strong>VERIFIED</strong>' if v == 'VERIFIED' else v.lower()}</td>"
                 f"<td>{'/'.join(map(str, x['holes'])) if x['holes'] else '—'}</td></tr>")
    H.append("</tbody></table></div>")
    H += ['<div class="table-wrap"><table>',
          "<thead><tr><th>Stage</th><th>Verified</th><th>Partial</th><th>Refused / error</th></tr></thead><tbody>"]
    for h in history:
        H.append(f"<tr><td>{h['label']}</td><td>{h['verified']}</td><td>{h['partial']}</td><td>{h['refused_or_error']}</td></tr>")
    H.append("</tbody></table></div>")
    open(os.path.join(FIG, "results_tables.html"), "w").write("\n".join(H) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
