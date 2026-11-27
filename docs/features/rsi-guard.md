# RSI Guard v2 (`harness.rsi_guard`)

`harness.rsi_guard` provides three pure-stdlib OSI MIT modules for fail-closed recursive self-improvement governance (`STA-070`, `N28`, `N49`, `N53`, `J13`, `F1`) with zero third-party runtime dependencies and strict IEEE-754 finite-float validation on every numeric input.

## Modules

`goodhart_valve.py` enforces independent out-of-band oracle checks, strict `math.isfinite` rejection of `NaN`, `+Inf`, `-Inf`, and booleans on `proxy_score`, `oracle_score`, `effective_rank`, `top1_energy`, and overflow gaps, plus Goodhart proxy-vs-oracle divergence limits and zero-penalty honest exit on unsolvable tasks.

`drift_monitor.py` tracks rolling capability, Shannon entropy, and effective-rank telemetry, raising fail-closed alerts on non-finite telemetry, capability floor breaches, silent peak regressions, entropy collapse, non-monotonic steps, and oscillation loops.

`receipt_bridge.py` verifies `engine-receipt/1` canonical digests (`subject_sha256`, `claim_sha256`, `envelope_sha256`), optional HMAC tags, on-disk artifact hashes, and an append-only prev-hash JSONL ledger committed with an RFC 6962 Merkle root.

## Quick start

```python
from harness.rsi_guard import CandidateStep, StepTelemetry, assess_series, evaluate_rsi_step

decision = evaluate_rsi_step(
    CandidateStep("step-1", "compiler", 0.90, 0.88, "oracle-v1", True, False, False, 2.6, 0.72)
)
assert decision.accepted
assert assess_series([StepTelemetry(1, 1.0, 2.4, 2.6), StepTelemetry(2, 1.05, 2.4, 2.6)])["ok"]
```

## Honest scope limits

`goodhart_valve` validates supplied numeric scores and oracle verdicts; it cannot detect proxy gaming that also fools the supplied external oracle. `drift_monitor` detects non-finite inputs, regressions, and oscillation loops in reported trajectories; it does not re-measure model weights. `receipt_bridge` verifies digests, disk files, and ledger chaining offline; it does not re-execute the original oracle command.
