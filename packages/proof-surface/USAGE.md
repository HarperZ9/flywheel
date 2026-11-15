# Using proof-surface

A practical guide to the public API. `proof-surface` is a **stdlib-only,
zero-dependency** library: every contract is a plain validator (returns a list
of `Issue`, empty meaning valid) plus, for the active contracts, a decision
helper that returns a closed-lattice verdict. Nothing here grants authority or
is meant to be fed back into a model as trusted state -- these are **verifier
inputs and reviewer-facing outputs**.

> The output blocks below were produced by running the calls against
> `proof_surface` 0.2.0 on CPython 3.12. Treat exact reason strings as
> illustrative -- assert on `decision` / `verdict` / `path`, not on prose.

## Install

From a checkout (no runtime dependencies):

```bash
python -m pip install -e .
```

Or run straight from a checkout without installing, by putting `src/` on the
path:

```bash
PYTHONPATH=src python your_script.py
```

The test extra pulls in `pytest` and `jsonschema`:

```bash
pip install ".[test]"
pytest
```

There is no documented PyPI release path in this repository. Use the checkout
or an internal package built from this source tree.

## CLI entrypoints

The installed console scripts are declared in `pyproject.toml` under
`[project.scripts]`.

| Entrypoint | Module | What it does |
| --- | --- | --- |
| `telos-proof` | `proof_surface.cli:main` | Unified dispatcher for domain proof packets, contract validation, and bundle verification. |
| `proof-surface-agent-action` | `proof_surface.agent_action.cli:main` | Build/review an agent-action proof packet. |
| `proof-surface-visual-measurement` | `proof_surface.visual_measurement.cli:main` | Build/review a visual-measurement packet. |
| `proof-surface-research-claim` | `proof_surface.research_claim.cli:main` | Build/review a research-claim packet. |
| `proof-surface-model-eval` | `proof_surface.model_eval.cli:main` | Build/review a model-eval packet. |
| `proof-surface-optimization` | `proof_surface.optimization_workflow.cli:main` | Build/review an optimization-workflow packet. |
| `proof-surface-rollout-receipt` | `proof_surface.rollout_receipt.cli:main` | Build/review a rollout-receipt packet. |
| `proof-surface-eval-attempt` | `proof_surface.eval_attempt.cli:main` | Build/review a benchmark-attempt packet. |
| `proof-surface-ai4science` | `proof_surface.ai4science.cli:main` | Build/review an AI-for-science packet. |
| `proof-surface-conservation` | `proof_surface.conservation.cli:main` | Build/review a conservation packet. |
| `proof-surface-control-certificate` | `proof_surface.control_certificate.cli:main` | Build/review a control-certificate packet. |
| `proof-surface-competition-attempt` | `proof_surface.competition_attempt.cli:main` | Build/review a competition-attempt packet. |

Module entrypoints are available without installing scripts:

```bash
PYTHONPATH=src python -m proof_surface --help
PYTHONPATH=src python -m proof_surface.agent_action --help
```

The unified dispatcher also has two non-domain commands:

```bash
telos-proof validate path/to/document.json
telos-proof verify path/to/artifact-directory
```

`validate` currently recognizes authorization receipts v0.1/v0.2 and organ
receipt bundles v0.1. Unknown contracts return `UNVERIFIABLE`.

## Minimal quickstart

```bash
python -m pip install -e ".[test]"
telos-proof --help
telos-proof validate examples/agent_action/authorization.json
telos-proof visual-measurement \
  --input examples/visual_measurement/measurement.json \
  --claim "sRGB coverage measured on a read-only capture" \
  --scope "software capture only, no hardware probe" \
  --out ./demo-out
telos-proof verify ./demo-out
```

The domain command writes `packet.json`, `report.md`, `bundle.json`, and the
Crucible peer files into `./demo-out`.

## Configuration

Proof Surface has no service configuration, credentials, native dispatch, or
network setup. Inputs are local JSON files and output directories supplied on
the command line. Use environment variables only for normal Python packaging
concerns such as `PYTHONPATH=src` when running without installation.

For reproducible checks, keep input examples and generated artifact directories
inside a temporary or ignored path. Do not commit private payloads, credentials,
or local receipts.

## Troubleshooting

- `telos-proof: command not found`: install the checkout with
  `python -m pip install -e .`, or run `PYTHONPATH=src python -m proof_surface`.
- `UNVERIFIABLE` from `validate`: the document is malformed, is not an object,
  or is a contract the dispatcher does not recognize.
