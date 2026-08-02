# Flywheel Closeout Execution Contracts

**Workflow ID:** `FW-2026-08-02-CLOSEOUT`
**Status:** APPROVED BY CONTINUATION, PRE-DISPATCH CONTRACT
**Purpose:** Resolve the integration ambiguities found by validation before any
implementation worker edits product code.

## 1. Canonical source and package boundary

`public/flywheel` is the only canonical Flywheel platform source. It owns the
gateway, boot, governance, lane composition, desktop, benchmark orchestration,
package builder, public evidence pack, site, and demos.

`local-model` is a first-class lane. It owns model roots, serving, training,
model-specific profiles, and weight-adjacent research. Flywheel consumes it
through its declared endpoint and interop contracts. Platform changes are not
manually duplicated into `local-model`.

The existing shared file copies are transitional. Add a drift report that
classifies each copy as:

- `platform_owned`: may exist only in `public/flywheel`;
- `lane_owned`: may exist only in `local-model`;
- `generated_shared_contract`: generated from one named source and checked by
  byte hash;
- `legacy_duplicate`: blocks package acceptance until removed or classified.

All new executable packages are built from `public/flywheel`. Package receipts
must name the Flywheel source commit and the exact local-model manifest/profile
hash they consume. A package built from `local-model` cannot close this
workflow.

Two package classes are explicit:

1. `external-runtime`: excludes model-serving dependencies and states that a
   configured local-model endpoint is required.
2. `full-runtime`: includes the supported serving executable/runtime adapter
   and must pass an isolated install, serve smoke, generation smoke, and
   shutdown/cleanup test.

The full-runtime package is the executable-criterion target. The
external-runtime package is useful but cannot substitute for it.

## 2. Dependency DAG and ownership

```text
Proof Surface kinds and inner authorization
    -> Flywheel authorization state and fail-closed governance
        -> Flywheel boot, gateway, infrastructure, and desktop
            -> Mneme and Relay governed boundaries
                -> owner manifests and Plexus probe
                    -> flagship exact interop and Telos freshness
                        -> cross-harness executor and package
                            -> evidence reports and release preparation
                                -> demos, decks, portfolio, profile
```

| Work unit | Repository/file owner | May not edit |
| --- | --- | --- |
| Proof contracts | Proof Surface task | Flywheel implementation files |
| Authorization, governance, boot, gateway | Flywheel core task | Mneme, Relay, Plexus |
| Cloud IAM, Lean boundary, native label | Flywheel infrastructure task | public derivatives |
| Desktop governance | Flywheel desktop task | engine policy |
| Mneme replay | Mneme task | Relay or Plexus |
| Relay authority/probe/receipts | Relay task | Mneme or Plexus |
| Flagship adapters and owner manifests | Flagship interop task | Plexus loader/probe |
| Plexus loader, lock, probe, self-probe | Plexus task | owner repository adapters |
| Cross-harness executor/package | Flywheel benchmark task | local-model platform copies |
| BuildLang verifier | BuildLang task on a fresh branch from `origin/main` | existing docs topic branch |
| Public user docs | repository-specific doc task after code merge | package publication |
| Projection generator and derivatives | public-release task after evidence merge | product truth or private prospect corpus |

Each work unit uses a fresh non-default branch from verified `origin/main`,
except the existing Flywheel governance branch. No stale post-squash or broadly
diverged branch is merged wholesale.

## 3. Authorization and governance state

### Trusted keyring

Public keys and metadata live in a JSON keyring selected by
`FLYWHEEL_TRUSTED_KEYRING`. The application has no repository-local default
trust anchor. The keyring schema is `flywheel.trusted-keyring/v1`:

```json
{
  "schema": "flywheel.trusted-keyring/v1",
  "keys": [
    {
      "fingerprint": "sha256:<64 lowercase hex>",
      "public_key_pem": "<PEM text>",
      "not_before": "<RFC3339 UTC>",
      "not_after": "<RFC3339 UTC>",
      "status": "active",
      "usage": ["authorization", "governance-state", "revocation"]
    }
  ]
}
```

