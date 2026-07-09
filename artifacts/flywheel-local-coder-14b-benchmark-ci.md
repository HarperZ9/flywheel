## Confidence intervals

### flywheel-local-coder-14b-benchmark-m7-scorecard.json

| Arm | Passed | Wilson 95% CI |
|---|---|---|
| flat_n | 8/8 (100%) | [0.676, 1.000] |
| no_search | 8/8 (100%) | [0.676, 1.000] |
| single_shot | 8/8 (100%) | [0.676, 1.000] |
| verified_inference | 8/8 (100%) | [0.676, 1.000] |

Difference verified_inference minus single_shot: +0.000, 95% CI [-0.324, +0.324] (newcombe_unpaired_approximation). This interval includes zero: no uplift is claimable at this N.

### flywheel-local-coder-14b-benchmark-m7-hard-scorecard.json

| Arm | Passed | Wilson 95% CI |
|---|---|---|
| flat_n | 9/10 (90%) | [0.596, 0.982] |
| no_search | 8/10 (80%) | [0.490, 0.943] |
| single_shot | 8/10 (80%) | [0.490, 0.943] |
| verified_inference | 9/10 (90%) | [0.596, 0.982] |

Difference verified_inference minus single_shot: +0.100, 95% CI [-0.236, +0.420] (newcombe_unpaired_approximation). This interval includes zero: no uplift is claimable at this N.
