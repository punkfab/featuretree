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
            r"``Valid'': passes \code{ir.validate}. Onshape's run stopped at the free plan's daily API quota.}",
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
    macros = [x for x in out if x.startswith(r"\newcommand")]
    (HERE / "macros.tex").write_text("\n".join(macros) + "\n")
    (HERE / "tables.tex").write_text("\n".join(x for x in out if x not in macros))
    print("\n".join(out[:3]))


if __name__ == "__main__":
    main()