Allowed statuses are `active`, `retired`, and `revoked`; allowed usages are
`authorization`, `governance-state`, and `revocation`. Verification recomputes
the fingerprint and requires the intended usage. Rotation adds a new active key
before retiring the old key. Revoked keys never authorize a new action or state.

### Signed authorization

The signed wrapper is `flywheel.signed-receipt/v1`; its inner receipt is Proof
Surface's versioned authorization receipt. The inner receipt includes a stable
`receipt_id`, a random 128-bit or stronger `nonce`, `agent_id`, exact action,
exact target, issued time, expiry time, `max_actions`, and optional policy
reference. Embedded public keys never establish trust.

### Atomic usage and revocation store

`harness/authorization_store.py` owns a SQLite database selected by
`FLYWHEEL_AUTHORIZATION_DB`. There is no repository-local default. Tables:

```sql
CREATE TABLE authorization_usage (
  receipt_id TEXT PRIMARY KEY,
  nonce TEXT NOT NULL UNIQUE,
  actions_used INTEGER NOT NULL,
  max_actions INTEGER NOT NULL,
  expires_at TEXT NOT NULL,
  last_action_at TEXT NOT NULL
);

CREATE TABLE authorization_revocations (
  receipt_id TEXT PRIMARY KEY,
  revoked_at TEXT NOT NULL,
  reason TEXT NOT NULL,
  source_ref TEXT NOT NULL
);

CREATE TABLE authorization_revocation_imports (
  issuer_fingerprint TEXT NOT NULL,
  issuer_sequence INTEGER NOT NULL,
  bundle_sha256 TEXT NOT NULL UNIQUE,
  imported_at TEXT NOT NULL,
  PRIMARY KEY (issuer_fingerprint, issuer_sequence)
);
```

Each action executes `BEGIN IMMEDIATE`, checks trusted signature, expiry,
revocation, nonce identity, action, target, agent, and `actions_used <
max_actions`, increments usage, and commits before calling product code. A lock,
I/O, schema, corruption, or unavailable-store error denies the action. Concurrent
calls cannot both consume the same final allowance. The action ledger records a
hash of the authorization decision but never private key material.

### Governance state writer and reader

`FLYWHEEL_GOVERNANCE_STATE` selects a signed JSON state file outside the
repository. Only the exact-scope classification and compliance endpoints may
write it, after trusted authorization is atomically consumed. Writes use a
same-directory temporary file, fsync, and atomic replace. The state includes
classification, control receipt, signature wrapper, written time, expiry, and
source receipt identifiers.

The state file is a `flywheel.signed-receipt/v1` wrapper with exactly
`schema`, `inner_receipt`, and `signature`; `inner_receipt` has schema
`flywheel.governance-state/v1`. The inner receipt is serialized as
`flywheel.canonical-json/v1`: UTF-8 JSON,
object keys sorted by Unicode code point, no insignificant whitespace, integers
only for numeric fields, and no duplicate keys, NaN, infinities, or negative
zero. The signature covers exactly the canonical `inner_receipt` bytes.
`FLYWHEEL_GOVERNANCE_SIGNER_CONFIG` selects an operator-owned
JSON file outside the repository with schema `flywheel.signer-command/v1`, an
argv array, an expected active key fingerprint, and a timeout. Flywheel sends
the canonical payload bytes on stdin without a shell. The signer returns one
`flywheel.signed-receipt/v1` JSON object on stdout. Flywheel rejects extra
output, fingerprint mismatch, nonzero exit, timeout, malformed output, or a key
that is not active in the configured keyring. Production code never accepts a
private key, signer command, or signer configuration from an API request. Tests
use a process-owner-injected signer and ephemeral test keys only.

