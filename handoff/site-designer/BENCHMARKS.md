# Flywheel: Benchmarks

The numbers, their intervals, and the evidence file behind them. Put these on the
site as first-class content, not an afterthought. Keep the honest null.

Evidence: `evidence/benchmark-ci.json` in this bundle is a copy of the receipt the
site should cite. The live app serves the same file at
`/artifacts/flywheel-local-coder-14b-benchmark-ci.json`, so a reader can re-check.

---

## The model

Flywheel-Local-Coder-14B, a trained artifact with a full provenance chain.

- Artifact: `telos-coder-14b-cpt2020-q4_k_m.gguf`
- Size: just under 9 GB (4-bit)
- Weights fingerprint (sha256): `613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be`

## Hard set, 10 tasks

| Arm | Result | Wilson 95% CI | Receipts |
|---|---|---|---|
| single-shot | 8 / 10 (80%) | [0.490, 0.943] | 100% |
| verified inference | 9 / 10 (90%) | [0.596, 0.982] | 100% |
| best-of-4 | 9 / 10 (90%) | [0.596, 0.982] | 100% |
| single + oracle | 8 / 10 (80%) | [0.490, 0.943] | 100% |

## The honest null (keep it visible)

Verified inference beats single-shot by +0.100 here. The 95% interval on that
difference is [-0.236, +0.420], which includes zero, and plain best-of-4 sampling
ties it. So **we do not claim a capability uplift.**

What we do claim, and can measure:

- 100% receipt reproducibility. Every accepted answer re-checks.
- Pass parity with the models we route to.
- Availability on your own schedule, from weights you hold.
- Local cost.

Separating a real effect at this size would take roughly a hundred tasks. That is
what the curated hard lane is building toward. The number moves the day the
evidence does, not before.

## How to present this

Lead with the receipt-reproducibility and availability claims, which are strong
and true. Show the table with the intervals, not point estimates alone. Put the
honest null in the reader's eye line, in the warm-amber candor color, not buried.
A reader who sees you refuse to overclaim trusts the claims you do make.
