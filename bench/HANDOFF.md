# featuretree vs CADFather — handoff (2026-10-12)

Goal: (1) run featuretree's `step_recognize` on CADFather's test sets, (2) run CADFather on the
11 NIST parts, (3) write the comparison. This was started on the Mac (8 cores, no GPU). Neither
half is finished. This file says what exists, what is trustworthy, and what to run next on the
workstation.

This folder (`bench/` on branch `build123d-0.13`) holds the handoff, the benchmark scripts and
the CADFather-on-NIST drivers and results. On the Mac the working directory was
`featuretree-bench/`, a sibling of the repo; the scripts assume that layout (`run_bench.py` looks
for the repo at `../featuretree`, `cf_nist/run_part.py` for the CADFather clone at `../cadfather`),
so copy `bench/` out to a sibling `featuretree-bench/` before running. Datasets, envs and the
NIST STL meshes are not in git: re-fetch the data as described below and regenerate the meshes
with `cf_nist/tessellate.py` (settings recorded in `cf_nist/tessellation.json`).

## Status at a glance

| Piece | State | Trust it? |
|---|---|---|
| DeepCAD test set as STEP (8,028 of 8,052 ids) | done, `data/deepcad/norm/` | yes |
| Fusion 360 test set as STEP (1,725 of 1,725) | done, `data/fusion360/norm/` | yes |
| featuretree on DeepCAD / Fusion 360 | 95 / 32 parts run, then stopped | **no — discard** (wrong build123d, see below) |
| CADFather algorithmic tools on NIST, paper limits | done, all 11 parts | yes, with the qualifier below |
| CADFather algorithmic tools on NIST, extended limits | killed part-way (3–4 parts started) | no — rerun |
| Full CADFather (generator + assistant) on NIST | not run, needs GPUs | — |
| Port of featuretree to build123d 0.13 | branch `build123d-0.13` created, **no edits yet** | — |

## 1. The build123d problem (read this first)

The repo does not record which build123d it was developed against, and no release I tried on the
Mac passes its own recogniser tests:

| build123d | OCP | Result |
|---|---|---|
| 0.13.0 | 7.9.x | `Vector.to_tuple()` removed → every part errors |
| 0.12.0 | 7.9.x | same |
| 0.11.0 | 7.9.3 | 5 of 62 tests fail (layered + shell paths, NIST CTC-01) |
| 0.10.0 | 7.8.1 | 8 of 62 fail (adds the three revolve tests) |
| 0.9.1 / 0.9.0 | 7.8.1 | layered path works, revolve detection fails |
| 0.8.0, 0.7.0 | 7.8.1 | import error (`HashCode`) |

Two behaviour changes explain it:

- **`edge @ t` now follows edge orientation** (0.10 and later). `_ordered_edges` returns a
  `rev` flag and its callers flip reversed edges themselves, so on new versions they are flipped
  twice. A 40×30 rectangle comes back as three points with one duplicated, `_split_pinched`
  then drops a corner, and the layered candidate fails verification.
- **An empty Boolean result**: on 0.9.x/0.10 `solid - rot` returns a `ShapeList` with no
  `.volume`; `_is_revolve_about` swallows the exception and answers "not a revolve".

**On the workstation, first run** `python -c "import build123d, OCP; print(build123d.__version__, OCP.__version__)"`
in the env where the paper's numbers were produced, and `python -m pytest tests/test_step_recognize.py tests/test_shell.py tests/test_iou_check.py -q`.
If that passes, use that env for the benchmark and write the version into the README — no port
needed for the comparison.

If you still want the port (you asked for it; I had only created the branch), the edits are:

1. `x.to_tuple()` → `tuple(x)`: 12 sites in `step_recognize.py` (lines 147, 153, 216–217, 335,
   713, 1156, 1303, 1329, 1397, 1424, 1588).
2. In `_ordered_edges` (`step_recognize.py:416`), wrap each edge forward-oriented
   (`Edge(e.Oriented(TopAbs_FORWARD))`) and keep the `rev` flag, so every `e @ t` downstream
   means what it meant before. Check the other `e @` users that take edges from `.edges()`
   rather than `_ordered_edges`: `_edge_bulge` (1226), `_ordered_poly` (1242), and
   `cell_recognize.py:303` (which goes through `_ordered_edges`).
3. `_is_revolve_about` (`:333`): treat an empty/`ShapeList` difference as volume 0 instead of
   relying on `.volume`.
4. `orig.solid()` (`:1341, 1583, 1602, 1609`, `cell_recognize.py:368`): 0.13 raises on a
   multi-solid input, older versions silently take the first. See finding (a) below — pick the
   largest solid and refuse VERIFIED when the input has more than one.

