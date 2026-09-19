# Proof Surface (native feature inside Flywheel)

One proof packet per agent action. A checker re-derives the verdict from the evidence and does not read a stored verdict out of the record.

Proof Surface is a stdlib-only Python contract library (repo `public/proof-surface`, package `proof-surface`, MIT). It gives Flywheel two things: nine base validators for AI-workflow records (evidence packets, work-record receipts, authorization receipts, a witness-receipt mirror, a pre-execution gate, an evaluation contract, a claim ledger, a delegation chain, and an organ-receipt bundle), and eleven domain proof-packet wedges reachable through one CLI seam, `telos-proof <domain>`. Each wedge takes evidence a tool already produces and turns it into a validated, content-addressed packet carrying a `MATCH` / `DRIFT` / `UNVERIFIABLE` verdict plus a reviewer report, so a stranger can recompute the verdict from the same evidence. Inside Flywheel today it is not a standalone lane. It is the decision core behind the `accountable-surface` actuation lane and the schema behind Flywheel's organ-receipt handoffs, wired in as a runtime source sibling.

## Integration status (observed)

- Proof Surface has no entry in `harness/lanes_registry.py` `LANES`, so it is not a probeable MCP lane.
- It rides in as `extra_source_repos=("public/coherence-membrane", "public/proof-surface")` on the `accountable-surface` lane (`harness/lanes_registry.py`). `harness/lane_runtime_support.py::extra_import_roots` adds `public/proof-surface/src` to the lane child's `PYTHONPATH`, so the lane imports Proof Surface live even when nothing is pip-installed.
- Runtime coupling is confirmed in code: `accountable-surface` routes every proposed action through `coherence_membrane.membrane.decide`, and `coherence_membrane/membrane.py` calls `from proof_surface import evaluate_gate` and returns `evaluate_gate(request)` (lines 81 and 91). Proof Surface's pre-execution gate is the allow / deny / needs-human logic under the surface's operator-grant seam.
- `harness/lesson_interop.py::lesson_bundle` builds an organ-receipt bundle whose shape is validated by `proof_surface.validate_organ_receipt_bundle`, so Flywheel's organizational-learning-loop handoff is a Proof Surface contract instance.
- `harness/superproject.py` lists it in the `EXTENDED` flagship roster as `Flagship("proof-surface", "agent-action proof packets", "public/proof-surface")` at `tier="declared"` (present in repo, not MCP-probed).
- `harness/classifier_friction_bench.py` uses a `proof_surface_score` text metric. That is a friction-bench scoring term. It does not import this library; do not read it as runtime integration.

Version note (observed): package metadata and the README state `0.2.0`; the in-package constant `proof_surface.__version__` reads `0.1.0`; the contracts themselves are versioned `v0.1`. Treat contract shapes as `v0.1` and subject to change (the repo status says alpha).

## Feature list (each item bound to code)

