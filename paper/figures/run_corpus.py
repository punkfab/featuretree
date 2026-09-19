#!/usr/bin/env python3
"""Corpus benchmark: run step_recognize over the NIST MBE PMI test corpus.

This is the evaluation the paper needs to move past n=1. It reports a
VERIFIED / PARTIAL / ERROR / TIMEOUT rate over the NIST CTC + FTC parts and,
for each part, the residual decomposition that shows how much the scalar volume
test understates the true geometric discrepancy.

Corpus: the "AP203 geometry only" set -- pure b-rep, no PMI annotations, which
is the input class the recogniser targets. Source:
  NIST MBE PMI Validation and Conformance Testing project.
  https://www.nist.gov/programs-projects/mbe-pmi-validation-and-conformance-testing-project
NOTE: NIST's own README states these are NOT error-free reference files and that
conformance checkers report syntax errors in some of them. Failures below may
therefore reflect the input, not only the recogniser -- do not over-read them.

Each part runs in a SUBPROCESS with a hard timeout, so one pathological part
cannot hang or crash the sweep.

Usage (from the REPO ROOT):
    python3 paper/figures/run_corpus.py [--corpus DIR] [--timeout SEC] [--jobs N]

Writes paper/figures/corpus_results.json and prints a summary + LaTeX table.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import subprocess
import sys
import time

DEFAULT_CORPUS = os.path.expanduser(
    "~/Downloads/NIST-PMI-STEP-Files/AP203 geometry only"
)
OUT_JSON = os.path.join("paper", "figures", "corpus_results.json")

# Executed in a subprocess, one part per process.
WORKER = r'''
import json, os, sys, time
sys.path.insert(0, os.getcwd())
path = sys.argv[1]
res = {"part": os.path.basename(path)}
t0 = time.time()
try:
    import b3d_emit, step_recognize as sr
    from build123d import Pos, import_step

    spec, rep = sr.recognize(path)
    res.update(
        status="VERIFIED" if rep.get("verified") else "PARTIAL",
        dvol_pct=rep.get("dvol_pct"),
        dsize_mm=rep.get("dsize_mm"),
        vol_orig=rep.get("vol_orig"),
        vol_ir=rep.get("vol_ir"),
        features=len(spec.get("features", [])),
        method=rep.get("method"),
        recovered=rep.get("recovered"),
        warnings=rep.get("warnings", []),
    )

    # Residual decomposition (union / inclusion-exclusion; direct OCCT boolean
    # difference is unreliable on these operands -- see error_decomposition.py).
    try:
        def one(o):
            s = o.solids() if hasattr(o, "solids") else []
            return s[0] if s else o
        orig = one(import_step(path))
        out = b3d_emit.emit(spec)
        rec = one(out[0] if isinstance(out, tuple) else out)
        bo, br = orig.bounding_box(), rec.bounding_box()
        rec = Pos(bo.min.X - br.min.X, bo.min.Y - br.min.Y, bo.min.Z - br.min.Z) * rec
        A, B = orig.volume, rec.volume
        u = orig + rec
        U = sum(s.volume for s in u.solids()) if u.solids() else u.volume
        overcut, uncut, net = U - B, U - A, B - A
        total = overcut + uncut
        res["decomp"] = {
            "overcut": overcut, "uncut": uncut, "net": net, "total": total,
            "overlap_pct": 100.0 * (A + B - U) / A if A else None,
            "cancellation": (total / abs(net)) if abs(net) > 1e-9 else None,
        }
    except Exception as exc:
        res["decomp_error"] = f"{type(exc).__name__}: {exc}"[:200]

except Exception as exc:
    res.update(status="ERROR", error=f"{type(exc).__name__}: {exc}"[:300])

res["seconds"] = round(time.time() - t0, 2)
print("@@JSON@@" + json.dumps(res))
'''


def run_one(path: str, timeout: int) -> dict:
    t0 = time.time()
    try:
        p = subprocess.run(
            [sys.executable, "-c", WORKER, path],
            capture_output=True, text=True, timeout=timeout,
        )
        for line in p.stdout.splitlines():
            if line.startswith("@@JSON@@"):
                return json.loads(line[len("@@JSON@@"):])
        return {
            "part": os.path.basename(path), "status": "ERROR",
            "error": (p.stderr.strip().splitlines() or ["no output"])[-1][:300],
            "seconds": round(time.time() - t0, 2),
        }
    except subprocess.TimeoutExpired:
        return {"part": os.path.basename(path), "status": "TIMEOUT",
                "seconds": timeout}


def latex_table(rows: list[dict]) -> str:
    out = [
        r"\begin{tabular}{llS[table-format=3.2]S[table-format=3.0]S[table-format=4.1]}",
        r"\toprule",
        r"Part & Verdict & {$|\Delta V|/V$ (\%)} & {Features} & {Time (s)} \\",
        r"\midrule",
    ]
    for r in rows:
        name = r["part"].replace("nist_", "").replace("_asme1", "")
        name = os.path.splitext(name)[0].replace("_", r"\_")
        dv = r.get("dvol_pct")
        nf = r.get("features")
        out.append(
            f"\\code{{{name}}} & \\textsc{{{r['status'].lower()}}} & "
            f"{dv if dv is not None else '{--}'} & "
            f"{nf if nf is not None else '{--}'} & {r.get('seconds','{--}')} \\\\"
        )
    out += [r"\bottomrule", r"\end{tabular}"]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=DEFAULT_CORPUS)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()

    files = sorted(
        os.path.join(args.corpus, f)
        for f in os.listdir(args.corpus)
        if f.lower().endswith((".stp", ".step"))
    )
    if not files:
        sys.exit(f"no STEP files in {args.corpus}")
    print(f"corpus: {args.corpus}\n{len(files)} parts, timeout {args.timeout}s, "
          f"{args.jobs} jobs\n")

    rows: list[dict] = []
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(run_one, f, args.timeout): f for f in files}
        for fut in cf.as_completed(futs):
            r = fut.result()
            rows.append(r)
            d = r.get("decomp") or {}
            extra = ""
            if d.get("cancellation"):
                extra = (f"  [overcut {d['overcut']:.0f} / uncut {d['uncut']:.0f}"
                         f" -> {d['cancellation']:.2f}x]")
            print(f"  {r['status']:<9} {r['part']:<34} "
                  f"dvol={r.get('dvol_pct','--')!s:>7}  "
                  f"feat={r.get('features','--')!s:>4}  "
                  f"{r.get('seconds','--')!s:>7}s{extra}")

    rows.sort(key=lambda r: r["part"])
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w") as fh:
        json.dump({"corpus": args.corpus, "results": rows}, fh, indent=2)

    n = len(rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\n" + "=" * 62)
    print(f"{n} parts")
    for k in ("VERIFIED", "PARTIAL", "ERROR", "TIMEOUT"):
        if counts.get(k):
            print(f"  {k:<9} {counts[k]:>3}   ({100.0*counts[k]/n:.1f}%)")
    cancels = [r["decomp"]["cancellation"] for r in rows
               if (r.get("decomp") or {}).get("cancellation")]
    if cancels:
        print(f"\ncancellation factor over {len(cancels)} decomposed parts: "
              f"min {min(cancels):.2f}x  max {max(cancels):.2f}x  "
              f"mean {sum(cancels)/len(cancels):.2f}x")
    print(f"\nwrote {OUT_JSON}")
    print("\n--- LaTeX ---\n" + latex_table(rows))


if __name__ == "__main__":
    main()
