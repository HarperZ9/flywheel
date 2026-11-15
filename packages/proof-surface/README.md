<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/proof-surface/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/proof-surface/main/docs/art/hero-light.svg" alt="proof-surface: One proof packet per agent action, with verdicts derived from checks. A chain of small linked squares, each holding a few ruled lines, winds inward to a bright core." width="100%">
</picture>

# proof-surface

proof-surface checks an AI agent's trace against what the agent was allowed to do, and turns that trace, or a measurement, eval or solver run, into a JSON packet with a verdict and a readable report. It is a Python library and a command line with no runtime dependencies.

[![CI](https://github.com/HarperZ9/proof-surface/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/proof-surface/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-MIT-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/proof-surface/blob/main/LICENSE)
![python 3.10+](https://img.shields.io/badge/python-3.10%2B-e6e1d6?style=flat-square&labelColor=1a1712)

Give it an agent trace (OpenTelemetry, LangSmith or Langfuse style, or its own JSON format) and a permission grant that lists allowed actions, targets and an expiry. It checks every action against the grant and writes a packet that marks each one MATCH, DRIFT or UNVERIFIABLE, with the reason. A write outside the granted path comes back DRIFT with a BLOCK decision.

It is for people who build or review AI agents and want a portable record of what an agent did and whether it stayed in bounds, and for eval and research engineers who want a result written down with its claim, scope and tolerance. The same library can validate evidence packets and other workflow records against fixed schemas, with each problem reported by its JSON path.

**Versions.** PyPI has 0.1.0, which contains the base validators only. The packet builders and the `telos-proof` command are in 0.2.0 on GitHub, which is not on PyPI yet. Install from GitHub to follow this page.

## Try it

```bash
git clone https://github.com/HarperZ9/proof-surface
cd proof-surface
python -m pip install .
```

Check a trace in which an agent wrote to a file its grant did not cover:

```bash
telos-proof agent-action \
  --trace examples/agent_action/trace_denied.json \
  --authorization examples/agent_action/authorization.json \
  --claim "the agent stayed inside its grant" \
  --scope "one trace" \
  --out ./out-denied
```

```text
**Verdict: DRIFT** -- the agent stayed inside its grant
**BLOCK** (confidence: high) -- at least one checked claim drifted outside its tolerance
### `fs.write` on `/etc/passwd` -- DRIFT
- **Admission:** DENY (grant `grant-fs-write-work`) -- target '/etc/passwd' is outside the grant scope
```

The same command with `--trace examples/agent_action/otel-export.json --trace-format otel` reads an OpenTelemetry export and comes back MATCH. The command exits 0 whenever it writes a packet, so read the verdict from `packet.json` or the report.

Each run writes `packet.json`, `report.md`, `bundle.json` and two files for [crucible](https://github.com/HarperZ9/crucible); a third crucible file appears when crucible is installed. `bundle.json` records a SHA-256 for every file. To check later that nothing was edited:

```bash
telos-proof verify ./out-denied
# {"issues": [], "verdict": "MATCH"}     (exit 0; DRIFT exit 1, UNVERIFIABLE exit 2)
```

`verify` checks those digests. They are unsigned, so they catch an edit made without updating the bundle; anyone who rewrites the files and the bundle together will pass. `verify_bundle.py` in the repo does the same check as a single file with no imports from this package. Rebuilding from the same input gives byte-identical files, so a second person can rerun the command and compare.

For the 0.1.0 validators alone, install from PyPI:

```bash
pip install proof-surface
```

That release has `validate_packet`, `check_action`, `evaluate_gate`, `verify_delegation` and the other base validators, and no command line.

The outputs above come from 0.2.0 installed from a fresh clone into a new virtual environment on Python 3.12.

## How it compares

- **Tracing tools such as OpenTelemetry, LangSmith and Langfuse.** These record what an agent did. proof-surface reads their exports and adds the check against a permission grant and a verdict per action.
- **Policy engines such as Open Policy Agent and Cedar.** These evaluate rules written in a policy language at request time. proof-surface checks a recorded action against one fixed grant format after the fact, with expiry, revocation and scope.
- **Supply-chain attestations such as in-toto and SLSA.** These are signed and widely supported. proof-surface packets carry unsigned digests, and an adapter can import an SLSA provenance record as evidence.
- **Plain JSON Schema.** The schemas in `schemas/` check shape. The Python validators add rules a schema cannot express, such as time windows, scope narrowing along a delegation chain, and refusing words such as `APPROVED` in fields that must not carry authority.

## See it work, step by step

The [animated explainer](https://harperz9.github.io/repo-explainers/proof-surface.html)
walks through an authorization receipt allowing one read and denying everything else with the deciding field, the pre-execution gate allowing and escalating, a delegation chain, a visual-measurement proof packet from the shipped example, and the calibration gate rejecting an inflated claim. Every value on it is output from this repository. Its
source is [docs/explainer/index.html](docs/explainer/index.html).

## Watch

[![A passing check can still be wrong: a narrated film, 2 min 24 s](https://harperz9.github.io/media/explainers/passing-check/poster.jpg)](https://harperz9.github.io/explainers.html#passing-check-h)

**[A passing check can still be wrong](https://harperz9.github.io/explainers.html#passing-check-h)** (2 min 24 s, narrated, captioned). Proof Surface refuses a packet whose claim outruns its measurement. The film page carries the transcript, the sources and recall questions.

## Walkthrough

The demo and a measurement packet, step by step. The commands and outputs match a run of 0.2.0 from a fresh clone.

1. **Install.** Install from a checkout. Python 3.10 or newer.

   ```text
   $ git clone https://github.com/HarperZ9/proof-surface && cd proof-surface
   $ python -m pip install -e ".[test]"
   ```

2. **First run: the demo.** The demo gates the same action with and without a budget.

   ```text
   $ python examples/demo.py
   with budget       : allow
   without budget    : needs-human
   ```

3. **Build a packet from a measurement.** Turn the shipped colour measurement into a packet with a stated claim and scope.

   ```text
   $ telos-proof visual-measurement --input examples/visual_measurement/measurement.json --claim "sRGB coverage measured on a read-only capture" --scope "software capture only, no hardware probe" --out ./demo-out
   | delta_e_2000_mean | 1.42 dE | 0.0 | 1.42 | 2.0 | MATCH |
   | white_luminance | 118.0 cd/m2 | 120.0 | 2.0 | 5.0 | MATCH |
   Calibration boundary: hardware_measurement_used=False, physical_calibration_claim=False
   bundle.json  crucible-measurements.json  crucible-thesis.json
   packet.json  report.md
   ```

## What's inside

- **Eleven packet builders, one command.** `telos-proof agent-action`, `visual-measurement`, `research-claim`, `model-eval`, `optimization-workflow`, `rollout-receipt`, `eval-attempt`, `ai4science`, `conservation`, `control-certificate`, `competition-attempt`. Each takes a record your tools already write and produces a packet plus a Markdown report. Each wedge also installs its own script (`proof-surface-agent-action` and so on), and `python -m proof_surface <domain>` works too.
- **Overclaim checks per domain.** Each builder refuses the claim its domain tends to inflate: an eval answer marked correct when the model had the ground truth, a calibration claim from a read-only screen capture, an invariant check with no negative case that breaks it. The table further down lists all eleven.
- **Nine base validators.** Evidence packets, work records, permission grants (two versions), witness records, pre-execution gates, evaluation contracts, claim ledgers, delegation chains and receipt bundles. Each returns a list of issues with a JSON path; an empty list means valid. The decision helpers (`check_action`, `evaluate_gate`, `evaluate`, `verify_delegation`) deny or escalate to a person when something cannot be confirmed.
- **Importers.** `proof_surface.trace_adapters` reads OpenTelemetry exports and LangSmith or Langfuse run trees, and imports evidence from MLflow, Weights & Biases (artifacts and Weave), Braintrust, Arize Phoenix, promptfoo, Helicone, DVC and SLSA provenance. Each importer lists in `NON_INFERABLE` what its source cannot supply.
- **No runtime dependencies.** JSON Schemas are in `schemas/`, passing and failing examples for each contract in `conformance/`, and runnable demos in `examples/`.

The validators check structure and rules. They do not recompute a packet's verdict from its numbers; rerunning the builder on the same input does that.

## Why it matters

A log records what a tool chose to write down. A packet from proof-surface also records the claim, what the evidence covers, and a verdict worked out from that evidence, in a format another tool can read. Verdicts come from small fixed sets, and the library never writes `TRUSTED`, `APPROVED` or `AUTHORIZED`. It checks records only. It does not grant permission, run actions or store private payloads.

## Worked example

`check_action` verifies a specific action against an authorization receipt. It is default-deny: a structurally invalid receipt, a revoked grant, an expired window, or an out-of-scope action all deny.

```python
from datetime import datetime, timezone
from proof_surface import check_action, validate_authorization_receipt

receipt = {
    "authorization_version": "0.1",
    "receipt_id": "ar-demo",
    "kind": "authorization-grant",
    "principal": {"id": "user:alice@example.com", "role": "project-owner"},
    "agent": {"id": "agent:planner"},
    "intent": "Read repository files.",
    "scope": {
        "allowed_actions": ["read_file"],
        "allowed_targets": ["repo:proof-surface"],
    },
    "granted_at": "2026-06-17T00:00:00Z",
    "expires_at": "2026-06-19T00:00:00Z",
    "revoked": False,
}

now = datetime(2026, 6, 18, tzinfo=timezone.utc)
print(validate_authorization_receipt(receipt))                      # []
print(check_action(receipt, "read_file", "repo:proof-surface", now=now))    # None (allowed)
print(check_action(receipt, "delete_file", "repo:proof-surface", now=now))
# Issue(path='$.scope.allowed_actions',
#       message="action denied: 'delete_file' not in allowed_actions")
```

## The base contracts

| Contract | Validator | One line |
| --- | --- | --- |
| proof-surface packet (`v0.1`) | `validate_packet` | Neutral evidence/index packet a proof-index consumes. |
| work-record receipt (`v0.1`) | `validate_work_record` | Outward-flowing record of agent work; `additionalProperties: false` at every level, never read back as model state. |
| authorization receipt (`v0.1`) | `validate_authorization_receipt`, `check_action` | Explicit, least-privilege, expiring, revocable grant from a human principal. Verifier input only. |
| authorization receipt (`v0.2`) | `validate_authorization_receipt_v2`, `check_action_v2` | Exactly scoped inner receipt with agent, action, target, nonce, time window, revocation flag, and action budget. Signature trust and atomic consumption stay outside this library. |
| witness receipt | `validate_witness_receipt` | Consumer-side mirror of EMET's witness-receipt shape and closed verdict lattice. |
| pre-execution gate (`v0.1`) | `evaluate_gate`, `validate_gate_request` | Default-deny, fail-closed, advisory: allow / deny / needs-human with per-dimension checks. Any unconfirmable dimension escalates to needs-human. |
| evaluation contract (`v0.1`) | `validate_evaluation_contract`, `evaluate` | Eval as a deploy gate: deploy / block / needs-human, uncertainty-aware (a measured value whose interval straddles its threshold never silently passes). |
| claim ledger (`v0.1`) | `validate_claim_ledger`, `confidence_gate`, `find_conflicts`, `trace_dependents` | Traceable multi-agent memory: source-provided confidence, declared conflicts, cycle-safe contamination tracing. Reports provenance; does not adjudicate truth. |
| delegation chain (`v0.1`) | `validate_delegation_chain`, `verify_delegation`, `compute_binding`, `compute_chain_binding` | Authority rooted in a real human, monotonic scope attenuation per hop, SHA-256 hash-chained with a whole-chain binding. Verdicts: `VALID` / `DENIED` / `UNVERIFIABLE`. |
| organ receipt bundle (`v0.1`) | `validate_organ_receipt_bundle` | Links related receipts from different tools by digest and reference, including classification and control receipts; closed `receipt_kind` vocabulary, no embedded payloads. |

Integrity caveat, stated up front: the delegation hash-chain is keyless, so it gives self-consistent integrity, not tamper-evidence against an adversary who rewrites the document and recomputes every binding. Real anti-forgery needs an external anchor: pin `chain_binding` out-of-band or verify asymmetric signatures per hop. Demanding signature assurance with no verifier returns `UNVERIFIABLE`, never a fabricated `VALID`.

![Eight stages of a single gate evaluation: request, shape, reserved names, authorization, budget, state, human gap, and aggregate. A request describes one planned action with its kind, its target and an estimated cost in tokens and wall time. Five fields are allowed at the root and any other field is refused. Reserved names are rejected at every level of the object rather than only at the top, so a forbidden key cannot hide inside a nested block. Four checks then run: authorization, budget, state and the human gap. Each check returns one of four values: pass, fail, unknown, or not applicable. The state check reads a witness verdict from a closed set of seven, of which only three count as confirming, alongside a target digest and the digest that was expected. The aggregate is not a vote. One failure anywhere denies the action; with no failure but any unknown the answer is that a person still has to look; allow requires authorization to pass outright and the other three to pass or not apply. Three outcomes: allow, deny, and needs human.](docs/art/gate-lane.svg)

## The packet builders

Each builder (called a wedge in the code) comes with a validator, a report and a command. They share one verdict rule (`MATCH` / `DRIFT` / `UNVERIFIABLE`), a required decision summary, a limit on what a single packet may claim, and a bundle file with a digest per file.

![Eight stages of one domain run: evidence, wedge, contract, honesty gate, measure, combine, decide, and bundle. Evidence starts as a trace, a run record or a measurement already on disk. One command routes it to one of eleven domain wedges, each of which owns its own arguments. The contract rejects unknown fields rather than ignoring them, so an unrecognised document is unverifiable rather than valid. Each wedge then applies its own refusal, the rule that stops that domain's characteristic overclaim. Measurement is a margin: tolerance minus deviation, over tolerance, matching if that margin is at or above zero. The combination is not an average. Unverifiable dominates, then drift, and an empty set reads as a match because there is nothing to refute. One decision follows from the overall verdict, with a closed vocabulary of seven outcomes and three confidence levels, defaulting to escalate when the verdict is not recognised. Four artifacts are written and hashed into one manifest, which records a digest per file and a digest over those digests. Three outcomes: match, drift, and unverifiable.](docs/art/packet-lane.svg)

| Wedge | Turns this into a packet | The overclaim it refuses |
| --- | --- | --- |
| `agent-action` | an agent trace | admission / side-effects / evidence refs / typed failures / compute leases |
| `visual-measurement` | a read-only color / display measurement | no physical-calibration claim without hardware and mutation evidence |
| `research-claim` | a math / formal proof attempt | a PASSED kernel replay must disclose axioms, toolchain, source; never `PROMOTED_LAW` from one packet |
| `model-eval` | a model + eval set + directional metrics | default-deny promotion: promote only on overall `MATCH` |
| `optimization-workflow` | a solver run vs an exact baseline | a non-executed branch claims no coverage; a surrogate may not self-certify feasibility |
| `rollout-receipt` | an RL / post-training run | reward, verifier, admission, promotion stay separate |
| `eval-attempt` | a single benchmark attempt | `correct` with ground-truth access counts as contamination and fails |
| `ai4science` | a claim-to-experiment run | no unmeasured discovery claims; independent reproduction required |
| `conservation` | a transformation + declared invariant | the check must carry a negative fixture that provably breaks the invariant |
| `control-certificate` | a stability / feasibility claim | hardware validity is never claimable from simulation-only evidence |
| `competition-attempt` | a competition / judge attempt | source-pinned judge repo; verdicts cite only certificate layers that executed |

Optional disclosure fields use the same format and are checked when present: `declared_branches[]` (a fenced branch claims no verdict and is not citable support), `witness_tier` (the promotion rung may not exceed the strongest verifier tier that executed), `evidence_classes[]` (single-modality evidence caps at the hypothesis rung), and `replication` (a generalization claim needs two or more independent `MATCH` instances). Omit them and a packet validates unchanged.

![Eleven domain wedges, one to a row, each with the overclaim it refuses and the rule that does the refusing. Agent action binds every material action to one admission and one side-effect class. Visual measurement blocks a calibration claim from a read-only surface. Research claim stops tier inflation from a fenced branch or a single modality. Model eval is default-deny on promotion. Optimization workflow blocks a hardware or quantum claim without a completed hardware branch. Rollout receipt keeps reward, verdict, admission and promotion as four separate records. Eval attempt is accented, because it is the one row where a correct answer is refused: a correct outcome recorded alongside ground-truth access is contamination rather than a pass. AI for science gates each promotion rung on measurement, independent reproduction and settled objections. Conservation requires a negative fixture that provably breaks the invariant. Control certificate requires every condition of its kind to be witnessed and blocks hardware validity from simulation. Competition attempt allows the overall verdict to cite only layers that executed.](docs/art/wedge-refusals.svg)

## Status

- Version 0.2.0 on GitHub, alpha. PyPI has 0.1.0 (base validators only). Contracts are versioned `v0.1` and may still change shape.
- Runtime: Python 3.10 or newer per package metadata; CI runs the suite on 3.11 and 3.12. Stdlib-only core, no runtime dependencies.
- The pytest suite and the passing and failing examples under `conformance/<contract>/v0.1/` are the tests for the current contracts.
- Scope: Proof Surface validates records. Granting authority, executing actions and storing private payloads are outside it. EMET stays an independent peer, not a dependency; the witness-receipt validator mirrors its schema so other tools can validate EMET receipts without importing EMET.

## Documentation

- **[docs/INTRODUCTION.md](docs/INTRODUCTION.md)**: what it is, core concepts, and a first-ten-minutes walkthrough.
- **[USAGE.md](USAGE.md)**: the full call surface with worked examples and expected output.
- **[CHANGELOG.md](CHANGELOG.md)**: current delivery status.
- `examples/` for runnable demos, `schemas/` for JSON Schemas, `conformance/` for valid and invalid fixtures.
- Peer repos and the wider toolkit: [harperz9.github.io](https://harperz9.github.io).

A packet is worth more than a log only when a checker can catch it being wrong, and the tests here include the failing cases for each contract.

## For developers

Keep the public README, package metadata, and examples aligned with current behavior. Before opening a PR or pushing a release, run the local package verification path:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

See [AGENTS.md](AGENTS.md) for the repository's contributor rules. Brand assets live under `docs/brand/` (hero: `docs/brand/proof-surface-hero.png`).

## License

MIT.

---
**Zain Dana Harper**, small tools with explicit edges.
[Portfolio](https://harperz9.github.io) · [HarperZ9](https://github.com/HarperZ9)
<sub>Built with Claude Code; reviewed, tested, and owned by me.</sub>

## What this believes

This tool is one part of a family that holds a single belief steady across
every surface: knowledge open to anyone who can attain the means; acceptance
decided by external checks, never reputation; every result re-runnable;
honest nulls first-class; ownership earned by comprehension; learning woven
into the work. The full text lives in [CREDO.md](CREDO.md).
The long form of this belief: [The Unbundling](https://github.com/HarperZ9/flywheel/blob/main/docs/essays/2026-07-13-the-unbundling.md).

---

Built by **[Zain Dana Harper](https://harperz9.github.io)** in Seattle: evidence-first tools that leave a re-checkable artifact behind. The full workbench is at [Project Telos](https://harperz9.github.io).

---

## The ecosystem

This tool is one part of a family that holds a single belief steady across
every surface: knowledge open to anyone who can attain the means; acceptance
decided by external checks, never reputation; every result re-runnable;
honest nulls first-class; ownership earned by comprehension; learning woven
into the work.

- **[Workspace canon](https://github.com/HarperZ9/workspace)**: AGENTS.md, CREDO.md, MISSION.md, ECOSYSTEM.md
- **[Flywheel](https://github.com/HarperZ9/flywheel)**: the one platform (receipts, governance, infra controls, learning loop)
- **[Getting Started](https://github.com/HarperZ9/flywheel/blob/main/GETTING-STARTED.md)**: your first thirty minutes

Built by **[Zain Dana Harper](https://harperz9.github.io)** in Seattle.
