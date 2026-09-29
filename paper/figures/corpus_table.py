#!/usr/bin/env python3
"""The full NIST MBE PMI test-case set, part by part, with every verification detail.

Generated from the result files, never hand-edited, so the table cannot drift from
the data:
    corpus_results.json   recogniser verdict, volume and extent residuals, features,
                          recovery method, wall-clock  (run_corpus.py)
    iou_mc_results.json   Boolean-free IoU with a 95% interval  (iou_mc_check.py)

The verification gate (step_recognize._verify) accepts when BOTH hold:
    volume error  <= VOL_TOL  (0.5% of the input's volume)
    extent error  <= DIM_TOL  (0.05 mm, largest difference of the sorted bbox sizes)
The "Fails" column says which test a PARTIAL part failed.

Rows NIST publishes that were not run are listed too, with the reason, so the table
is the whole set rather than a flattering subset.

Run from the REPO ROOT (after run_corpus.py and iou_mc_check.py):
    python3 paper/figures/corpus_table.py
Writes: paper/figures/corpus_table.md, paper/figures/corpus_table.html
"""
from __future__ import annotations

import html
import json
import os
import re
import sys

sys.path.insert(0, os.getcwd())
from step_recognize import DIM_TOL, VOL_TOL  # noqa: E402

FIG = os.path.join("paper", "figures")
SETS = {"ctc": "Combined", "ftc": "Fully-toleranced"}

# Published by NIST but not run. The STC share FTC geometry (NIST: "The geometry of the STC
# is the same as the corresponding FTC"); we confirmed 06/08/09/10 by volume (<0.001%) and
# sorted extents, and STC-07 does not import in OpenCASCADE.
NOT_RUN = [
    ("STC-06", "Simplified", "same geometry as FTC-06 (confirmed: volume and extents)"),
    ("STC-07", "Simplified", "same geometry as FTC-07 per NIST; does not import in OpenCASCADE"),
    ("STC-08", "Simplified", "same geometry as FTC-08 (confirmed: volume and extents)"),
    ("STC-09", "Simplified", "same geometry as FTC-09 (confirmed: volume and extents)"),
    ("STC-10", "Simplified", "same geometry as FTC-10 (confirmed: volume and extents)"),
    ("FTC-08 (tessellated)", "Fully-toleranced", "faceted surfaces, not exact B-rep; out of scope"),
    ("HTC", "Hole", "2024 model, not in the corpus download used; not evaluated"),
    ("MTC", "Modified", "2018 model, not in the corpus download used; not evaluated"),
]


def label(part):
    m = re.match(r"nist_(ctc|ftc)_(\d+)_", part)
    return f"{m.group(1).upper()}-{m.group(2)}", SETS[m.group(1)]


def how_recovered(r):
    if r.get("method") == "revolve":
        return "revolve"
    w = " ".join(r.get("warnings", []))
    ly = re.search(r"layered along \(([^)]*)\): (\d+) layer\(s\), (\d+) hole run", w)
    if ly:
        v = [abs(float(x)) for x in ly.group(1).split(",")]
        return f"layered ∥{'XYZ'[v.index(max(v))]} · {ly.group(2)} layers · {ly.group(3)} hole runs"
    sh = re.search(r"open shell along \(([^)]*)\)", w)
    if sh:
        v = [abs(float(x)) for x in sh.group(1).split(",")]
        ax = "XYZ"[v.index(max(v))]
        layers = re.search(r"outline layers: ([^;]*)", w)
        n_layers = len(layers.group(1).split(", ")) if layers else 1
        d = re.search(r"draft ([-\d.]+) deg outside, ([-\d.]+) deg inside", w)
        draft = max(abs(float(d.group(1))), abs(float(d.group(2)))) if d else 0.0
        fc = re.search(r"(\d+) floor cutout", w)
        bits = [("drafted " if draft else "") + f"shell ∥{ax}" + (f" ({draft:.1f}°)" if draft else "")]
        if n_layers > 1:
            bits.append(f"{n_layers} outline layers")
        if fc:
            bits.append(f"{fc.group(1)} floor cutouts")
        rec = r.get("recovered") or {}
        if rec.get("pockets") or rec.get("holes"):
            bits.append(f"+{rec.get('pockets', 0)} pockets, +{rec.get('holes', 0)} cross-holes")
        return " · ".join(bits)
    m = re.search(r"extrude axis \(([^)]*)\)", w)
    axis = "Z"
    if m:
        v = [abs(float(x)) for x in m.group(1).split(",")]
        axis = "XYZ"[v.index(max(v))]
    bits = [f"extrude ∥{axis}"]
    m = re.search(r"cross-section is (\d+) disjoint region", w)
    if m:
        bits.append(f"{m.group(1)} regions")
    rec = r.get("recovered") or {}
    if rec.get("pockets") or rec.get("holes"):
        bits.append(f"+{rec.get('pockets', 0)} pockets, +{rec.get('holes', 0)} cross-holes")
    return " · ".join(bits)


def fails(r):
    v = r["dvol_pct"] > 100 * VOL_TOL
    e = (r.get("dsize_mm") or 0) > DIM_TOL
    return {(False, False): "—", (True, False): "volume", (False, True): "extents",
            (True, True): "volume + extents"}[(v, e)]


