# Introduction to Proof Surface

Proof Surface is a stdlib-only Python library that validates AI workflow
records and builds re-derivable proof packets. It ships two layers:

1. **Nine base contracts**: validators for evidence packets, work-record
   receipts, authorization receipts, witness receipts, pre-execution gates,
   evaluation contracts, claim ledgers, delegation chains, and organ receipt
   bundles. Every validator returns a list of `Issue` objects; an empty list
   means valid.
2. **Eleven domain proof-packet wedges**: builders that take evidence a tool
   already produces (an agent trace, a color measurement, a benchmark attempt,
   a solver run, a scientific claim) and turn it into a validated packet with
   a `MATCH` / `DRIFT` / `UNVERIFIABLE` verdict, all reachable through one
   CLI: `telos-proof <domain>`.

It has zero runtime dependencies. Version 0.2.0, alpha; contracts are
versioned `v0.1` and may still change shape.

## Why it exists

A log records what a producer chose to write down. A proof packet carries the
evidence, the claim, the scope boundary, and a verdict that any independent
checker can re-derive from the evidence itself. Proof Surface is the validator
layer that keeps those records honest: it rejects malformed or
authority-shaped content, and a packet that overclaims (a benchmark that saw
the answer, a read-only tool claiming a hardware calibration) is rejected, not
warned about.

## Core concepts

**Issue lists.** Every validator takes a parsed `dict` and returns
`list[Issue]`. `Issue` is a frozen dataclass with `path` (a JSONPath-style
string like `$.scope.allowed_actions`) and `message`. Empty list means valid.
`*_file` variants take a `pathlib.Path` and return the same shape.

**Closed lattices.** Decision helpers never return free text. The gate returns
allow / deny / needs-human. The evaluation contract returns deploy / block /
needs-human. Delegation verification returns `VALID` / `DENIED` /
`UNVERIFIABLE`. Wedge verdicts are `MATCH` / `DRIFT` / `UNVERIFIABLE`. Nothing
ever emits `TRUSTED`, `APPROVED`, or `AUTHORIZED`.

**Default-deny, fail-closed.** An action is authorized when it is on the
allowlist, so an empty allowlist denies everything. A check has to be confirmed
to pass; anything less becomes `unknown` and escalates to needs-human. A
measured value whose uncertainty interval straddles its threshold also goes to
needs-human.

**Contracts vs wedges.** The base contracts validate the shape of a record.
The wedges go further: each builds a packet from domain evidence, derives a
verdict from checks (never reads it from the input), renders a reviewer-facing
Markdown report, and emits crucible `thesis` / `measurements` files so an
independent checker can recompute the verdict from the same evidence.

**Honesty gates.** A proof packet is only worth more than a log if it can be
wrong in a way a checker can catch. Every wedge names the specific way its
claim could be inflated and rejects the packet when that inflation is present.

**Bundles.** Each wedge run writes a content-addressed `bundle.json` that
digests the other artifacts, so a packet, its report, and its re-derivation
inputs travel as one checkable unit.

## The first ten minutes

From a checkout of the repo:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

**Minute one: validate a document.** Any dict, any contract.

```python
from proof_surface import validate_claim_ledger

ledger = {
    "ledger_version": "0.1",
    "claims": [{
        "claim_id": "c1",
        "statement": "Accuracy on the held-out set is 92.3%.",
        "source": "agent:evaluator-v1",
        "confidence": 0.95,
        "evidence_refs": ["runs/metrics.json"],
        "depends_on": [],
        "conflicts_with": [],
    }],
}
print(validate_claim_ledger(ledger))   # [] means valid
```

**Minute two: break it.** Add an unknown top-level key `"foo": 1` and the
validator answers with a precise path:

```
[Issue(path='$.foo', message='unexpected field')]
```

That rejection is the product. Every level of the hard-pinned contracts sets
`additionalProperties: false`, so the shape itself catches drift and smuggled
fields.

**Minutes three to five: run the API demo.**

```bash
python examples/demo.py
```

It walks the authorization receipt (`check_action` allowing `read_file` and
denying `delete_file`), the pre-execution gate (allow with a budget
estimate, needs-human once the estimate is dropped), the evaluation contract
(deploy on a clear pass, needs-human on a straddle), the claim ledger, and the
delegation chain (`VALID`, `DENIED`, and `UNVERIFIABLE` when signature
assurance is demanded and the verifier is absent).

**Minutes five to eight: build a proof packet.**

```bash
telos-proof visual-measurement \
  --input examples/visual_measurement/measurement.json \
  --claim "sRGB coverage measured on a read-only capture" \
  --scope "software capture only, no hardware probe" \
  --out ./demo-out
```

The report prints with `**Verdict: MATCH**` and six artifacts land in
`./demo-out`. Open `report.md` for the reviewer view, `packet.json` for the
validated record, and the `crucible-*.json` files for the re-derivation
inputs. Note what the packet refuses to say: it is read-only, so it makes no
physical-calibration claim, and the report says so explicitly.

**Minutes eight to ten: look at the fixtures.** Each contract ships valid and
invalid documents under `conformance/<contract>/v0.1/` with a
`manifest.json`. The invalid fixtures are the specification of what gets
rejected; read them next to the schema in `schemas/` when you need a concrete
shape.

## Where to go next

- **[USAGE.md](../USAGE.md)**: the full call surface, all nine contracts and
  eleven wedges, with worked examples and expected output.
- **[README.md](../README.md)**: the feature overview, the contract and wedge
  tables, and the design stance.
- `proof_surface.trace_adapters`: attach receipts to the stack you already
  run. Normalizers for OpenTelemetry and LangSmith / Langfuse run trees, and
  evidence importers for MLflow, Weights & Biases, Braintrust, Arize Phoenix,
  promptfoo, Helicone, DVC, and SLSA / in-toto.
- **[CHANGELOG.md](../CHANGELOG.md)**: current delivery status and the
  history of each gate.
- The wider toolkit: [harperz9.github.io](https://harperz9.github.io).