- **Nine base validators, one import surface.** `proof_surface/__init__.py` exports `validate_packet`, `validate_work_record`, `validate_authorization_receipt` (+ `_v2`), `validate_witness_receipt`, `evaluate_gate` / `validate_gate_request`, `evaluate` / `validate_evaluation_contract`, `validate_claim_ledger`, `validate_delegation_chain` / `verify_delegation`, and `validate_organ_receipt_bundle`. The authorization receipt carries both a `v0.1` and a `v0.2` shape, so ten table rows map to nine contracts.
- **Issues carry a location, empty means valid.** Every validator returns `list[Issue]` where `Issue` has a JSONPath-style `path` and a `message` (`proof_surface/_validate.py`). An empty list is the only "valid" signal; there is no boolean pass flag to trust.
- **Decision helpers are default-deny and fail-closed.** `evaluate_gate` allows only when every applicable dimension positively passes, denies on any `fail`, and collapses any unconfirmable dimension to `needs-human` (`proof_surface/pre_execution_gate.py`, aggregation documented at the top of the file). `check_action` denies a structurally invalid, revoked, expired, or out-of-scope receipt.
- **Authority-shaped content is rejected.** A recursive forbidden-field guard (same `FORBIDDEN_FIELDS` set across authorization receipt, work record, and gate request) strips any field that would let a record assert its own authority. The library never emits `TRUSTED` / `APPROVED` / `AUTHORIZED`.
- **Closed verdict lattices.** Gate verdicts are allow / deny / needs-human; delegation verdicts are `VALID` / `DENIED` / `UNVERIFIABLE`; wedge verdicts are `MATCH` / `DRIFT` / `UNVERIFIABLE`. A demand for signature assurance with no verifier present returns `UNVERIFIABLE`, never a fabricated `VALID` (delegation-chain caveat in the README).
- **Eleven domain wedges over one CLI.** `telos-proof <domain>` dispatches to `agent-action`, `visual-measurement`, `research-claim`, `model-eval`, `optimization-workflow`, `rollout-receipt`, `eval-attempt`, `ai4science`, `conservation`, `control-certificate`, `competition-attempt` (`proof_surface/cli.py::_DOMAINS`). Each wedge also installs a standalone script and a `python -m proof_surface <domain>` form (`pyproject.toml [project.scripts]`).
- **Every wedge run is re-derivable.** A wedge writes six artifacts to `--out`: `packet.json`, `report.md`, `bundle.json`, `crucible-thesis.json`, `crucible-measurements.json`, `crucible-assessment.json` (`proof_surface/agent_action/cli.py`, lines 96-110). An independent checker recomputes the verdict from these.
- **Per-domain honesty gates.** Each wedge names the specific way its claim could be inflated and rejects the packet when that inflation is present (README wedge table): a benchmark that saw the answer is contamination not a pass, a read-only tool cannot claim a hardware calibration, an invariant check must carry a negative fixture that provably breaks it, and simulation-only evidence cannot claim hardware validity.
- **Optional disclosure fields, held honest when present.** `declared_branches[]`, `witness_tier`, `evidence_classes[]`, and `replication` ride the same spine; a fenced branch is not citable support, a promotion rung may not exceed the strongest verifier tier that executed, single-modality evidence caps at the hypothesis rung, and a generalization claim needs two or more independent `MATCH` instances. Omit them and a packet validates unchanged.
- **Adapters for common stacks.** `proof_surface.trace_adapters` normalizes OpenTelemetry and LangSmith / Langfuse traces and imports evidence from MLflow, Weights & Biases, Braintrust, Arize Phoenix, promptfoo, Helicone, DVC, and SLSA / in-toto, declaring via `NON_INFERABLE` what each export cannot supply.
- **Bundle re-check with zero imports.** `telos-proof verify <artifact-dir>` recomputes the content-addressed bundle and returns `MATCH` / `DRIFT` / `UNVERIFIABLE` (`proof_surface/cli.py::_verify_result`); the repo also ships `verify_bundle.py`, a standalone vendored verifier.
- **Zero runtime dependencies.** `dependencies = []` in `pyproject.toml`. JSON Schemas live under `schemas/`, valid and invalid conformance vectors under `conformance/<contract>/v0.1/`, runnable demos under `examples/`. The `test` extra pulls `pytest` and `jsonschema`.

## Stepwise usage (how a user runs it)

Inside a Flywheel checkout, Proof Surface sits at `public/proof-surface`.

1. **Install for development and run the suite.**
   ```bash
   cd public/proof-surface
   python -m pip install -e ".[test]"
   python -m pytest
   ```
   The pytest suite plus the conformance vectors are the verification surface for the current contracts.

2. **Build a proof packet from a shipped example.**
   ```bash
   telos-proof visual-measurement \
     --input examples/visual_measurement/measurement.json \
     --claim "sRGB coverage measured on a read-only capture" \
     --scope "software capture only, no hardware probe" \
     --out ./demo-out
   ```
   The report begins with `**Verdict: MATCH**` and six artifacts land in `./demo-out`. `telos-proof --help` lists all eleven domains. `python -m proof_surface <domain>` is the module-form equivalent.

