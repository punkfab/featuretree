| Part | NIST set | Verdict | Fails | Volume error | Extent error | IoU (%) | Features | How recovered | Time |
|---|---|---|---|---|---|---|---|---|---|
| CTC-01 | Combined | **VERIFIED** | — | 0.14% | 0.00 mm | 99.81 ± 0.07 | 54 | extrude ∥Z · +14 pockets, +10 cross-holes | 29 s |
| CTC-02 | Combined | PARTIAL | volume + extents | 62.19% | 267.69 mm | 7.4 ± 0.4 | 64 | extrude ∥Y · 2 regions | 94 s |
| CTC-03 | Combined | PARTIAL | volume + extents | 41.46% | 132.54 mm | 36.1 ± 3.0 | 16 | extrude ∥Y | 13 s |
| CTC-04 | Combined | PARTIAL | volume + extents | 2.43% | 390.00 mm | 30.8 ± 0.5 | 270 | extrude ∥Z | 79 s |
| CTC-05 | Combined | PARTIAL | volume + extents | 51.80% | 349.25 mm | 14.5 ± 0.8 | 106 | extrude ∥Z | 18 s |
| FTC-06 | Fully-toleranced | PARTIAL | volume + extents | 31.85% | 98.83 mm | 59.6 ± 0.6 | 44 | extrude ∥Y · +17 pockets, +5 cross-holes | 16 s |
| FTC-07 | Fully-toleranced | PARTIAL | volume + extents | 1.80% | 6.36 mm | 94.9 ± 0.4 | 21 | drafted shell ∥Y (1.0°) · +9 pockets, +8 cross-holes | 57 s |
| FTC-08 | Fully-toleranced | PARTIAL | volume | 32.61% | 0.00 mm | 52.7 ± 1.0 | 24 | extrude ∥X · 2 regions | 46 s |
| FTC-09 | Fully-toleranced | **VERIFIED** | — | 0.19% | 0.00 mm | 99.70 ± 0.05 | 80 | extrude ∥Y | 10 s |
| FTC-10 | Fully-toleranced | PARTIAL | volume + extents | 20.80% | 18.00 mm | 76.0 ± 0.5 | 24 | extrude ∥Z | 31 s |
| FTC-11 | Fully-toleranced | **VERIFIED** | — | 0.00% | 0.00 mm | 100.00 ± 0.00 | 2 | revolve | 3 s |

11 of 11 parts yield an editable tree; 3 VERIFIED, 8 PARTIAL, 0 refused. PARTIAL IoU ranges 7.4–94.9%.

Gate: volume error ≤ 0.5% and extent error ≤ 0.05 mm. IoU is Boolean-free (60 000 sampled points, 95% interval) and exactly registered: the recogniser's own rotation and offset are undone, so it is a measurement, not a bound.

Published by NIST but not run:

| Part | NIST set | Status |
|---|---|---|
| STC-06 | Simplified | same geometry as FTC-06 (confirmed: volume and extents) |
| STC-07 | Simplified | same geometry as FTC-07 per NIST; does not import in OpenCASCADE |
| STC-08 | Simplified | same geometry as FTC-08 (confirmed: volume and extents) |
| STC-09 | Simplified | same geometry as FTC-09 (confirmed: volume and extents) |
| STC-10 | Simplified | same geometry as FTC-10 (confirmed: volume and extents) |
| FTC-08 (tessellated) | Fully-toleranced | faceted surfaces, not exact B-rep; out of scope |
| HTC | Hole | 2024 model, not in the corpus download used; not evaluated |
| MTC | Modified | 2018 model, not in the corpus download used; not evaluated |