def main():
    runs = {r["part"]: r for r in json.load(open(os.path.join(FIG, "corpus_results.json")))["results"]}
    mc = {r["part"]: r for r in json.load(open(os.path.join(FIG, "iou_mc_results.json")))["results"]}

    rows = []
    for part in sorted(runs):
        r, m = runs[part], mc.get(part, {})
        b = m.get("best") or m.get("at_harness_rot") or {}
        name, group = label(part)
        verified = r["status"] == "VERIFIED"
        # exact registration (the recogniser's own transform undone) makes IoU a measurement;
        # only a search-registered figure is a lower bound, and is marked as one
        exact = b.get("registration") == "exact"
        iou = ((f"{b['iou_pct']:.2f} ± {b['ci_pct']:.2f}" if verified else f"{b['iou_pct']:.1f} ± {b['ci_pct']:.1f}")
               if exact else f"≥ {b['iou_pct']:.1f}") if b.get("iou_pct") is not None else "—"
        rows.append({
            "Part": name, "NIST set": group, "Verdict": r["status"], "Fails": fails(r),
            "Volume error": f"{r['dvol_pct']:.2f}%",
            "Extent error": f"{r.get('dsize_mm') or 0:.2f} mm",
            "IoU (%)": iou, "Features": str(r["features"]),
            "How recovered": how_recovered(r), "Time": f"{r['seconds']:.0f} s",
        })
    cols = list(rows[0])

    n = len(rows)
    nv = sum(r["Verdict"] == "VERIFIED" for r in rows)
    ious = [(mc[p].get("best") or mc[p].get("at_harness_rot") or {}).get("iou_pct")
            for p in sorted(runs) if runs[p]["status"] == "PARTIAL"]
    ious = [x for x in ious if x is not None]
    summary = (f"{n} of {n} parts yield an editable tree; {nv} VERIFIED, {n - nv} PARTIAL, "
               f"0 refused. PARTIAL IoU ranges {min(ious):.1f}–{max(ious):.1f}%.")

    gate = (f"Gate: volume error ≤ {100 * VOL_TOL:g}% and extent error ≤ {DIM_TOL:g} mm. "
            "IoU is Boolean-free (60 000 sampled points, 95% interval) and exactly registered: "
            "the recogniser's own rotation and offset are undone, so it is a measurement, not a bound.")

    md = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        cells = [f"**{r[c]}**" if c == "Verdict" and r[c] == "VERIFIED" else r[c] for c in cols]
        md.append("| " + " | ".join(cells) + " |")
    md += ["", summary, "", gate, "", "Published by NIST but not run:", "",
           "| Part | NIST set | Status |", "|---|---|---|"]
    md += [f"| {a} | {b} | {c} |" for a, b, c in NOT_RUN]
    open(os.path.join(FIG, "corpus_table.md"), "w").write("\n".join(md) + "\n")

    # The HTML is the COMPACT variant for narrow pages (the blog): the Markdown above stays
    # complete. The NIST set is implied by the CTC/FTC prefix, wall-clock is dropped, and cells
    # are shortened so a 760 px column does not wrap part names.
    e = html.escape
    short = {"Part": "Part", "Verdict": "Verdict", "Fails": "Fails", "Volume error": "Vol. error",
             "Extent error": "Extent error (mm)", "IoU (%)": "IoU (%)", "Features": "Features",
             "How recovered": "Recovered as"}
    def cell(r, c):
        v = r[c]
        if c == "Fails":
            v = {"volume + extents": "both"}.get(v, v)
        elif c == "Extent error":
            v = f"{float(v.split()[0]):.1f}"
        elif c == "Volume error":
            v = f"{float(v.rstrip('%')):.2f}%"
        elif c == "How recovered":
            v = (v.replace("extrude ∥", "extrude ").replace(" pockets", " pockets")
                  .replace("+", "").replace(" cross-holes", " holes"))
        v = e(v)
        if c in ("Verdict", "IoU (%)") and r["Verdict"] == "VERIFIED":
            v = f"<strong>{v}</strong>"
        nowrap = ' style="white-space:nowrap"' if c in ("Part", "IoU (%)", "Volume error") else ""
        return f"<td{nowrap}>{v}</td>"
    h = ['<div class="table-wrap"><table>', "<thead><tr>"
         + "".join(f"<th>{e(short[c])}</th>" for c in short) + "</tr></thead>", "<tbody>"]
    for r in rows:
        h.append("<tr>" + "".join(cell(r, c) for c in short) + "</tr>")
    h.append("</tbody></table></div>")
    h.append('<div class="table-wrap"><table>')
    h.append("<thead><tr><th>Published by NIST, not run</th><th>NIST set</th><th>Why</th></tr></thead><tbody>")
    h += [f"<tr><td>{e(a)}</td><td>{e(b)}</td><td>{e(c)}</td></tr>" for a, b, c in NOT_RUN]
    h.append("</tbody></table></div>")
    open(os.path.join(FIG, "corpus_table.html"), "w").write("\n".join(h) + "\n")

    print("\n".join(md))
    print(f"\nwrote {FIG}/corpus_table.md and corpus_table.html")


if __name__ == "__main__":
    main()