3. **Validate a single record document.**
   ```bash
   telos-proof validate path/to/document.json
   ```
   Dispatch keys on the document: `organ_bundle_version == "0.1"`, `authorization_version == "0.1"`, or `authorization_version == "0.2"`. An empty issues list prints `MATCH`; issues print `UNVERIFIABLE` with JSONPath locations; an unknown contract or malformed file exits non-zero (`proof_surface/cli.py::_validation_result`).

4. **Re-check an existing artifact directory.**
   ```bash
   telos-proof verify ./demo-out
   ```
   Recomputes the bundle. A missing manifest is `UNVERIFIABLE`; a mismatch is `DRIFT`; a clean recompute is `MATCH`.

5. **Use the Python API directly.** Import the base validators from `proof_surface` and call them; each returns `list[Issue]`. Decision helpers (`evaluate_gate`, `evaluate`, `verify_delegation`, `check_action`) return closed-lattice results.

## Piecewise reference (each capability, what it does)

### Base contracts (`proof_surface`)

| Capability | Entry point | What it does |
| - | - | - |
| Proof-surface packet | `validate_packet`, `PACKET_VERSION` | Validates the neutral evidence/index packet a proof-index consumes. |
| Work-record receipt | `validate_work_record`, `WORK_RECORD_VERSION` | Validates an outward-flowing record of agent work; `additionalProperties: false` at every level; never read back as model state. |
| Authorization receipt v0.1 | `validate_authorization_receipt`, `check_action` | Validates an explicit, least-privilege, expiring, revocable human-to-agent grant; `check_action` is default-deny against action and target. |
| Authorization receipt v0.2 | `validate_authorization_receipt_v2`, `check_action_v2` | Adds nonce, exact time window, revocation flag, and an action budget. Signature trust and atomic consumption stay outside the library. |
| Witness receipt | `validate_witness_receipt`, `WITNESS_VERDICTS` | Consumer-side mirror of EMET's witness-receipt shape and closed verdict lattice, so other tools validate EMET receipts without importing EMET. |
| Pre-execution gate | `evaluate_gate`, `validate_gate_request`, `GateDecision` | Default-deny, fail-closed, advisory allow / deny / needs-human with per-dimension checks; any unconfirmable dimension escalates to needs-human. Reports a decision, grants no authority. |
| Evaluation contract | `evaluate`, `validate_evaluation_contract`, `EvalDecision` | Treats an eval as a deploy gate (deploy / block / needs-human); a measured value whose interval straddles its threshold never silently passes. |
| Claim ledger | `validate_claim_ledger`, `confidence_gate`, `find_conflicts`, `trace_dependents` | Traceable multi-agent memory with source-provided confidence, declared conflicts, and cycle-safe contamination tracing. Reports provenance; does not adjudicate truth. |
| Delegation chain | `validate_delegation_chain`, `verify_delegation`, `compute_binding`, `compute_chain_binding` | Authority rooted in a real human, monotonic scope attenuation per hop, SHA-256 hash-chained with a whole-chain binding. The chain is keyless, so it gives self-consistent integrity, not tamper-evidence against an adversary who recomputes every binding. |
| Organ receipt bundle | `validate_organ_receipt_bundle`, `ORGAN_BUNDLE_VERSION` | Interchange spine tying sibling receipts together by nonzero digest and reference, including TADR classification and control receipts; closed `receipt_kind` vocabulary, no embedded payloads. This is the contract Flywheel's `lesson_interop` handoff conforms to. |

### Domain wedges (`telos-proof <domain>`)

