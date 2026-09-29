# Figure & number provenance

Every quantitative claim in `main.tex` must be regenerable by a command here.
Run all commands from the **repo root** (`/home/dan/sandbox/punkfab/featuretree`).

Verified on **2026-09-19** against commit `4ac569a` (+ uncommitted README/paper work).

---

## Numbers in Table~1 (NIST CTC-01)

All rows except the base envelope come from one call:

```bash
python3 -c "
import step_recognize
spec, r = step_recognize.recognize('tests/step/nist_ctc_01_asme1_rd.stp')
print(r['verified'], r['vol_orig'], r['vol_ir'], r['dvol'], r['dvol_pct'], r['dsize_mm'])
print(len(spec['features']), r['recovered'], r['blind_holes'])
"
```

Observed 2026-09-28 (after the multi-region / axis-gate change):

| Quantity | Value |
|---|---|
| `verified` | `True` |
| `vol_orig` | `14642823.6` mm³ |
| `vol_ir` | `14622488.2` mm³ |
| `dvol` | `20335.36` mm³ |
| `dvol_pct` | `0.14` % |
| `dsize_mm` | `0.0` mm |
| features | `54` |
| `recovered` | `{'pockets': 14, 'holes': 10, 'residual_lumps': 2}` |
| `blind_holes` | `14` |
| `method` / `extrude_axis` | `extrude` / `[0,0,1]` |
| wall-clock | `7.7` s (single desktop CPU core) |

### Base envelope (the "+154.7%" row)

The base envelope is the **leading `sketch`+`pad` of the winning axis**, before
any carving. It is *not* what `recognize(..., recover=False)` returns — that call
can select a **different axis candidate** (it reported `dvol_pct=31.72`, an
under-volume best-effort on another axis), so do not use it for this row.

```bash
python3 -c "
import step_recognize as sr, b3d_emit
spec, r = sr.recognize('tests/step/nist_ctc_01_asme1_rd.stp')
sub = dict(spec); sub['features'] = spec['features'][:2]   # sketch + pad only
out = b3d_emit.emit(sub)
solid = out[0] if isinstance(out, tuple) else out
print('base=%.1f orig=%.1f  %+.1f%%' % (solid.volume, r['vol_orig'],
      100.0*(solid.volume-r['vol_orig'])/r['vol_orig']))
"
```

Observed: `base=37292555.0 orig=14642823.6 +154.7%`.

> **Correction logged.** The repo previously stated **139%** in three places
> (`README.md:200`, `LAUNCH.md:61`, `step_recognize.py:19`). That figure dates
> from commit `8840907` (2026-07-12) and the algorithm changed afterwards. The
> reproducible value today is **+154.7%**. Fix the three call sites before
> release so the paper and the repo agree.

## Regression suite

```bash
python3 -m pytest tests/ -q
```
Observed: `47 passed in 16.80s`.

## Assembly ingestion

```bash
python3 cadgen_ingest.py --selftest
```
Observed: `plate_peg: 2 occurrence(s), 1 mate(s), 0 coupling(s), 1 pose(s);
parts recognized 2, VERIFIED 2` — `base_plate` and `peg` both `VERIFIED vol Δ0.0%`,
mates joined, labels agree.

> **⚠ Unreproducible claim — do not put in the paper as written.** The repo
> README claims the cadgen **planetary** hero model (9 parts, 8 mates, a gear
> coupling, 2 poses) recovers with *every* part VERIFIED (gears Δ0.0%, pins
> Δ0.01%). That result **cannot be reproduced from the distributed fixtures**:
> `tests/fixtures/cadgen/README.md` states the `components/*.surf` geometry blobs
> "are not included", and `--selftest` exercises only the 2-part `plate_peg` case.
> `main.tex` is currently scoped to the 2-part fixture and carries a
> `TODO-EVIDENCE` comment. To use the 9-part number, ship the geometry.

## Priority / availability dates

```bash
git log --reverse --format='%ad %s' --date=short | head -1        # 2026-06-26 initial public release
git log --format='%ad %h %s' --date=short -- step_recognize.py | tail -1   # 2026-07-10 first recogniser commit
gh repo view punkfab/featuretree --json createdAt --jq .createdAt # 2026-06-26T07:18:51Z
```

---

## Figure 1 — `carve_convergence.pdf` (in the paper)

