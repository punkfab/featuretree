| Part | NIST set | Verdict | Fails | Volume error | Extent error | IoU (%) | Features | How recovered | Time |
|---|---|---|---|---|---|---|---|---|---|
| CTC-01 | Combined | **VERIFIED** | — | 0.14% | 0.00 mm | 99.82 ± 0.07 | 54 | extrude ∥Z · +14 pockets, +10 cross-holes | 24 s |
| CTC-02 | Combined | PARTIAL | volume + extents | 62.19% | 267.69 mm | ≥ 3.9 | 64 | extrude ∥Y · 2 regions | 90 s |
| CTC-03 | Combined | PARTIAL | volume + extents | 41.46% | 132.54 mm | ≥ 6.5 | 16 | extrude ∥Y | 5 s |
| CTC-04 | Combined | PARTIAL | volume + extents | 2.43% | 390.00 mm | ≥ 25.0 | 270 | extrude ∥Z | 81 s |
| CTC-05 | Combined | PARTIAL | volume + extents | 51.80% | 349.25 mm | ≥ 8.2 | 106 | extrude ∥Z | 11 s |
| FTC-06 | Fully-toleranced | PARTIAL | volume + extents | 31.85% | 98.83 mm | ≥ 39.3 | 44 | extrude ∥Y · +17 pockets, +5 cross-holes | 12 s |
| FTC-07 | Fully-toleranced | PARTIAL | volume + extents | 63.41% | 30.25 mm | ≥ 30.3 | 52 | extrude ∥X · 2 regions | 18 s |
| FTC-08 | Fully-toleranced | PARTIAL | volume | 32.61% | 0.00 mm | ≥ 53.3 | 24 | extrude ∥X · 2 regions | 63 s |
| FTC-09 | Fully-toleranced | **VERIFIED** | — | 0.19% | 0.00 mm | 99.67 ± 0.05 | 80 | extrude ∥Y | 5 s |
| FTC-10 | Fully-toleranced | PARTIAL | volume + extents | 20.80% | 18.00 mm | ≥ 46.5 | 24 | extrude ∥Z | 26 s |
| FTC-11 | Fully-toleranced | **VERIFIED** | — | 0.00% | 0.00 mm | 100.00 ± 0.01 | 2 | revolve | 3 s |

11 of 11 parts yield an editable tree; 3 VERIFIED, 8 PARTIAL, 0 refused. PARTIAL IoU floors range 3.9–53.3%.

Gate: volume error ≤ 0.5% and extent error ≤ 0.05 mm. IoU is Boolean-free (60 000 sampled points, 95% interval); a PARTIAL figure is a lower bound.

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