Revocation ingestion is append-only and authenticated. The command
`flywheel governance ingest-revocations --bundle <path>` accepts a
`flywheel.revocation-set/v1` payload wrapped in
`flywheel.signed-receipt/v1`. Its canonical payload contains issuer
fingerprint, strictly increasing issuer sequence, issued time, source digest,
and entries with receipt id, revoked time, and reason. The wrapper must verify
against an active key whose keyring usage includes `revocation`; the source
digest must match the imported bytes. One `BEGIN IMMEDIATE` transaction records
the import digest and inserts new revocations. A repeated identical import is
idempotent. A sequence rollback, conflicting receipt row, unavailable store,
signature failure, revoked signer, or malformed bundle rejects the whole
transaction. There is no delete or un-revoke operation. The store adds an
`authorization_revocation_imports` table keyed by issuer and sequence so replay
and rollback remain detectable.

Boot reads and verifies the state against the keyring, revocation store,
classification/control schemas, internal references, and freshness. Default
maximum age is 24 hours and can only be shortened by configuration. Missing,
malformed, stale, revoked, or unavailable state produces a typed paused envelope.
Boot does not consume an action allowance because it observes state rather than
performing an authorized mutation.

### Standalone consumer verification

Mneme and Relay remain zero-runtime-dependency packages. Their standalone MCP
servers obtain authority through a process-owner-configured verifier command,
never through caller-supplied configuration. `FLYWHEEL_GOVERNANCE_VERIFY_COMMAND`
contains a JSON argv array for an installed `flywheel governance
consume-authorization --json` command. The consumer sends the signed receipt
plus expected agent, exact action, exact target, and request digest over stdin;
the Flywheel process performs trusted-key verification and atomic consumption,
then returns one typed decision over stdout. Invocation never uses a shell and
has a fixed timeout and output limit. Missing configuration, process failure,
timeout, malformed output, non-MATCH verdict, or receipt/request mismatch denies
the mutation before product code runs. Library embedding may inject the same
verifier protocol at process construction time for tests or a trusted host, but
no MCP request may replace it or raise its authority. Read-only operations that
do not require authority remain available under their documented policy.

## 4. Roster layers and portable manifests

Three rosters have distinct names:

- **Six flagship MCP servers:** Gather, Crucible, Index, Forum, Learn, Telos.
- **Seven Flywheel lanes:** the six flagship servers plus local-model.
- **Ten Plexus components:** the seven lanes plus Mneme, Relay, and Plexus.

Plexus self-probes its own status/doctor surface and reports the result under the
same receipt contract.

Every owner repository ships `*.interop.json` as package data. Plexus runtime
discovery uses this precedence:

1. explicit `--manifest-dir` or configured manifest paths;
2. installed Python entry points in group `plexus.manifests`;
3. a packaged locked aggregate generated during the Plexus release build.

Node-owned manifests enter the locked aggregate through the release generation
command. The lock records owner repository, component version, source commit,
source manifest SHA-256, and bundled manifest SHA-256. CI regenerates into a
temporary directory and fails on drift. Runtime behavior never assumes a
particular workspace root.

Language-neutral conformance vectors exercise each producer. Python and Node
producer runners write bundles to a temporary artifact root; Proof Surface
validates those files as a separate process. No sibling source import is a
release gate.

## 5. Cross-harness executor, oracle, and output contracts

### Exact role semantics

- `codex_harness`: one direct `codex exec` invocation using the official CLI,
  exact model request, read-only sandbox, ephemeral session, fixed timeout, and
  captured JSONL/last-message output.
- `flywheel_harness`: the same Codex CLI backend and model request used as the
  proposer inside `RouterAgent` and `local_loop.run_agent`; Flywheel owns tool
  interpretation, policy, tool receipts, ledger, and verification.