```bash
python3 paper/figures/make_convergence.py
```
Emits the recovered IR incrementally and plots reconstructed volume vs the
target. Observed: base `37292555.0` (+154.7%) → final `14627973.5` (−0.10%),
target `14642823.6`. Regenerates both `.pdf` (used by LaTeX) and `.png`.

## Table 2 — residual decomposition

```bash
python3 paper/figures/error_decomposition.py
```
Observed 2026-09-28 (after the multi-region / axis-gate change):

| Component | mm³ | % of part |
|---|---|---|
| over-cut (missing from reconstruction) | 20397.0 | 0.1393 |
| uncut (extra in reconstruction) | 61.6 | 0.0004 |
| net, signed (what the verifier sees) | −20335.4 | 0.1389 |
| **total geometric discrepancy** | **20458.7** | **0.1397** |

Overlap `|A∩B|` = 99.861% of `A`. Cancellation factor **1.01×** — on this
recovery the residual is almost purely over-cut.

> **This number moved, and that is the point.** Observed 2026-09-19, on the
> recovery produced *before* the axis-gate/multi-region change, the same part
> decomposed as 19035.9 over-cut vs 4185.9 uncut — a **1.56×** cancellation
> factor. Nothing in the criterion bounds this term, and it moved by 50% of its
> own value under a front-end change that was not aimed at it. Re-run this
> script after ANY recogniser change before quoting the figure.

> **Correction logged.** The repo previously attributed the ~0.1% residual
> entirely to the part's 8 uncut chamfers. That cannot be right: uncut chamfers
> would make the reconstruction *larger*, and it is **smaller**. Over-cut
> dominates uncut material throughout. `README.md` has been corrected.

> **Boolean trap.** Direct OCCT `-` and `&` between the original and the
> co-registered reconstruction return degenerate results (zero intersection for
> solids whose bounding boxes coincide exactly), while `+` behaves. The
> decomposition is therefore derived from the **union** by inclusion–exclusion,
> with a self-consistency assertion. Do not "simplify" the script back to a
> direct difference.

## Results report — the scorecard, per-part table and history (blog + paper)

```bash
python3 paper/figures/run_corpus.py --jobs 1 --timeout 5000   # ~33 min; cached per part
python3 paper/figures/iou_mc_check.py --jobs 3 --fine 20000
python3 paper/figures/intent_eval.py
python3 paper/figures/results_report.py   # -> results.md, results.json, results_tables.html
```

`run_corpus.py` persists every recovered tree to `recovered/<part>.json` and caches each
part's row in `recovered/<part>.row.json`, keyed on a hash of the recogniser's source;
a re-run redoes only parts whose code changed (`--fresh` redoes everything). Every
later script reads the persisted trees, so all numbers describe the same trees.
Published run: FEATURETREE_JOBS=2 (candidate processes per part), one part at a time.
The scorecard criteria are OURS -- NIST's test cases target PMI translation and define
no feature-recognition score.

## IoU — Table 1's last column, and why it is NOT from the Boolean harness

```bash
python3 paper/figures/iou_corpus.py      # Boolean (OCCT union) IoU  -> iou_results.json
python3 paper/figures/iou_mc_check.py --jobs 3 --fine 20000   # Boolean-FREE check -> iou_mc_results.json
```

**The paper's IoU column comes from `iou_mc_check.py`, not `iou_corpus.py`.** The measurement
itself is the library module `iou_check.py` (tests: `tests/test_iou_check.py`; CLI:
`step_recognize.py part.step --iou`); the paper script only runs it over the corpus.
Every input is reduced to its solids first: NIST STEP imports carry stray wires, and
CTC-01's import bounding box (1170 × 650 mm around an 800 × 450 mm solid) once put a
VERIFIED part at 20% IoU through the corner alignment. The
Boolean harness derives IoU from an OCCT union by inclusion–exclusion. On
PARTIAL parts that union is unreliable in a way no range check catches: it can
return the larger operand as the "union", which makes IoU equal the volume ratio
and satisfies `U >= max(A,B)` with equality. Preprint v2 shipped four such
numbers. `iou_mc_check.py` classifies 20 000 sampled points (the published run; default 60 000) against both solids
(no Booleans at all) and reports a 95% binomial interval.