- `DRIFT` from `verify`: the artifact directory has a bundle but one or more
  receipt checks no longer match.
- `UNVERIFIABLE` from `verify`: the artifact directory is missing the bundle
  manifest or cannot be read.
- Import errors while running tests: install the test extra with
  `python -m pip install -e ".[test]"`.

## Limitations

Proof Surface validates records and produces reviewer-facing artifacts. It does
not grant authority, execute actions, contact providers, store private payloads,
or prove a scientific claim true outside the evidence and scope supplied to the
packet.

## The public surface at a glance

Everything is re-exported from the top-level `proof_surface` package.

| Contract | Validator (`-> list[Issue]`) | Decision / helper |
| --- | --- | --- |
| proof-surface packet | `validate_packet`, `validate_packet_file` | -- |
| work-record receipt | `validate_work_record`, `validate_work_record_file` | -- |
| authorization receipt v0.1 | `validate_authorization_receipt`, `validate_authorization_receipt_file` | `check_action(receipt, action, target, *, now=None) -> Issue \| None` |
| authorization receipt v0.2 | `validate_authorization_receipt_v2`, `validate_authorization_receipt_v2_file` | `check_action_v2(receipt, action, target, *, agent_id, actions_used, now=None) -> Issue \| None` |
| witness receipt | `validate_witness_receipt`, `validate_witness_receipt_file` | -- |
| pre-execution gate | `validate_gate_request` | `evaluate_gate(request) -> GateDecision` |
| evaluation contract | `validate_evaluation_contract` | `evaluate(contract, results) -> EvalDecision` |
| claim ledger | `validate_claim_ledger` | `confidence_gate`, `find_conflicts`, `trace_dependents` |
| delegation chain | `validate_delegation_chain`, `validate_delegation_chain_file` | `verify_delegation(...) -> DelegationVerdict`; producer helpers `compute_binding`, `compute_chain_binding` |
| organ receipt bundle | `validate_organ_receipt_bundle`, `validate_organ_receipt_bundle_file` | compact interchange over sibling organ receipts |

`Issue` is a frozen dataclass with two fields: `Issue.path` (a JSONPath-ish
string like `"$.scope.allowed_actions"`) and `Issue.message`. **An empty list
means valid.**

```python
from proof_surface import Issue, validate_packet
```

## Proof-packet wedges (the `telos-proof` CLI)

Eleven domain wedges live under `proof_surface.<wedge>` with a `build_*_packet`
builder, a `validate_*_packet` validator, a `render_report`, and a
`to_crucible_inputs` re-derivation helper. All eleven also route through one CLI:

```bash
telos-proof <domain> --input run.json --claim "..." --scope "..." --out ./artifacts
# equivalently: python -m proof_surface.<wedge> --input run.json ...
```

| Domain (`telos-proof <domain>`) | Module | Verdict is |
| --- | --- | --- |
| `agent-action` | `proof_surface.agent_action` | derived per action, filled by the crucible bridge |
| `visual-measurement` | `proof_surface.visual_measurement` | `MATCH` iff every metric is within tolerance |
| `research-claim` | `proof_surface.research_claim` | a promotion-ladder rung (never `PROMOTED_LAW`) |
| `model-eval` | `proof_surface.model_eval` | default-deny promotion (promote only on `MATCH`) |
| `optimization-workflow` | `proof_surface.optimization_workflow` | the solver-vs-exact-baseline obligation |
| `rollout-receipt` | `proof_surface.rollout_receipt` | the verifier verdict, with default-deny promotion |
| `eval-attempt` | `proof_surface.eval_attempt` | `MATCH` iff `correct` and uncontaminated |
| `ai4science` | `proof_surface.ai4science` | `MATCH` once independently reproduced |
| `conservation` | `proof_surface.conservation` | `MATCH` iff every witness conserves the invariant |
| `control-certificate` | `proof_surface.control_certificate` | `MATCH` iff every witnessed certificate condition holds |
| `competition-attempt` | `proof_surface.competition_attempt` | `MATCH` iff an executed, passing judge verdict, with no tier inflation |

Each CLI writes `packet.json`, a Markdown `report.md`, the crucible
`thesis`/`measurements` for independent re-derivation, and a content-addressed
`bundle.json`. Adapters for incumbent trace/eval systems live in
`proof_surface.trace_adapters`.

### Optional family evidence gates

Three optional fields let a packet disclose more of its evidence, and are held
honest when present. Omit them and the packet validates exactly as before.

