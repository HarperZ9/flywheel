# Governance Bridge (`harness.governance_bridge`)

`harness.governance_bridge` provides three pure-stdlib OSI MIT verification
modules (`N34`, `N68`, `N70`) with zero third-party runtime dependencies:

- **`quote_provenance.py` (`N34`)**: lints standing-rule citations against
  canonical ruling texts, requiring a valid ISO-8601 calendar date, exact
  FIPS 180-4 SHA-256 source digest, and verbatim substring match (`>= 8`
  characters). Paraphrased, misdated, short, or hash-tampered citations fail
  closed with deterministic bitmasks (`1`, `2`, `4`, `8`).
- **`anti_softness.py` (`N68`)**: deterministic adversarial dialogue critic
  measuring sycophancy phrases, premature hedging, and tidy-redemption tropes
  against direct-falsification evidence, failing closed on soft or unbacked
  agreement.
- **`boring_bridge.py` (`N70`)**: offline FIPS 180-4 SHA-256 and RFC 6962
  Merkle receipt bundle sealer and verifier built on `harness.merkle`, catching
  any 1-bit payload mutation, inclusion-proof tamper, root mismatch, or bundle
  digest edit offline.

## Quick start

```python
from harness.governance_bridge import (
    RuleCitation, StandingRule, evaluate_transcript,
    lint_citation, seal_boring_bundle, verify_boring_bundle,
)

rule = StandingRule("R1", "Zero em dashes in published prose.", "2026-11-24")
assert lint_citation(rule, RuleCitation("R1", "2026-11-24", rule.source_sha256, "Zero em dashes in published prose.")).ok

score = evaluate_transcript("Claim A is false: measured drift contradicts baseline and fails parity.")
assert score.passed

bundle = seal_boring_bundle([{"id": "rec-0", "verdict": "MATCH"}], bundle_id="demo-1")
assert verify_boring_bundle(bundle) == (True, "MATCH")
```

## Honest scope limits

Each module publishes an explicit `HONEST_SCOPE_LIMIT` string:

- `quote_provenance` checks exact substring and SHA-256 provenance against
  supplied canonical text; it does not resolve external legal authority.
- `anti_softness` applies a deterministic lexical rubric; it does not model
  semantic sincerity or literary merit.
- `boring_bridge` verifies cryptographic integrity and RFC 6962 inclusion
  offline; it does not establish external witness consensus or timestamping.
