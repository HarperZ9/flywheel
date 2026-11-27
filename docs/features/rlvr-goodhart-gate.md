# RLVR Goodhart Divergence Gate

`harness/rlvr_goodhart_gate/` is a pure-stdlib MIT verifier for test-time Monte Carlo tree search and self-play RLVR oracle reports. It separates learned reward-model proxies from deterministic verifiers so reward-hacking candidates cannot pass silently.

## Checks Performed

Whenever a candidate reports `prm_score >= 0.90` while `oracle_score <= 1e-12`, the gate requires rejection, quarantine, and a negative assigned value. Any acceptance backed by a zero oracle verdict fails closed. Non-finite `NaN`, `Inf`, or boolean scores are rejected immediately.

The oracle also verifies non-decreasing solve-rate curves, blocks non-zero policy weight updates when `oracle_score == 0.0`, keeps trap-rule probability mass strictly below `0.05`, and caps three-way runtime parity error at `1e-10`. Optional `engine-receipt/1` envelopes must carry a `MATCH` verdict and exit code `0`.

## Scope Limits

This verifier audits candidate telemetry, policy update logs, and summary receipts produced by upstream runners. It does not train model weights or invoke remote endpoints.
