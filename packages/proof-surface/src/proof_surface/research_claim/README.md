# Research-Claim Proof Packet (`proof_surface.research_claim`)

> Make an AI-assisted research claim inspectable: sources, a formal statement,
> prover/checker attempts, verification checks, a re-derivable verdict, and a
> promotion-ladder rung. A failed attempt is still evidence.

Wedge #3 (pipeline-math++).

## One command

```bash
python -m proof_surface.research_claim \
  --input examples/research_claim/triangular.json \
  --claim "The identity held under a bounded numeric probe." \
  --scope "Bounded probe n=1..1000; not a general proof." \
  --packet-id demo-triangular --out demo-out
# emits: packet.json · report.md · crucible-thesis.json · crucible-measurements.json
```

The input JSON carries `statement`, `sources` (`ref` + optional `url`/`sha256`),
`attempts` (`method`, `result`), and `checks` (`checker`, `status` in
pass/fail/unverifiable). Each check maps to a crucible measurement — pass →
MATCH, fail → DRIFT, unverifiable → UNVERIFIABLE — and the verdict re-derives
through real crucible.

## Honest failure is a first-class outcome

A `fail` or `unverifiable` check still produces a **valid** packet that preserves
the sources, attempts, and evidence — a negative result is evidence, not a
discarded run. The packet carries a rung of the dogfood **promotion ladder**
(`SOURCE_LEAD → HYPOTHESIS → IDENTITY → PROBE_MATCH → CRUCIBLE_MATCH →
UNVERIFIABLE → LAW_CANDIDATE`); `PROMOTED_LAW` is deliberately unreachable by a
single packet — that requires independent reproduction and review. The packet
inherits the family's forbidden-field and authority-language guards, so it can
never call an unproven claim "CERTIFIED".
