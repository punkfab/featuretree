#!/usr/bin/env python3
"""tables.py — the IR paper's result tables and inline numbers, generated from cached measurements.

Reads paper/figures/freecad/*.json and onshape/*.json (from freecad_corpus.py / onshape_corpus.py),
paper/figures/native_nist.json (native_nist.py) and onshape_coverage.json (recorded Onshape
coverage runs). Writes tables.tex beside this file.

    python3 paper/ir/tables.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIG = HERE.parent / "figures"


def short(part):
    return part.replace("nist_", "").split("_asme")[0].upper().replace("_", "-")


def cell(r):
    if r is None:
        return "not run", "", ""
    if r.get("error"):
        return "build fails", "", ""
    return (r["verdict"].lower() if r["verdict"] == "MISMATCH" else r"\VERIFIED{}",
            f"{r['iou_pct']:.2f}", f"{r['dvol_pct']:.2f}")


def main():
    parts = sorted(p.stem for p in (FIG / "freecad").glob("*.json") if "." not in p.stem)
    fc = {p: json.loads((FIG / "freecad" / f"{p}.json").read_text()) for p in parts}
    osh = {p: json.loads(f.read_text()) for f in (FIG / "onshape").glob("*.json") for p in [f.stem]}
    rec = {p: json.loads((FIG / "recovered" / f"{p}.stp.json").read_text())["spec"] for p in parts}
    out = []
    n_fc = sum(1 for r in fc.values() if r.get("verdict") == "VERIFIED")
    out.append(rf"\newcommand{{\FCverified}}{{{n_fc}}}")
    bad = [f"{short(p)} ({'build fails' if r.get('error') else f'IoU {r['iou_pct']:.1f}\\%'})"
           for p, r in fc.items() if r.get("verdict") != "VERIFIED"]
    lead = "The exception is " if len(bad) == 1 else "The exceptions are "
    out.append(r"\newcommand{\FCnote}{" + (lead + ", ".join(bad) +
               r"; \S\ref{sec:defects} traces the cause.}" if bad else "}"))

    out.append(rf"\newcommand{{\OSrun}}{{{len(osh)}}}")
    out.append(rf"\newcommand{{\OSverified}}{{{sum(1 for r in osh.values() if r.get('verdict') == 'VERIFIED')}}}")
    out += [r"\begin{table}[t]", r"\centering\small", r"\begin{tabular}{@{}lrrlrrlrr@{}}", r"\toprule",
            r"& & & \multicolumn{3}{c}{FreeCAD} & \multicolumn{3}{c}{Onshape} \\",
            r"\cmidrule(lr){4-6}\cmidrule(l){7-9}",
            r"Part & Features & Valid & Verdict & IoU \% & $|\Delta V|$ \% & Verdict & IoU \% & $|\Delta V|$ \% \\",
            r"\midrule"]
    import sys
    sys.path.insert(0, str(HERE.parents[1]))
    import ir as IR
    for p in parts:
        v, i, d = cell(fc[p])
        ov, oi, od = cell(osh.get(p))
        if osh.get(p) and osh[p].get("built") is not None and osh[p]["built"] < osh[p]["features"]:
            ov = f"{osh[p]['built']}/{osh[p]['features']} built"
        valid = "yes" if not IR.validate(rec[p]) else "no"
        out.append(f"{short(p)} & {len(rec[p]['features'])} & {valid} & {v} & {i} & {d} & {ov} & {oi} & {od} \\\\")
    out += [r"\bottomrule", r"\end{tabular}",
            r"\caption{Each recovered NIST feature tree built by FreeCAD and Onshape and gated against the "
            r"build123d reference build of the same IR (\VERIFIED{}: IoU $\geq$ 99.5\% and $|\Delta V| \leq$ 0.5\%). "
            r"``Valid'': passes \code{ir.validate}. Onshape's run is limited by the free plan's daily API quota.}",
            r"\label{tab:corpus}", r"\end{table}", ""]

    cov = json.loads((HERE / "onshape_coverage.json").read_text())
    out += [r"\begin{table}[t]", r"\centering\small", r"\begin{tabular}{@{}llrrr@{}}", r"\toprule",
            r"Part & Feature & Onshape (mm$^3$) & Reference (mm$^3$) & Difference \\", r"\midrule"]
    for part in cov["parts"]:
        for k, (name, o, ref) in enumerate(part["features"]):
            out.append(f"{part['part'] if k == 0 else ''} & \\code{{{name.replace('_', chr(92) + '_')}}} & "
                       f"{o:,.3f} & {ref:,.3f} & {o - ref:+.3f} \\\\")
    out += [r"\bottomrule", r"\end{tabular}",
            r"\caption{Onshape coverage parts: volume after every solid feature against the build123d reference. "
            r"The $-4.175$ offset enters at \code{top\_pk} (a pocket crossing a concave arc edge) and is carried "
            r"through; everything else agrees to three decimals.}",
            r"\label{tab:coverage}", r"\end{table}", ""]

    nat = json.loads((FIG / "native_nist.json").read_text())
    out.append(rf"\newcommand{{\NatOnshape}}{{{nat['summary']['onshape']}}}")
    out.append(rf"\newcommand{{\NatCadmpeg}}{{{nat['summary']['cadmpeg']}}}")
    out += [r"\begin{table}[t]", r"\centering\small", r"\begin{tabular}{@{}lrrrlrr@{}}", r"\toprule",
            r"& \multicolumn{2}{c}{Onshape import} & \multicolumn{2}{c}{cadmpeg 0.6.0} & \multicolumn{2}{c}{Solid operations} \\",
            r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(l){6-7}",
            r"Part & IoU \% & $\Delta V$ \% & IoU \% & STEP & Designer & Recovered \\", r"\midrule"]
    for r in nat["parts"]:
        c = r["cadmpeg"]
        state = "valid" if c["valid"] else ("no solid" if not c.get("solids") else "invalid")
        out.append(f"{short(r['part'])} & {r['onshape']['iou_pct']:.2f} & {r['onshape']['dvol_pct']:+.3f} & "
                   f"{c['iou_pct']:.2f} & {state} & {r['designer_ops']} & {r['ours_ops']} \\\\")
    out += [r"\bottomrule", r"\end{tabular}",
            r"\caption{NIST's native SolidWorks 2018 files decoded to STEP by two decoders and compared with NIST's "
            r"own STEP of each part; and the number of solid operations in the designer's tree (as decoded) against "
            r"the tree \code{featuretree} recovers from the STEP.}",
            r"\label{tab:native}", r"\end{table}", ""]
    # -- the designers' feature vocabulary against the IR's kinds ---------------------------------
    from collections import Counter
    mix = Counter()
    for r in nat["parts"]:
        mix.update(r["designer_mix"])
    how = {"extrude": ("pad, pocket, prism\\_cut", "kind"), "fillet": ("fillet", "kind"),
           "revolve": ("revolve", "kind"),
           "hole": ("a pocket or placed cut", "geometry"), "pattern": ("its instances, one cut each", "geometry"),
           "chamfer": ("a placed cut", "geometry"), "draft": ("taper on the extrusion it drafts", "geometry"),
           "shell": ("a pocket", "geometry"), "rib": ("a pad", "geometry"), "combine": ("--", "none")}
    total = sum(mix.values())
    n_kind = sum(n for k, n in mix.items() if how[k][1] == "kind")
    n_next = sum(mix[k] for k in ("hole", "pattern", "chamfer"))
    out.append(rf"\newcommand{{\VocabTotal}}{{{total}}}")
    out.append(rf"\newcommand{{\VocabKind}}{{{n_kind}}}")
    out.append(rf"\newcommand{{\VocabKindPct}}{{{100 * n_kind / total:.0f}}}")
    out.append(rf"\newcommand{{\VocabNext}}{{{n_next}}}")
    out.append(rf"\newcommand{{\VocabNextPct}}{{{100 * (n_kind + n_next) / total:.0f}}}")
    out += [r"\begin{table}[t]", r"\centering\small", r"\begin{tabular}{@{}lrrl@{}}", r"\toprule",
            r"Designer's feature & Count & Share \% & In the IR \\", r"\midrule"]
    for k, n in mix.most_common():
        tag = {"kind": "own kind: ", "geometry": "shape only, as ", "none": ""}[how[k][1]]
        out.append(f"{k} & {n} & {100 * n / total:.1f} & {tag}{how[k][0]} \\\\")
    out += [r"\midrule", f"all & {total} & 100.0 & \\\\", r"\bottomrule", r"\end{tabular}",
            r"\caption{The solid-modifying features in the designers' own trees of the eleven NIST SolidWorks "
            r"files (as decoded by cadmpeg), and what the IR has for each. ``Shape only'' means the IR can "
            r"hold the geometry but the feature loses its identity in the tree.}",
            r"\label{tab:vocab}", r"\end{table}", ""]

    # -- the edit round trip -------------------------------------------------------------------
    def nudge(d):
        rows, tot = [], Counter()
        for f in sorted((FIG / d).glob("*.json")):
            r = json.loads(f.read_text())
            c = Counter(e["outcome"] for e in r["edits"])
            tot.update(c)
            rows.append((r["part"], r["editable"], len(r["edits"]), c))
        return rows, tot
    rows, tot = nudge("nudge")
    _, before = nudge("nudge_before")
    tried = sum(tot.values())
    out.append(rf"\newcommand{{\NudgeTried}}{{{tried}}}")
    out.append(rf"\newcommand{{\NudgeAgree}}{{{tot['agree']}}}")
    out.append(rf"\newcommand{{\NudgeBeforeAgree}}{{{before['agree']}}}")
    out.append(rf"\newcommand{{\NudgeBeforeLost}}{{{before['edit did not reach the IR']}}}")
    out.append(rf"\newcommand{{\NudgeBeforeTried}}{{{sum(before.values())}}}")
    cols = ["agree", "volumes differ", "reference rebuild failed", "FreeCAD rebuild failed",
            "edit did not reach the IR", "other parameters changed"]
    cols = [c for c in cols if tot[c] or c == "agree"]
    out += [r"\begin{table}[t]", r"\centering\small", r"\begin{tabular}{@{}lrr" + "r" * len(cols) + "@{}}",
            r"\toprule", "Part & Editable & Edited & " + " & ".join(c.capitalize() for c in cols) + r" \\",
            r"\midrule"]
    for part, ed, n, c in rows:
        nm = short(part) if part.startswith("nist") else part.replace("_", " ")
        out.append(f"{nm} & {ed} & {n} & " + " & ".join(str(c[k]) for k in cols) + r" \\")
    out += [r"\midrule", f"all & {sum(r[1] for r in rows)} & {tried} & " +
            " & ".join(str(tot[k]) for k in cols) + r" \\", r"\bottomrule", r"\end{tabular}",
            r"\caption{The edit round trip. One dimension at a time is set to 1.1 times its value in the "
            r"FreeCAD tree, every parameter is read back into the IR by feature name, and the reference "
            r"rebuilds from the IR. ``Agree'': the edited FreeCAD solid and the rebuilt reference are within "
            r"0.5\% in volume. ``Editable'': dimensions FreeCAD can drive; up to six per part were edited.}",
            r"\label{tab:nudge}", r"\end{table}", ""]

    macros = [x for x in out if x.startswith(r"\newcommand")]
    (HERE / "macros.tex").write_text("\n".join(macros) + "\n")
    (HERE / "tables.tex").write_text("\n".join(x for x in out if x not in macros))
    print("\n".join(out[:3]))


if __name__ == "__main__":
    main()