This is an **orchestration-stack comparison**, not a pure harness-only model
ablation, because both paths depend on the Codex CLI and its opaque internal
behavior. Public reports must use that name. A pure harness-only ablation remains
unavailable unless the identical Spark model is exposed through a lower-level
endpoint that both harnesses can call under identical controls.

For paired attempts, both roles receive identical task prompt bytes, read-only
workspace snapshot, allowed-tool declaration, timeout, max-output budget, and
model request. Randomness support is recorded as `controlled`, `unsupported`,
or `unknown`; an unsupported CLI seed is never reported as fixed.

### Adapter interface

```python
class CrossHarnessAdapter(Protocol):
    role: str

    def availability(self) -> dict: ...

    def execute(self, request: "AttemptRequest") -> "AdapterResult": ...

@dataclass(frozen=True)
class AttemptRequest:
    run_id: str
    task_id: str
    prompt: str
    model_id: str
    workspace_snapshot: str
    tool_policy: dict
    repetition: int
    timeout_seconds: int

@dataclass(frozen=True)
class AdapterResult:
    status: str
    output_text: str
    tool_trace: list[dict]
    elapsed_ms: int
    model_observed: str
    randomness_control: str
    failure_class: str
```

### Independent oracle

`harness/cross_harness_oracles.py` owns deterministic task-completion checks.
Each task gains an `oracle` object naming a versioned checker and its expected
artifact schema. Checkers operate on raw output and produced artifact bytes,
never on a provider's self-score. A model-generated rubric can be retained as a
secondary observation but cannot set completion or acceptance.

The 24-row pilot uses four fixed oracle families:

- Index failure-class enumeration and receipt verification.
- Shared-task artifact schema, required hash fields, and forbidden-claim scan.
- Paired friction result with exact mode/task keys and denominator.
- Documentation maintenance diff with code-derived link and claim checks.

If a task lacks a deterministic oracle, its attempt is `UNVERIFIABLE` for task
completion and excluded from completion comparisons.

### Attempt and run outputs

One CLI owns the pipeline:

```text
harness cross-harness-execute --manifest <manifest.json> --artifact-root <root> --tasks <csv> --roles <csv> --repetitions <n>
```

It writes:

- `run.json`: `harness.cross-harness-run-receipt/v1`;
- one directory per role/task/repetition containing prompt, output, tool trace,
  resource observation, oracle result, attempt receipt, metrics, and limitations;
- `artifact-index.json` with SHA-256 for every output;
- `comparison-input.json` consumed directly by the comparison synthesizer;
- `closed-loop-seed.json` consumed directly by the outcome synthesizer.

The executor runs compatibility tests against both synthesizers before live
execution. Resource sampling uses a bounded process sampler and `nvidia-smi`
where available. Unsupported token/cost/resource fields are explicit nulls with
reason codes.

## 6. TADR and Lean public boundary

The private manual is not a reproducible public standard. Flywheel checks in a
Flywheel-owned derived schema and a provenance note that identifies the doctrine
version and source hash without a local path. Public wording is limited to
"selected concepts derived from operator-provided TADR-2026 v1.0 doctrine."
Flywheel does not claim certification, official standard status, or full manual
conformance.

Both `lean_oracle` and `infra/lean_adapter` currently launch a local Lean
executable. Product wiring does not make either path safe for untrusted input.
Until a pinned isolated sidecar is configured and verified, untrusted Lean input
is refused and promotion remains UNVERIFIABLE. Trusted local-artifact checks must
record the trust declaration, toolchain identity, source hash, imports, axiom
and admitted-hole checks, timeout, and isolation state.

## 7. Public projection and generation contract

`project-docs/outreach/public-projection.json` is an explicit allowlist. Its
schema is `flywheel.public-projection/v1`:

```json
{
  "schema": "flywheel.public-projection/v1",
  "product_commit": "<40 lowercase hex>",
  "inputs": [{"path": "<relative>", "sha256": "<64 lowercase hex>"}],
  "outputs": [{"path": "<relative>", "kind": "html|pdf|player|transcript|media"}],
  "privacy_profile": "public",
  "forbidden_roots": ["dispatch-ready", "job-applications-private", "deliverables"],
  "required_checks": ["claim", "path", "secret", "writing", "render"]
}
```

`scripts/build_public_projection.py` reads only allowlisted inputs, refuses paths
outside the configured public source roots, invokes named existing generators or
renderers with argv arrays, and writes `public-projection.receipt.json` containing
input/output hashes, command hashes, tool versions, product commit, timestamps,
and check results. It cannot write the private client package. Private generation,
if later authorized, uses a separate manifest and output root.

Viewport and PDF inspection receipts record surface, viewport or zoom, renderer,
image/PDF hash, clipping/overflow/contrast/focus/reduced-motion results, inspector,
and timestamp. One human or visual-agent inspection remains required for every
distinct layout class.

The current verified demo-path denominator is one of ten transcripts with a
drive-qualified path, the Telos showcase. Generated players and source scripts
are scanned separately. No broader denominator is claimed without a saved scan
receipt.

The target-state public core statement may be rendered only after upstream
governance, health, and adapter acceptance passes.

## 8. Release and publication boundary

Authorized in this workflow:

- code and documentation commits;
- non-default branch pushes;
- pull requests, review fixes, terminal-green CI, merges, and live default
  verification;
- GitHub Pages updates that follow from merged repository content;
- version proposals, changelogs, dry-run packages, checksums, SBOMs,
  provenance, and `READY_TO_RELEASE` records.

Withheld without a separate operator instruction:

- PyPI, npm, Hugging Face, package-registry, or model-weight publication;
- triggering a production release workflow;
- creating a public release whose workflow uploads a package;
- professional-network, prospect, client, or outbound message sends;
- production deployment outside repository-hosted documentation pages.

No acceptance criterion requires a withheld action. A prepared release ends at
`READY_TO_RELEASE` with the exact withheld command recorded but not run.

## 9. Evidence destinations and command receipts

All implementation and acceptance commands are executed through
`scripts/run_acceptance_command.py`, which records argv, cwd as a repository-
relative identifier, start/end/duration, exit code, stdout/stderr files and
hashes, source repository and HEAD, environment-variable names without values,
and a `does_not_prove` statement.

The recorder is Task 0 and lands before all product changes. It accepts argv as
a JSON array or repeated argument, invokes without a shell, redacts configured
secret values from captured streams, records environment names only, and fails
if the artifact root is outside the configured public evidence root. Every
later plan command block is recorder input; the displayed command is the inner
argv, not permission to bypass the recorder.

Durable workflow evidence lives under:

```text
artifacts/closeout/FW-2026-08-02-CLOSEOUT/<run-id>/
```

The public artifact index uses repository-relative paths. Scratch copies may
use machine paths but are never public evidence authority.

Required full gates:

- full repo-local suites for every changed repository;
- full Flywheel Python gates and Flutter analyze/test/build;
- full BuildLang fmt/test/release build;
- Proof Surface conformance;
- cross-language producer conformance;
- both external-runtime and full-runtime package doctors and isolated smokes;
- endpoint gates and the 24-row pilot before the 84-attempt matrix;
- claim, public-instruction, writing, secret, link, package, and render gates;
- clean-worktree assertion after generated outputs are committed or excluded.

## 10. Revalidation acceptance

Implementation dispatch may start when a validator confirms:

- canonical source and package input are singular;
- dependency and file ownership are non-overlapping;
- authorization state and concurrency fail closed;
- roster terms and installed manifest discovery are portable;
- executor roles, deterministic oracles, outputs, and synthesizer inputs are
  exact;
- TADR and Lean copy cannot overstate public or safety posture;
- projection generation is allowlisted, receipted, and downstream-only;
- package publication remains withheld;
- every acceptance command has a durable evidence destination.