Observed 2026-09-28 (boolean vs Boolean-free, at the Boolean harness's rotation):

| Part | Boolean | Boolean-free | Verdict |
|---|---|---|---|
| CTC-01 | 99.86 | 99.82 ± 0.07 | agrees |
| CTC-02 | 11.34 | 3.88 ± 0.34 | **Boolean wrong** |
| CTC-03 | 58.54 | 0.14 ± 0.28 | **Boolean wrong** (= B/A) |
| CTC-04 | 25.17 | 25.04 ± 0.47 | agrees |
| CTC-05 | 11.42 | 8.03 ± 0.62 | **Boolean wrong** |
| FTC-06 | 22.86 | 23.10 ± 0.53 | agrees (but not the best rotation: 39.34) |
| FTC-07 | 30.02 | 29.33 ± 0.83 | agrees |
| FTC-08 | 53.21 | 52.91 ± 0.99 | agrees |
| FTC-09 | 99.68 | 99.74 ± 0.04 | agrees |
| FTC-10 | 74.35 | 1.20 ± 0.19 | **Boolean wrong** |
| FTC-11 | 100.00 | 100.00 | agrees |

The table reports the Boolean-free **best over all 24 orientations**
(`best` in the JSON; CTC-01 falls back to `at_harness_rot` because its full search
crashed OCCT). All three VERIFIED parts agree, so "no false accept" rests on a
Boolean-free measurement.

Also fixed on the way: `one()` in both harnesses took `solids()[0]`, so
multi-region recoveries (CTC-02, FTC-07, FTC-08) were scored on a single region.

## Figures

| Figure | Content | Command |
|---|---|---|
| `carve_convergence.{pdf,png}` | CTC-01 volume vs features applied | `python3 paper/figures/make_convergence.py` |
| `recovered_parts.png` | original vs recovered for CTC-01, FTC-10, FTC-07, drawn in the Boolean-free registration | `iou_mc_check.py`, then `python3 paper/figures/render_recovered.py` |
| `freecad_tree.png` | CTC-01's recovered tree as a native FreeCAD PartDesign document | `python3 paper/figures/freecad_screenshot.py` (needs the FreeCAD AppImage, `xvfb-run`, ImageMagick) |
| `recovered_all.png` | original vs recovered for **all 11** parts, Boolean-free registration | `python3 paper/figures/render_recovered.py --all` |
| `corpus_table.{md,html}` | the full NIST set, every verification detail, plus the rows NIST publishes that were not run | `python3 paper/figures/corpus_table.py` (after `run_corpus.py`, `iou_mc_check.py`) |

`freecad_screenshot.py` runs FreeCAD with `FREECAD_USER_HOME` pointed at a
throwaway directory. Without that it reads the invoking user's real config, and
a pending Document Recovery from their own sessions opens a modal dialog over
the capture — which a script must never click.

`recovered_parts.png` is what exposed the Boolean failure: FTC-10's recovery drew
at right angles to its original under a caption claiming 74% overlap. **Render
every registration you report a number for.**

`out/nist_compare.png` is stale (51-feature recovery, uncommitted command) and is
superseded by `recovered_parts.png`.

## Design intent vs the designer's PMI — `intent_results.json`

```bash
python3 paper/figures/intent_eval.py
```

Recovers each VERIFIED part from its geometry-only file, infers intent with `intent.py`
(holes, counterbores, patterns, units, standard sizes) and scores it against the semantic PMI
in the part's AP242 file, read by `pmi.py`. The two files are different exports of one design
(CTC-01: 117 vs 139 faces, +2,000 mm^3) but share a frame, so recovered holes are carried into
it with `iou_check.registration_transform`.

Observed 2026-09-29:

| Part | Holes found | Nominal agrees | Units | Grouping P / R |
|---|---|---|---|---|
| CTC-01 | 7/7 | 7/7 | metric ✓ | n/a — every callout is a single hole |
| FTC-09 | 29/30 | 27/27 | inch ✓ | 0.78 / 0.78 |
| FTC-11 | 2/2 | 2/2 | metric ✓ | n/a — two callouts, one feature each |

Caveats. CTC parts are "not intended to be fully toleranced" (NIST), so CTC-01's drawing
dimensions only 7 of its round features and never groups them; grouping is only meaningful on
FTC-09. A callout partition is a proxy for pattern truth, not the truth: a designer may give
two holes of one pattern separate callouts. Drill sizes come from the ASME B94.11M values as
tabulated on Wikipedia's "Drill bit sizes" (fetched 2026-09-29).

