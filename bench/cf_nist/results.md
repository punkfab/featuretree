# CADFather algorithmic tools only (det + optimize), NIST CTC/FTC parts

NOT full CADFather: the CADENA generator VLM (`stepwise`) and the Qwen assistant were not run.
A scripted greedy policy (`det_policy.py`) drives the repo's own harness, det and optimizer.
IoU / GMS / CD are CADFather's own metric code (`agent/cad_agent/capabilities/metrics.py`).

## Run A: paper limits (depth 12, det 6, opt 10, 30 s/candidate, 1000 s/part)

| part | GT faces | valid closed solid | ops | IoU | GMS_norm (raw) | CD x1e3 | score | det calls (timeouts) | opt ok/calls | wall s | stop |
|---|---|---|---|---|---|---|---|---|---|---|---|
| nist_ctc_01 | 4334 | yes | 6 | 0.809 | 0.713 (7.18) | 0.41 | 0.761 | 6 (0) | 0/0 | 71 | done:exhausted |
| nist_ctc_02 | 36052 | yes | 6 | 0.567 | 0.524 (11.91) | 1.67 | 0.545 | 6 (0) | 0/0 | 187 | done:exhausted |
| nist_ctc_03 | 4950 | yes | 1 | 0.697 | 0.764 (5.89) | 1.54 | 0.731 | 6 (0) | 0/0 | 38 | done:exhausted |
| nist_ctc_04 | 28944 | yes | 6 | 0.779 | 0.632 (9.21) | 0.35 | 0.706 | 6 (0) | 0/0 | 168 | done:exhausted |
| nist_ctc_05 | 11270 | yes | 6 | 0.906 | 0.804 (4.90) | 0.31 | 0.855 | 6 (0) | 0/1 | 262 | done:exhausted |
| nist_ftc_06 | 14112 | yes | 6 | 0.898 | 0.690 (7.75) | 0.74 | 0.794 | 6 (0) | 0/0 | 124 | done:exhausted |
| nist_ftc_07 | 15348 | yes | 6 | 0.883 | 0.847 (3.81) | 0.37 | 0.865 | 6 (0) | 0/0 | 180 | done:exhausted |
| nist_ftc_08 | 12324 | yes | 6 | 0.783 | 0.861 (3.49) | 0.36 | 0.822 | 6 (0) | 0/0 | 110 | done:exhausted |
| nist_ftc_09 | 7680 | yes | 3 | 0.994 | 0.924 (1.90) | 0.09 | 0.959 | 6 (0) | 0/0 | 172 | done:exhausted |
| nist_ftc_10 | 22208 | yes | 2 | 0.587 | 0.573 (10.67) | 1.67 | 0.580 | 6 (0) | 0/0 | 223 | done:exhausted |
| nist_ftc_11 | 7050 | yes | 1 | 0.990 | 0.798 (5.06) | 0.10 | 0.894 | 6 (0) | 0/1 | 121 | done:exhausted |

Mean IoU over parts with an IoU: 0.808 (n=11 of 11); mean with failures as 0: 0.808; mean score (mean of IoU and GMS_norm, failures 0): 0.774