Done when the six test files above pass on 0.13.

## 2. featuretree on their test sets

Scripts (all in `featuretree-bench/`):

- `prep.py deepcad|fusion360` — one STEP per test part, scaled so the largest extent is 100 mm
  (featuretree's tolerances are absolute mm; IoU is scale-invariant).
  - DeepCAD: rebuilt from `cad_json` with DeepCAD's own `cadlib` logic ported from pythonocc to
    OCP; ids from `train_val_test_split.json["test"]`. 24 of 8,052 fail to build. The paper
    counts 8,046, so the sets differ by about 18 parts.
  - Fusion 360: the dataset's own `<id>.step` for the ids in `train_test.json["test"]`.
- `run_bench.py <dataset> --limit N --jobs J --timeout 300` — one subprocess per part, resumable,
  fixed seeded shuffle (any prefix is a random sample). Writes `results/<dataset>/<id>.json` and
  the recovered IR. IoU is `iou_check` (Boolean-free, best of 24 rotations, 20,000 points)
  against **all** solids of the input.
- `report.py deepcad fusion360` — invalid ratio, mean IoU over valid and over all, VERIFIED rate,
  VERIFIED-but-low-IoU counts.

To rerun on the workstation:

```bash
# data (HF is not needed; these are the original hosts)
curl -LO http://www.cs.columbia.edu/cg/deepcad/data.tar          # 208 MB -> data/deepcad/cad_json + split json
git clone --depth 1 https://github.com/ChrisWu1997/DeepCAD deepcad_src
# Fusion: only the 1,725 test .step files are needed from r1.0.1.zip (2.1 GB);
#   https://fusion-360-gallery-dataset.s3.us-west-2.amazonaws.com/reconstruction/r1.0.1/r1.0.1.zip
python prep.py deepcad && python prep.py fusion360     # prep needs matplotlib; works on build123d 0.13
rm -rf results/                                         # the Mac results are invalid
python run_bench.py deepcad   --jobs <cores/3>          # no --limit = full set
python run_bench.py fusion360 --jobs <cores/3>
python report.py deepcad fusion360
```

Edit `PY` at the top of `run_bench.py` to the workstation interpreter (it points at `ft_env`).
`recognize()` itself starts up to 3 subprocesses (`FEATURETREE_JOBS`), so keep `--jobs` near
cores/3; oversubscribing the Mac pushed load past 100. Unloaded cost on the Mac was roughly
10–25 s per DeepCAD part, most of it interpreter start-up for the isolated candidates.

Numbers to compare against (CADFather paper, Table 1, mean IoU over valid / invalid ratio):
DeepCAD 0.987 / 0.000, Fusion 360 0.976 / 0.000. The same table has **CADFit†** (algorithmic
only) at 0.914 / 0.275 and 0.882 / 0.256 — the closest like-for-like for a no-learning method.
MCB is mesh-only and cannot be fed to `step_recognize`.

Caveats to state in any write-up: input is the B-rep, theirs is a mesh of the same part; their
IoU is on normalised meshes, this one is point-classified against the B-rep.

### Findings from the invalid pilot (still worth checking)

These came from 40 DeepCAD parts under build123d 0.10, so the rates mean nothing, but two
behaviours are independent of the version bug:

- **(a) VERIFIED on half a part.** Two inputs with two solids were reported VERIFIED while
  scoring IoU 0.51 and 0.80 against the whole input: the recogniser takes the first solid and
  verifies against that alone. Multi-body parts are common in DeepCAD.
- **(b)** Several PARTIAL parts scored IoU 0.11–0.62 on simple extrusions. Probably the
  orientation bug; re-check on a correct env before reading anything into it.

## 3. CADFather on NIST

`cf_nist/` holds the work. What ran is **CADFather's algorithmic tools only**: `det_cold`,
`det_warm` and `optimize`, driven through the repo's own harness, scoring and budgets, with a
scripted greedy policy (`cf_nist/det_policy.py`) standing in for the Qwen assistant. The CADENA
generator (`stepwise`) and the assistant were not run. Do not label these "CADFather".

Setup on the Mac: `cf_env` (Python 3.12, cadquery 2.5.2, cadquery-ocp 7.7.2 and the other pins
from `agent/env/check_env.txt`), both native modules built (`cadfit._native` and `_cad_grad`),
a `realpath` shim for the build scripts. Inputs: `cf_nist/stl/` — the 11 "AP203 geometry only"
STEP files tessellated at 0.001 × bbox diagonal, cleaned through manifold3d
(`cf_nist/tessellate.py`, details in `stl/tessellation.json`).

Run A, paper limits (12 ops, 6 det calls, 10 optimizer calls, 30 s per candidate, 1000 s per
part), CADFather's own metric code. featuretree column is the paper's Table (`paper/main.tex`),
not re-measured here:

| Part | CADFather det+opt: ops | IoU | GMS | wall s | featuretree: verdict | features | IoU |
|---|---|---|---|---|---|---|---|
| CTC-01 | 6 | 0.809 | 0.713 | 71 | VERIFIED | 54 | 0.998 |
| CTC-02 | 6 | 0.567 | 0.524 | 187 | PARTIAL | 144 | 0.935 |
| CTC-03 | 1 | 0.697 | 0.764 | 38 | PARTIAL | 64 | 0.952 |
| CTC-04 | 6 | 0.779 | 0.632 | 168 | PARTIAL | 108 | 0.990 |
| CTC-05 | 6 | 0.906 | 0.804 | 262 | PARTIAL | 57 | 0.972 |
| FTC-06 | 6 | 0.898 | 0.690 | 124 | PARTIAL | 27 | 0.982 |
| FTC-07 | 6 | 0.883 | 0.847 | 180 | PARTIAL | 29 | 0.954 |
| FTC-08 | 6 | 0.783 | 0.861 | 110 | PARTIAL | 37 | 0.987 |
| FTC-09 | 3 | 0.994 | 0.924 | 172 | VERIFIED | 80 | 0.997 |
| FTC-10 | 2 | 0.587 | 0.573 | 223 | PARTIAL | 38 | 0.973 |
| FTC-11 | 1 | 0.990 | 0.798 | 121 | VERIFIED | 2 | 1.000 |
| **Mean** | | **0.808** | | | | | **0.976** |

All 11 produced a valid closed solid. Every part used all 6 det calls; the optimizer was called
on only two parts and improved neither. Full rows: `cf_nist/results.md`, `results.json`.

Read this table carefully: the two IoU columns come from different code (theirs on normalised
meshes, featuretree's on the B-rep), and the featuretree column predates this session. A clean
comparison scores both outputs with one metric — see "next" below.

### Next on the workstation

1. **Full CADFather on NIST** (the point of moving to GPUs). Follow the repo README: two envs
   (`agent/env/build_env.sh run|gen`), both native builds, download `kulibinai/cadena` (`rl/*`)
   and `Qwen/Qwen3.8-27B-FP8` (Hugging Face was unreachable from the Mac's network). The config
   assumes 4 GPUs — generator on one, three assistant replicas; edit `cuda_visible_devices` and
   `data-parallel-size` in `agent/configs/dialogue_lean.yaml` for what you have. Then:
   ```bash
   agent/run_folder.sh /path/to/cf_nist/stl --out /path/to/cf_nist/full --name nist
   ```
   Output is one `<part>.py` + `<part>.stl` per part and `results.csv` (score, IoU, GMS).
2. **Extended det-only run** (optional): `cf_env/bin/python cf_nist/sweep.py extended --jobs 3`
   lifts the caps to 60 ops / 60 det calls / 1 h per part (outside the paper's configuration;
   these parts have 27–144 features, so the 12-op cap is the obvious handicap).
   `cf_nist/sweep_whole.py` runs cadfit whole-part; one part took 1,886 s on the loaded Mac.
3. **One metric for both.** Score CADFather's result STLs and featuretree's re-emitted solids
   against the same input with the same code — either `iou_check` on both, or CADFather's
   `metrics.py` on both. `cf_nist/collect.py` already gathers the CADFather side.
4. Re-run featuretree's NIST corpus on the workstation (`paper/figures/run_corpus.py`) so the
   featuretree column is current.

Paths: `cf_nist/tessellate.py` has the Mac's absolute `SRC` path hard-coded; `run_part.py`
locates the clone as `../cadfather` relative to itself. NIST files:
https://www.nist.gov/document/nist-pmi-step-files (14 MB zip).

## 4. What the comparison can already say

- On NIST, CADFather's algorithmic component alone reaches mean IoU 0.81 inside the paper's
  12-operation cap; featuretree's published figure on the same parts is 0.976 with 27–144
  features on all but one part. Whether the learned generator and assistant close that gap is
  what the GPU run answers.
- On DeepCAD / Fusion 360 there is no valid featuretree number yet.

## Housekeeping

- `featuretree` repo: on branch `build123d-0.13`, working tree clean, nothing committed.
  `git checkout main && git branch -d build123d-0.13` if you do not want it.
- Safe to delete on the Mac: `env_0.7.0 env_0.8.0 env_0.9.0 env_0.9.1 env_0.11.0 env_0.12.0
  ft_env` (about 5 GB), `results/`, `cf_nist/scratch`, `cf_nist/runs/extended`,
  `data/deepcad_data.tar`.