```python
from proof_surface.research_claim import (
    build_research_claim_packet,
    validate_research_claim_packet,
)

packet = build_research_claim_packet(
    statement="for all n >= 1, sum_{k=1}^n k = n(n+1)/2",
    sources=[{"ref": "probe log", "sha256": "a" * 64}],
    attempts=[{"attempt_id": "a1", "method": "numeric-probe", "result": "bounded"}],
    checks=[{"checker": "numeric-probe", "status": "pass", "evidence": ["n=1..1000"]}],
    claim="the identity held under a bounded probe",
    scope="bounded probe; not a general proof",
    packet_id="rc-1",
    promotion="PROBE_MATCH",
    # A branch that did not run claims no verdict and is not citable support.
    declared_branches=[
        {"branch_id": "numeric", "status": "EXECUTED", "verdict": "MATCH"},
        {
            "branch_id": "lean-kernel",
            "status": "UNAVAILABLE_FENCED",
            "probe_evidence": "lake build failed: toolchain missing",
        },
    ],
    # The rung may not exceed the strongest verifier tier that actually ran.
    witness_tier={
        "declared_target_verifier": "kernel-proof",
        "strongest_executed_tier": "numeric-probe",
        "target_slot_status": "NOT_EXECUTED_FENCED",
    },
    # Single-modality evidence caps at the hypothesis rung.
    evidence_classes=["executable-check"],
)
assert validate_research_claim_packet(packet) == []
```

`declared_branches` is also accepted by `optimization_workflow`;
`witness_tier` and `evidence_classes` are `research_claim` fields bound to its
promotion ladder.

`model_eval` and `ai4science` accept an optional `replication` object. A
single-instance `MATCH` is never a scale claim: when `generalization_claim` is
true, the same contract must replay across two or more independent instances and
every instance verdict must be `MATCH`. Per-instance warnings are preserved.

```python
from proof_surface.ai4science import (
    build_ai4science_packet,
    validate_ai4science_packet,
)

packet = build_ai4science_packet(
    sources=[{"ref": "arxiv:2408.06292", "sha256": "a" * 64}],
    domain="biology",
    scientific_claim="compound X binds target Y",
    agent_actions=[{"action": "design assay", "tool": "benchling"}],
    protocol={"protocol_ref": "proto:1", "reproducible": True},
    measurement={"measured": True, "measurement_ref": "meas:1", "value": 0.4},
    reproduction={"status": "INDEPENDENTLY_REPRODUCED"},
    reviewer_objections=[],
    negative_result=False,
    claim="binding measured and reproduced across two labs",
    scope="two independent assays",
    packet_id="a4s-2",
    # A scale claim needs two or more MATCH instances; warnings are kept.
    replication={
        "instances": [
            {"instance_id": "lab-a", "verdict": "MATCH"},
            {"instance_id": "lab-b", "verdict": "MATCH", "warnings": ["site 2 rig"]},
        ],
        "generalization_claim": True,
    },
)
assert validate_ai4science_packet(packet) == []
```

---

## Example 1 -- validate a document

Every validator takes an already-parsed `dict` and returns `list[Issue]`. The
`*_file` variants take a `pathlib.Path`, load the JSON for you, and return the
same shape (a load/parse error comes back as a single `Issue` at `$`).

```python
from proof_surface import validate_claim_ledger

ledger = {
    "ledger_version": "0.1",
    "claims": [
        {
            "claim_id": "c1",
            "statement": "Accuracy on the held-out set is 92.3%.",
            "source": "agent:evaluator-v1",
            "confidence": 0.95,
            "evidence_refs": ["runs/metrics.json"],
            "depends_on": [],
            "conflicts_with": [],
        },
    ],
}

issues = validate_claim_ledger(ledger)
print(issues)
```

Expected output (valid document):

```
[]
```

If you misspell a field or drift past the allowlist, you get a precise path.
For example, adding an unknown top-level key `"foo": 1`:

```
[Issue(path='$.foo', message='unexpected field')]
```

---

## Example 2 -- authorization receipt + `check_action`

`check_action` returns `None` when the action is **allowed**, or an `Issue`
explaining the **denial**. It is default-deny: a structurally invalid receipt, a
revoked grant, an out-of-window timestamp, or an out-of-scope action all deny.
Pass an explicit `now` (an aware `datetime`) for reproducible checks.

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

