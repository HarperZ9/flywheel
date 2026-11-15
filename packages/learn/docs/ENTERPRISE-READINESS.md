# Learn Enterprise Readiness

`learn` is the enterprise learning-accountability edge: it automates course logistics, runs a real
study loop against an operator's own practice, and halts at every step tagged as graded, at
sensitive fills (credentials, payment details, CAPTCHA), and at submit and cost steps the operator
has not granted.

This guide aligns the flagship with Project Telos context envelopes and action receipts. The goal
is unattended agent work that can be left running and later inspected: what context the agent saw,
what exact material it relied on, what it changed, what verified, and what remained unverifiable.

## Enterprise Role

- Automate course and certification logistics (navigate, click, fill non-sensitive fields, wait,
  capture) while every `assess` step and every sensitive fill halts for the operator, and submit
  and cost steps halt unless the operator grants them for that invocation (`--submit
  witnessed-auto`, `--allow-cost`).
- Run a teach-you learning loop (spaced repetition, retrieval practice, predict-then-observe,
  self-explanation, misconception tracking, prerequisite gating) over the operator's own recorded
  practice, and gate a `mastery` verdict on that practice alone.
- Emit a witnessed, hash-chained receipt that separates automated logistics, human assessment, and
  aid visualizations into structurally distinct channels, so a downstream reader cannot mistake one
  for another.

## Host Commands

- `node src/cli.mjs status` and `node src/cli.mjs doctor` for host readiness; `doctor` re-derives
  every integrity invariant at runtime and reports `MATCH`/`DEGRADED`.
- `node src/cli.mjs run WORKFLOW.json --id ID` and `node src/cli.mjs resume ID --attest NOTE` for
  gated, resumable workflow runs.
- `node src/cli.mjs verify ID` and `node src/cli.mjs receipt ID` for ledger replay and receipt
  emission (JSON, Markdown, HTML).
- `node src/cli.mjs tutor plan|record|due|misconceptions|retrieval|explain|predict|score|path|
  study|study-receipt|mastery` for the learning loop, and `tutor reverify` to recompute an emitted
  receipt's evidence (typed `CHAIN_BROKEN` / `VERDICT_MISMATCH` failures; exit 0 only when clean).
- `learn mcp` (or `node src/mcp.mjs`) for a stdio MCP host: read tools, plus two that write
  tutor sessions inside the learn state folder (`LEARN_HOME`, else a per-user data folder).

## Context Envelope Contribution

- Workflow runs should carry the ledger's own `seq`, `stepKind`, and digest fields as the context a
  downstream agent or reviewer replays against, not a prose summary of what happened.
- Study sessions should be referenced by their own hash-chained `studyReceipt` entries rather than
  re-derived from a paraphrase; the receipt already carries `due`, `mastery`, `misconceptions`, and
  `visualizations` as one coherent, re-checkable snapshot.
- Aid visualizations (`interop/telos.mjs`) carry `provenance: "aid"` and a `scene_spec_hash` /
  `result_hash` pair; a context packet should reference those hashes, not restate the rendered
  content as if it were evidence of learning.

## Action Receipt Contribution

- `receipt/receipt.mjs` emits the input for a `project-telos.action-receipt/v1`-style receipt:
  logistics steps actuated, the human-assessment gate points reached, any witnessed-auto
  submissions and the pre-submit state digest they carry, and aid visualizations, each in its own
  structurally separate section.
- Side-effect class for logistics steps is `read` (navigate/click/fill/waitFor/capture) or
  `external_call` (submit, witnessed-auto only, with operator authorization already recorded).
  `assess` never appears as an actuated side effect; it appears only as a `human-gate` ledger entry.
- Verification verdicts come from `Ledger.verify()` (tamper-evident hash chain) and from
  `doctor()`'s integrity-invariant checks.

## Readability Gate

Enterprise agent output should be easier for the next agent and a human reviewer to continue:

- Keep patches small enough to review and tied to one bounded work item.
- Prefer named helpers and domain terms (`gate`, `ledger`, `witness`, `mastery`) over dense inline
  logic.
- Preserve public interfaces (CLI subcommands, MCP tool names, receipt field names) unless the
  receipt explains why they moved.
- Leave tests, command output, changed files, and next action in the handoff.
- Mark missing source refs, stale sessions, failed tests, and verifier abstentions (`UNVERIFIABLE`)
  as such instead of guessing.

## Platform Boundary

The flagship remains usable alone through CLI JSON and as part of a larger surface through MCP.
IDE, CLI, TUI, and application hosts should consume the same status/doctor/receipt fields rather
than reimplementing flagship behavior. The MCP surface is deliberately advisory-only: it never
performs a real course action, never authors a graded answer, and never moves the mastery-gate
needle on the agent's behalf. That stays operator-driven on the CLI.

See Project Telos `project-telos.context-envelope/v1` and `project-telos.action-receipt/v1` for the
shared cross-tool contract.
