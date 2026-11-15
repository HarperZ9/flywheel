# Model-Eval Proof Packet `demo-model-eval`

**Decision: PROMOTE - Verdict: MATCH** -- claude-opus-4-8 met the accuracy and latency objectives on arithmetic-bench.

- **Reason:** all gated metrics met their objective within tolerance
- **Scope:** One offline eval suite; default-deny promotion.
- **Model:** `claude-opus-4-8` (hosted) cfg `e3b0c44298fc...`
- **Eval set:** arithmetic-bench (`datasets/arith@v1`, 500 items)
- **Objective:** promotion-gate -- promote iff accuracy >= 0.90 and p95 latency <= 100ms

## Metrics

| Metric | Value | Target | Dir | Deviation | Tolerance | Verdict |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| accuracy | 0.94 ratio | 0.9 | maximize | 0.0 | 0.01 | MATCH |
| p95_latency_ms | 88 ms | 100 | minimize | 0.0 | 5.0 | MATCH |

## Uncertainty

- single offline eval suite; distribution shift not tested

_Default-deny: a model is promoted only if the overall verdict is MATCH. The verdict is re-derivable via crucible from the emitted thesis + measurements._