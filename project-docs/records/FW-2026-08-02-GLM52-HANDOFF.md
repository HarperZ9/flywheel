<!-- writing-profile: normative-spec -->

# Flywheel engine checkpoint and GLM 5.2 handoff

Date: 2026-08-02

Status: CHECKPOINTED, NOT COMPLETE

This record hands the active engine-completion goal to a new long-running
ZCode/GLM 5.2 session. It separates completed, reviewed work from the remaining
dependency-ordered sprint. It does not claim that the Flywheel engine, release
evidence, public documentation, or outreach surfaces are complete.

## Verified checkpoint

### Flywheel

- Branch: `feat/governance-integration`
- Task 0 implementation head before this checkpoint record:
  `c1aa19453fa199ec5e285fd6964557903050b735`
- Remote: `origin`
- Task 0 spec review: PASS
- Task 0 quality review: PASS
- Task 0 focused suite: 18 passed
- Result: shell-free, bounded, atomic acceptance-command recording with
  byte-preserving redaction, typed launch failure, process-tree timeout, and
  committed-blob checks.

The branch also contains the prior governance integration commit `9c7d86c`.
Audits found fail-open and trust-boundary defects in that code. Treat it as
implementation input, not merge-ready product state.

### Proof Surface

- Branch: `feat/tadr-governance-contracts`
- Reviewed head: `faf6bd47f5b403fd2f8a26e28adf0e67977adbbd`
- Remote: `origin`
- Spec review: PASS
- Quality review: PASS
- Full suite: 721 passed
- Public-surface gate: 348 tracked files, no findings
- Package build: wheel and source distribution succeeded
- Built-wheel CLI: valid TADR and authorization v0.2 MATCH; zero digest,
  duplicate keys, and non-finite numbers are typed UNVERIFIABLE inputs.

Proof Surface now provides:

- preserved authorization v0.1 behavior and fixture bytes;
- strict authorization v0.2 with exact agent, action, target, nonce, issue and
  expiry times, positive action budget, revocation, and optional policy data;
- explicit `tadr-classification` and `tadr-control` bundle kinds;
- nonzero 64-hex bundle digest enforcement;
- strict raw JSON parsing that rejects duplicate decoded keys and non-finite
  numbers before structural authorization validation;
- schema/reference-validator parity corpus and a tracked-file public gate.

Proof Surface does not own trusted-key selection, nonce uniqueness, durable
revocation state, or atomic action consumption. Those remain Flywheel Task 3.

## Evidence index

Compact reviewed receipts are committed under:

`artifacts/closeout/FW-2026-08-02-CLOSEOUT/`

Key groups:

- `task-1-proof-surface-exact-head.json`: final reviewed-head verification
  summary, package hashes, raw receipt hashes, and limitations.
- `task-0-bootstrap/`: recorder pass/fail fixtures.
- `task-1-proof-surface-reviewed/010-*` and `011-*`: initial red contract tests.
- `task-1-proof-surface-reviewed/020-*` and `021-*`: initial focused green tests.
- `task-1-proof-surface-reviewed/210-*` and `211-*`: hostile-input green tests.
- `task-1-proof-surface-reviewed/220-*`: final 721-test suite.
- `task-1-proof-surface-reviewed/222-*`: final package build.
- `task-1-proof-surface-reviewed/236-*`: staged public-surface gate.
- `task-1-proof-surface-reviewed/241-*` through `244-*`: push, head, and clean status.

The larger local evidence tree contains reproducible build directories,
temporary environments, the installed-wheel CLI probes, and negative or verbose
test receipts with machine-specific argv or output. Those bytes are
intentionally not committed. Their verified outcomes are summarized above.
Regenerate them rather than treating environment-specific bytes as a release
artifact.

Exact-head raw receipts stay local when argv contains machine-specific isolated
environment paths. Their hashes and scrubbed outcomes are committed in the
exact-head summary. Checkpoint status, writing, hygiene, commit, and push
receipts also stay local because their content changes while the checkpoint
commit is created.

## Architecture and execution authority

Read these in order before editing:

1. `docs/superpowers/specs/2026-08-02-engine-completion-design.md`
2. `docs/superpowers/specs/2026-08-02-execution-contracts.md`
3. `docs/superpowers/plans/2026-08-02-engine-completion.md`
4. This checkpoint

The execution-contract spec is authoritative where older audit prose differs.
Key decisions already closed:

- `public/flywheel` is the canonical platform and package source.
- `local-model` is a lane, not a second manually maintained platform tree.
- Proof Surface owns the inner authorization and receipt validation contract.
- Flywheel owns trusted signatures, state signing, append-only revocation
  ingestion, atomic action consumption, boot, gateway, and composition.
- Mneme and Relay remain zero-runtime-dependency packages and call the
  process-owner-configured Flywheel verifier command for mutations.
- Six flagship MCP servers, seven Flywheel lanes, and ten Plexus components are
  distinct roster layers.
- The benchmark is an orchestration-stack comparison, not a pure harness-only
  ablation.
- PyPI, npm, model-registry, weight publication, and production release jobs
  remain withheld. Git branches, PRs, merges, and repository-hosted pages are
  allowed after their gates pass.

## Known state and risks

- Do not merge `feat/governance-integration` yet. Its pre-checkpoint governance
  code has known fail-open defaults, embedded-key trust, incomplete state
  hydration, and route-scope defects covered by Tasks 2 through 5.
- Do not weaken the Task 0 recorder or bypass it for implementation, test,
  benchmark, build, render, or acceptance commands.
- Use fresh worktrees from verified `origin/main` for every repository except
  the existing Flywheel branch. Do not merge stale topic branches wholesale.
- Preserve unrelated dirty work and private Telos runtime material.
- Neither current Lean execution path is safe for untrusted input until the
  pinned isolated sidecar exists. Report UNVERIFIABLE rather than overstating
  isolation.
- The measured 14B result is 141/164 base versus 136/164 CPT, delta -3.05
  percentage points, p=0.404. It has one-seed/control and contamination limits.
- The 32B 52/52 result proves restart reproduction only, not model quality.
- External provider or subscription CLI unavailability is a typed unavailable
  row, never a performance failure and never silently removed.
- No active PR has been opened for Tasks 0 or 1. Default branches are unchanged.

## Resume protocol

1. Read workspace and repository instructions, then verify the active goal.
2. Fetch every repository and record base, head, upstream, status, and remotes.
3. Confirm the two branch heads above still match `origin`.
4. Run Task 0 focused tests and one pass/fail recorder fixture.
5. Run the Proof Surface 721-test suite, public gate, build, and installed-wheel
   CLI probes from the exact reviewed head.
6. Start Task 2 only after those receipts MATCH.
7. For every implementation task, use a fresh implementer, then a spec reviewer,
   then a quality reviewer. Fix findings before advancing.

Use `project-docs/records/FW-2026-08-02-LONG-SPRINT-CHECKLIST.md` as the
execution queue.

## Does not prove

This checkpoint proves the committed Task 0 and Task 1 code states and their
recorded gates. It does not prove that remaining governance, infrastructure,
benchmark, package, documentation, visual, CI, merge, or live-site work is
complete. It does not authorize publication to a package or model registry.
