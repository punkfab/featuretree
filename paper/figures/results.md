# featuretree on the NIST MBE PMI test geometry

## Scorecard

- Coverage: **11/11** distinct test geometries (all CTC and FTC cases)
- VERIFIED: **3/11** (volume ≤ 0.5%, extents ≤ 0.05 mm, IoU ≥ 99.5%); PARTIAL 8; errors 0
- False accepts (VERIFIED but independent IoU < 99.5%): **0**
- Exactly registered IoU, all parts: mean 97.6%, min 93.5%; 4/11 at ≥ 99%, 10/11 at ≥ 95%
- Within the volume gate: 6/11; within the extent gate: 9/11
- Recognition time: total 1763.4 s, median 152.3 s, max 562.2 s
- Complexity: 2727 input B-rep faces → 431 feature operations
- Intent vs PMI: holes 97/196, nominal sizes 68/74, units 9/11

## Per part

| Part | Verdict | Vol. err | Extent err (mm) | IoU (%) | Input faces | Operations | Time (s) | Holes vs PMI | Sizes | Units |
|---|---|---|---|---|---|---|---|---|---|---|
| CTC-01 | VERIFIED | 0.14% | 0.00 | 99.84 ± 0.11 | 139 | 39 | 86.5 | 7/7 | 7/7 | ✓ |
| CTC-02 | PARTIAL | 0.63% | 0.01 | 93.48 ± 0.75 | 663 | 89 | 562.2 | 2/7 | 2/2 | ✓ |
| CTC-03 | PARTIAL | 0.21% | 0.04 | 95.19 ± 2.46 | 139 | 33 | 72.2 | 0/11 | — | ✓ |
| CTC-04 | PARTIAL | 0.14% | 0.01 | 99.01 ± 0.23 | 517 | 93 | 193.9 | 36/41 | 30/36 | ✓ |
| CTC-05 | PARTIAL | 0.77% | 0.00 | 97.20 ± 0.77 | 208 | 40 | 58.2 | 1/1 | — | ✗ |
| FTC-06 | PARTIAL | 0.76% | 0.00 | 98.17 ± 0.27 | 144 | 18 | 165.7 | 0/22 | — | ✗ |
| FTC-07 | PARTIAL | 0.09% | 1.52 | 95.35 ± 0.66 | 269 | 21 | 194.1 | 4/27 | — | ✓ |
| FTC-08 | PARTIAL | 0.26% | 0.00 | 98.71 ± 0.40 | 270 | 32 | 152.3 | 16/16 | — | ✓ |
| FTC-09 | VERIFIED | 0.19% | 0.00 | 99.67 ± 0.09 | 158 | 40 | 18.5 | 29/30 | 27/27 | ✓ |
| FTC-10 | PARTIAL | 0.71% | 0.06 | 97.29 ± 0.31 | 214 | 25 | 241.3 | 0/32 | — | ✓ |
| FTC-11 | VERIFIED | 0.00% | 0.00 | 100.00 ± 0.00 | 6 | 1 | 18.5 | 2/2 | 2/2 | ✓ |

Why not VERIFIED:

- CTC-02: volume off 0.63%; overlap 93.5%
- CTC-03: overlap 95.2%
- CTC-04: overlap 99.0%
- CTC-05: volume off 0.77%; overlap 97.2%
- FTC-06: volume off 0.76%; overlap 98.2%
- FTC-07: extents off 1.52 mm; overlap 95.4%
- FTC-08: overlap 98.7%
- FTC-10: volume off 0.71%; extents off 0.06 mm; overlap 97.3%

## History

| Stage | VERIFIED | PARTIAL | Refused/error | IoU mean / min (exact) |
|---|---|---|---|---|
| First full run (preprint v1) (`e84737c`) | 3 | 5 | 3 | — |
| Axis prefilter relaxed, multi-region sections (`591c757`) | 3 | 8 | 0 | — |
| Open shells with draft; exact registration (`2ef8b6a`) | 3 | 8 | 0 | 61.0 / 7.4 |
| Shell outline layers, floor cutouts (`0f5162d`) | 3 | 8 | 0 | 65.0 / 7.4 |
| Layered 2.5D recognition, two-sided (IoU) gate, crash isolation (`HEAD`) | 3 | 8 | 0 | 97.6 / 93.5 |
