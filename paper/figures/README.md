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

Observed 2026-09-19:

| Quantity | Value |
|---|---|
| `verified` | `True` |
| `vol_orig` | `14642823.6` mm³ |
| `vol_ir` | `14627973.5` mm³ |
| `dvol` | `14850.06` mm³ |
| `dvol_pct` | `0.1` % |
| `dsize_mm` | `0.0` mm |
| features | `51` |
| `recovered` | `{'pockets': 11, 'holes': 10, 'residual_lumps': 2}` |
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

## Figures still to generate

| Figure | Intended content | Command | Status |
|---|---|---|---|
| `nist_recovery.png` | Input solid vs recovered tree, side by side | `python3 step_recognize.py tests/step/nist_ctc_01_asme1_rd.stp --stl out/nist_recovered.stl` then render | **not yet generated** |
| `ir_pipeline.pdf` | TikZ: IR → {FreeCAD, Onshape, build123d} + roundtrip back | would be authored inline in `main.tex` | not started |

`out/nist_compare.png` exists in the repo but its generating command is **not
recorded**; do not reuse it in the paper until it is regenerated by a documented
command (stale-artifact risk).