print(validate_authorization_receipt(receipt))
print(check_action(receipt, "read_file", "repo:proof-surface", now=now))
print(check_action(receipt, "delete_file", "repo:proof-surface", now=now))
```

Expected output:

```
[]
None
Issue(path='$.scope.allowed_actions', message="action denied: 'delete_file' not in allowed_actions")
```

The first line confirms the receipt is structurally valid, the second shows an
allowed action (`None`), and the third shows a denial because `delete_file` is
not in the allowlist.

### Exactly scoped v0.2 inner receipts

Version 0.2 is a separate contract for a signed authorization system's inner
receipt. It names one agent, one action, and one target, and it requires a
nonzero lowercase hexadecimal nonce with at least 128 bits, an issued time,
an expiry, and a positive `max_actions` budget. Unknown fields fail closed.
The v0.1 validator and `check_action` API remain unchanged.

```python
from datetime import datetime, timezone
from proof_surface import check_action_v2, validate_authorization_receipt_v2

receipt = {
    "authorization_version": "0.2",
    "receipt_id": "ar2-forum-route-0001",
    "kind": "authorization-grant",
    "nonce": "0123456789abcdef0123456789abcdef",
    "agent_id": "agent:router-7",
    "action": "lane.call",
    "target": "forum/forum_route",
    "issued_at": "2026-08-02T12:00:00Z",
    "expires_at": "2026-08-02T12:05:00Z",
    "max_actions": 1,
    "revoked": False,
}

assert validate_authorization_receipt_v2(receipt) == []
assert check_action_v2(
    receipt,
    "lane.call",
    "forum/forum_route",
    agent_id="agent:router-7",
    actions_used=0,
    now=datetime(2026, 8, 2, 12, 2, tzinfo=timezone.utc),
) is None
```

Proof Surface does not verify an external signature, prove nonce randomness or
uniqueness, read a revocation store, or consume the budget. A trusted producer
and consumer must perform those checks before product code runs, with ledger
checks and consumption in one atomic operation. `actions_used` is an observed
input to this pure checker, not a state mutation.

Raw authorization JSON must cross a strict decoding boundary before signature
verification or contract validation. `validate_authorization_receipt_v2_file`
and `telos-proof validate` reject duplicate decoded keys, including escaped
equivalents, plus `NaN` and infinities. A dict-only validator cannot recover
duplicate-key evidence after a permissive caller has already parsed it. An
integration that receives raw JSON must therefore use one of the strict file or
CLI paths, or an equivalently strict decoder, before canonicalization.

---

## Example 3 -- pre-execution gate and evaluation contract

Both `evaluate_gate` and `evaluate` return a frozen decision object. The gate is
**default-deny / fail-closed**: `allow` only when every applicable check passes;
any check that cannot be positively confirmed becomes `unknown` and the decision
escalates to `needs-human`.
If a request declares a required `human_gap`, the gate likewise escalates until
external operator attestation, an evidence label, and an evidence digest are
present.

```python
from datetime import datetime, timezone
from proof_surface import evaluate_gate

now = datetime(2026, 6, 18, tzinfo=timezone.utc)
receipt = {
    "authorization_version": "0.1", "receipt_id": "ar-demo",
    "kind": "authorization-grant",
    "principal": {"id": "user:alice@example.com"}, "agent": {"id": "agent:planner"},
    "intent": "Read repository files.",
    "scope": {"allowed_actions": ["read_file"], "allowed_targets": ["repo:proof-surface"]},
    "granted_at": "2026-06-17T00:00:00Z", "expires_at": "2099-01-01T00:00:00Z",
    "revoked": False,
}

request = {
    "planned_action": {
        "action_kind": "read_file",
        "target": "repo:proof-surface",
        "estimated_cost": {"tokens": 100},
    },
    "authorization": receipt,
    "budget": {"remaining_tokens": 1000},
}

decision = evaluate_gate(request)
print(decision.decision, decision.checks)

# Drop the budget: estimated tokens with no remaining-budget figure cannot be
# confirmed, so the budget check is "unknown" and the gate escalates.
request_no_budget = {**request, "budget": {}}
print(evaluate_gate(request_no_budget).decision)
```

Expected output:

```
allow {'authorization': 'pass', 'budget': 'pass', 'state': 'not-applicable', 'human_gap': 'not-applicable'}
needs-human
```

The evaluation contract works the same way, but the decision lattice is
`deploy` / `block` / `needs-human`, and it is **uncertainty-aware**: a measured
value whose `± uncertainty` interval straddles the threshold is `uncertain` and
never silently deploys.

```python
from proof_surface import evaluate