| Wedge | Turns this into a packet | Load-bearing honesty gate |
| - | - | - |
| `agent-action` | an agent trace | admission / side-effects / evidence refs / typed failures / compute leases |
| `visual-measurement` | a read-only color / display measurement | no physical-calibration claim without hardware and mutation evidence |
| `research-claim` | a math / formal proof attempt | a passed kernel replay must disclose axioms, toolchain, source; never a promoted law from one packet |
| `model-eval` | a model + eval set + directional metrics | default-deny promotion; promote only on overall `MATCH` |
| `optimization-workflow` | a solver run vs an exact baseline | a non-executed branch claims no coverage; a surrogate may not self-certify feasibility |
| `rollout-receipt` | an RL / post-training run | reward, verifier, admission, and promotion stay separate |
| `eval-attempt` | a single benchmark attempt | `correct` with ground-truth access is contamination and never a pass |
| `ai4science` | a claim-to-experiment run | no unmeasured discovery claims; independent reproduction required |
| `conservation` | a transformation + declared invariant | the check must carry a negative fixture that provably breaks the invariant |
| `control-certificate` | a stability / feasibility claim | hardware validity is never claimable from simulation-only evidence |
| `competition-attempt` | a competition / judge attempt | source-pinned judge repo; verdicts cite only certificate layers that executed |

### CLI verbs (`proof_surface/cli.py`)

- `telos-proof <domain> [options]` routes to the wedge module; each wedge owns its own arguments and writes the six artifacts.
- `telos-proof validate <document.json>` validates one record by detecting its contract version.
- `telos-proof verify <artifact-dir>` recomputes a bundle and returns the closed verdict.

### Trace adapters (`proof_surface.trace_adapters`)

Normalizes OpenTelemetry and LangSmith / Langfuse traces and imports evidence from MLflow, Weights & Biases, Braintrust, Arize Phoenix, promptfoo, Helicone, DVC, and SLSA / in-toto. Each adapter declares via `NON_INFERABLE` what its source export cannot supply, so a missing field stays an honest null. The adapter never guesses a value.

## Composition tutorial: how it plugs into Flywheel

### Which seam it is

Proof Surface is the **verification-contract layer** other lanes borrow. It runs no orchestration lane of its own. Map it against the `superproject.py` organ model: it is not one of the five spine organs and not a probed lane. It is a source sibling that supplies decision logic and record schemas to lanes that do actuate and orchestrate. Its natural organ neighbor is `verification` (the crucible organ), because a wedge run emits crucible-shaped `thesis` / `measurements` / `assessment` files an independent checker consumes.

### What it consumes from peers

- **Agent traces and tool outputs.** The `agent-action` wedge consumes an agent trace; other wedges consume a color measurement, a benchmark attempt, a solver run, an RL rollout, a scientific claim. In a Flywheel run these come from the acting lane (`relay`, `accountable-surface`) or a benchmark harness.
- **Authorization receipts.** `evaluate_gate` and `check_action` consume the human-to-agent grant that a Flywheel operator issues. `accountable-surface/grant.py` shapes a grant to fit Proof Surface's closed action-authorization schema before handing it across.

### What it emits for peers

- **A gate decision** (allow / deny / needs-human) consumed by the `accountable-surface` actuation lane through `coherence-membrane`.
- **A validated packet plus a reviewer report and a re-checkable bundle** consumed by the `verification` organ and by any reviewer.
- **An organ-receipt bundle** that ties sibling receipts together, consumed by `lesson_interop` and any cross-tool handoff.

### Worked example: the live actuation seam

This composition runs in code today. The `accountable-surface` lane gates every proposed action through Proof Surface:

1. A perception organ in `coherence-membrane` emits a witnessed observation; nothing reaches the model un-witnessed.
2. The lane proposes an action and builds a gate request (`coherence_membrane.membrane.build_gate_request`).
3. `coherence_membrane.membrane.decide` calls `from proof_surface import evaluate_gate` and returns `evaluate_gate(request)` (`membrane.py:81,91`). Proof Surface applies default-deny aggregation: allow only if authorization passes and budget, state, and human-gap are each pass or not-applicable; any `fail` denies; any `unknown` escalates to needs-human.
4. `accountable-surface/certify.py` folds that gate verdict, the re-perceived effector result, and an optional grounding step into one proof token under the oracle label `proof-surface-gate-v1`. The surface never executes; it returns the advisory decision for the operator or runtime to enforce.

Because the `accountable-surface` lane declares `extra_source_repos=("public/coherence-membrane", "public/proof-surface")`, `lane_runtime_support.extra_import_roots` puts `public/proof-surface/src` on the lane child's `PYTHONPATH`, so this chain works from a source checkout with nothing pip-installed.

### Worked example: the learning-loop handoff

`harness/lesson_interop.py::lesson_bundle` takes a list of lessons from Flywheel's organizational-learning loop, builds an `organ_bundle_version: "0.1"` document with entries tied by digest and derivation edges, and that document is validated by `proof_surface.validate_organ_receipt_bundle`. Any tool downstream can re-validate the bundle without importing Flywheel, because the contract is a Proof Surface schema that carries no Flywheel-internal shape.

## What it would take to become a native lane

Proof Surface is a CLI and library; it ships no MCP server (its `[project.scripts]` are all CLI entry points, and there is no `serve`/`mcp` callable). So the honest native-lane path is the **satellite bridge model that `chorus` uses**. A direct `LANES` MCP entry is ruled out. Chorus is likewise absent from `LANES`: it is wired through `harness/chorus_bridge.py`, which shells the installed CLI and returns its JSON verbatim, and `gateway.py` exposes it at `/api/discourse*`. Proposed steps, modeled on that:

1. **Bridge module** (proposed) `harness/proof_surface_bridge.py`: resolve the `telos-proof` argv (console script on PATH, else `python -m proof_surface` when importable), shell it with an injectable `runner` for tests, and return its packet JSON verbatim with a `flywheel.proof-packet/v1` schema wrapper and a named error on a missing CLI or bad input. Copy the `chorus_bridge.py` shape one for one, including the install-gate-behind-runner rule so the seam is testable in CI without the CLI installed.
2. **Gateway route** (proposed): add `/api/proof/<domain>` (and `/api/proof/verify`) handlers in `gateway.py` next to the discourse routes, delegating to the bridge and returning `400` on `error`.
3. **Desktop app card** (proposed): add a Proof Surface card to the desktop lane surface under `desktop/lib`, calling the new gateway routes, matching how the discourse and other lane cards are wired. Honest null: I did not locate a single lane-card registry file in `desktop/lib` during this pass, so the exact card wiring point is unverified and needs a read of the desktop lane-card source before implementing.
4. **Expected-set test** (required if it becomes a `LANES` entry): `tests/test_lanes.py::test_registry_covers_the_expected_lanes` asserts the exact `set(LANES)`. That frozenset is a coordinated invariant. Adding a `LANES` entry means updating that assertion (and `SUPERPROJECT.md` and the portfolio-site count, per the note in `superproject.py`). A bridge-only integration does not touch `LANES`, so it needs a bridge test (`tests/test_proof_surface_bridge.py`, proposed) plus a gateway-route test. The lane-set edit stays untouched.
5. **Payload manifest** (required only if bundled into a frozen gateway): `harness/bundled_lane_expectations.py::EXPECTED_BUNDLED_LANES` pins `source_commit`, `source_manifest_sha256`, `descriptor_sha256`, `module`, and `callable` for a `kind="bundled"` lane. Proof Surface as a source sibling or a shell bridge does not need this. It would only apply if a future step froze Proof Surface into the packaged gateway with its own MCP callable, which does not exist yet.

Boundary held throughout: Proof Surface validates records. It does not grant authority, execute actions, or store private payloads. Promoting it to a lane changes how Flywheel reaches it, not what it is allowed to assert.