contract = {
    "eval_version": "0.1",
    "contract_id": "ec-demo",
    "objective": "Gate deploy on accuracy and latency.",
    "criteria": [
        {"name": "accuracy", "metric": "accuracy_pct",
         "threshold": 90.0, "direction": ">=", "required": True},
        {"name": "p99_latency_ms", "metric": "p99_latency_ms",
         "threshold": 500.0, "direction": "<=", "required": True},
    ],
}

clear = [
    {"name": "accuracy", "measured": 92.3, "uncertainty": 0.5},
    {"name": "p99_latency_ms", "measured": 480.0, "uncertainty": 5.0},
]
print(evaluate(contract, clear).decision)

straddle = [
    {"name": "accuracy", "measured": 90.2, "uncertainty": 1.0},  # 89.2..91.2 straddles 90
    {"name": "p99_latency_ms", "measured": 480.0},
]
result = evaluate(contract, straddle)
print(result.decision, result.per_criterion)
```

Expected output:

```
deploy
needs-human {'accuracy': 'uncertain', 'p99_latency_ms': 'pass'}
```

---

## Example 4 -- delegation chain (build, validate, verify)

A delegation chain roots authority in a **real human** and attenuates scope down
every hop. Bindings are SHA-256 hash-chains; build them with the producer
helpers `compute_binding` (per hop) and `compute_chain_binding` (whole-chain
commitment), then `verify_delegation` re-derives them. The verdict lattice is
`VALID` / `DENIED` / `UNVERIFIABLE`; `effective_scope` and `effective_expiry`
are populated **only** on `VALID`.

```python
from datetime import datetime, timezone
from proof_surface import (
    compute_binding, compute_chain_binding,
    validate_delegation_chain, verify_delegation,
)

hop = {
    "from": {"id": "alice@example.com", "kind": "human"},
    "to": {"id": "agent:planner", "kind": "agent"},
    "scope": {
        "allowed_actions": ["read", "summarize"],
        "allowed_targets": ["repo:proof-surface"],
    },
    "granted_at": "2026-01-01T00:00:00Z",
    "expires_at": "2099-01-01T00:00:00Z",
    "revoked": False,
}
# The binding is computed over the hop WITHOUT its own "binding" key; the root
# hop uses prev_binding="".
hop["binding"] = compute_binding(hop, "")

chain = {
    "delegation_version": "0.1",
    "chain_id": "chain-demo",
    "hops": [hop],
    "chain_binding": compute_chain_binding("chain-demo", 1, hop["binding"]),
}

now = datetime(2026, 6, 18, tzinfo=timezone.utc)
print(validate_delegation_chain(chain))

ok = verify_delegation(chain, action="read", target="repo:proof-surface", now=now)
print(ok.verdict, ok.effective_scope)

bad = verify_delegation(chain, action="delete", target="repo:proof-surface", now=now)
print(bad.verdict)

# Demanding asymmetric-signature assurance with no verifier is honestly
# UNVERIFIABLE -- never a fabricated VALID.
print(verify_delegation(chain, require_signatures=True, now=now).verdict)
```

Expected output:

```
[]
VALID {'allowed_actions': ['read', 'summarize'], 'allowed_targets': ['repo:proof-surface'], 'any_target': False}
DENIED
UNVERIFIABLE
```

> **Integrity caveat (verbatim from the module).** The per-hop `binding` and the
> `chain_binding` are *keyless* SHA-256 hashes: they give self-consistent
> integrity and catch partial corruption and naive truncation/extension, but
> they are **not** tamper-evidence against an adversary who rewrites the whole
> document and recomputes every binding. For real anti-forgery, pin the
> out-of-band `chain_binding` via `pinned_chain_binding`, or verify an
> asymmetric signature per hop via `require_signatures=True` +
> `signature_verifier`.

---

## Conformance vectors

Each contract ships valid and invalid fixtures under its versioned
`conformance/<contract>/<version>/` directory with a `manifest.json`. They are
the canonical
"what a good/bad document looks like" reference and are exercised by the test
suite; read them alongside this guide when you need a concrete shape.

Validate an authorization receipt or organ bundle from the command line:

```bash
python -m proof_surface.cli validate document.json
```

The command prints a typed JSON result. It returns 0 for `MATCH`, 1 for a known
contract that is `UNVERIFIABLE`, and 2 when the document cannot be loaded or its
contract cannot be identified. Ambiguous raw JSON, such as duplicate object
keys or non-finite numeric constants, is a malformed document and returns the
typed `UNVERIFIABLE` result with exit code 2.
