# Canon Pillar Improvement Program

Status: Approved for audit. Implementation remains a design draft until the operator reviews the synthesized specification.

Date: 2026-08-30

## Objective

Turn Canon from a tested canonical-record prototype into an open, verifiable continuity layer that lets a person or team move active work between model providers, agent harnesses, APIs, local models, machines, and collaborators without silently losing the project's governing rules, current frontier, decisions, evidence, or operator intent.

Canon must improve two layers at once:

1. Product behavior: capture, curate, compress, inspect, transfer, restore, reconcile, and verify project continuity.
2. Capability environment: leave reusable schemas, adapter contracts, conformance fixtures, benchmarks, threat models, receipts, release gates, and community governance behind.

## Ambient bootstrap requirement

Canon must be designed to participate at the start of every supported agent session, new chat, and project entry. The receiving agent should freshen its context before eagerly beginning task work.

The required lifecycle is:

1. Detect session, chat, project, workspace, branch, or instruction-state entry.
2. Resolve the applicable personal, organization, project, workspace, and session continuity layers.
3. Check freshness, trust, conflicts, target-model budget, and source reachability.
4. Compile or reuse a valid capsule.
5. Present the receiving agent with the capsule and its explicit unknowns or omissions.
6. Require a small continuity readiness probe for critical goals, permissions, prohibitions, and current frontier.
7. Emit a bootstrap witness containing capsule identity, source-state identity, target surface, timestamp, checks performed, omissions, and readiness result.
8. Begin ordinary work only after the bootstrap result is visible.

This is an interoperability contract, not permission to claim lifecycle control a host does not expose. Adapters must publish one of these support tiers:

- **Enforced:** the host exposes a startup hook or equivalent control that can block ordinary work until bootstrap succeeds.
- **Native advisory:** the host can load persistent instructions or a connector that directs the agent to bootstrap first, but cannot technically prevent noncompliance.
- **Guided:** Canon supplies a launcher, project template, import flow, or first-message action that the user initiates.
- **Unsupported:** no safe or documented integration exists; the adapter must say so and provide an export-only fallback.

No adapter may label advisory or guided behavior as enforced. If a required bootstrap fails, the agent-facing surface must not silently continue with apparently fresh context. It must expose whether the failure was caused by missing authority, unavailable local state, stale evidence, a secret quarantine, a conflict, an incompatible budget, or an unsupported host lifecycle.

The audit must determine the strongest truthful integration tier for Claude applications, ChatGPT applications, Codex, Claude Code, OpenCode, Gemini CLI, Cursor, GitHub Copilot, local endpoints, generic APIs, MCP hosts, and A2A agents. It must also specify how launch-time refresh behaves when applications are offline, a provider quota is exhausted, multiple chats start concurrently, a project is opened from a different machine, the workspace is dirty, or the capsule changes during a session.

## Approved architectural direction

The working architecture is a hybrid Continuity Capsule:

- A human-readable, model-native `CANON.md` is the default transfer artifact.
- A deterministic `canon.capsule/v1` manifest supplies typed identity, authority, provenance, freshness, omissions, hashes, and compatibility metadata.
- An optional `.canonpack` preserves records, evidence indexes, and receipts by reference without forcing every target model to ingest the archive.
- Budget profiles provide a small Needle capsule, a normal Handoff capsule, and a reference-complete Archive.
- Lossy synthesis is permitted only when its source spans and transformation receipt remain addressable.
- Normative instructions, permissions, active goals, unresolved conflicts, and explicit unknowns may not be silently summarized away.
- Import, compilation, and export must have a deterministic floor that does not require a hosted model. Optional model-assisted refinement is a pluggable, reviewable enhancement.

## Product maturity thesis

Canon becomes a community pillar by making continuity safe and convenient enough to be the default boundary between AI surfaces. The sprint therefore audits five adoption promises in addition to technical correctness:

1. **Immediate rescue:** a user whose provider quota or session access disappears can make a useful handoff from locally available state.
2. **Fresh before work:** every supported session entry attempts continuity refresh before task execution and produces a witness the user or receiving harness can inspect.
3. **Visible truth:** a user can preview exactly what the next model will know, what was compressed, what was omitted, and why.
4. **Reversible control:** imports, edits, reconciliation, redaction, and export remain local-first, reviewable, and undoable.
5. **Broad access:** the same core workflow works for nontechnical users, keyboard and screen-reader users, constrained-context models, offline environments, and enterprise teams.
6. **Open compatibility:** third parties can implement and test the format without adopting the Canon runtime.

## Audit scope

Six independent lanes will produce evidence-backed reports under `project-docs/audits/2026-08-30/`:

| Lane | Owner output | Required questions |
|---|---|---|
| Core, schema, and I0 | `CORE-SCHEMA-I0-AUDIT.md` | What already exists, how I0 integrates, what the capsule schema and precedence model require, and how compatibility is tested |
| Platform adapters | `PLATFORM-ADAPTER-MATRIX.md` | What every major provider or harness can import/export, which semantics are representable, and where declared loss is unavoidable |
| Security and privacy | `SECURITY-PRIVACY-THREAT-MODEL.md` | What can leak, poison, forge, replay, over-authorize, or persist improperly, and which controls and gates contain those risks |
| Continuity evaluation | `CONTINUITY-BENCHMARK.md` | How to measure retained intent and resumed task quality, not merely token reduction, across frontier and local models |
| Community and release | `COMMUNITY-RELEASE-PILLAR-AUDIT.md` | What packaging, naming, licensing, governance, documentation, CI, provenance, and adoption work is required |
| UX and accessibility | `UX-ACCESSIBILITY-FEATURE-BLUEPRINT.md` | Which workflows make continuity understandable and delightful across abilities, platforms, skill levels, and edge conditions |

## Safety and coordination boundaries

- This audit is read-only except for the six assigned reports and their index.
- Product code, tests, manifests, package metadata, release state, and public services are out of scope until the implementation design is approved.
- The active `codex/full-history-memory-bank-20260830` worktree and its untracked I0 files are user-owned parallel work. They may be inspected read-only and must not be edited, moved, reformatted, staged, or superseded.
- Existing dirty branches in related repositories are evidence, not cleanup targets.
- Secrets, credentials, private databases, browser profiles, unpublished protected material, and raw conversation bodies must not be copied into reports.
- External claims require current primary sources where available. Local claims require file, command, test, or artifact evidence. Everything else is labeled inferred, unknown, or blocked.
- No deployment, publication, package reservation, trademark filing, or default-branch commit is authorized.

## Evidence handoff contract

Every lane report must contain:

1. Scope and inspected evidence.
2. Verified current state, with local paths or primary-source links.
3. Gaps and failure modes, each with severity and confidence.
4. Proposed capability or control.
5. Acceptance tests and measurable gates.
6. Dependencies, conflicts, and sequencing.
7. Explicit unknowns and decisions requiring the operator.
8. A prioritized Now / Next / Later feature or work table.

Recommendations must distinguish:

- `C: verified`: directly supported by evidence.
- `C: inferred`: a reasoned conclusion from cited evidence.
- `C: unknown`: evidence is not yet available.
- `C: blocked`: evidence exists but cannot be obtained within current authority or safety bounds.

## Initial quality gates

The synthesized design must define executable tests for at least these gates:

- Byte-identical deterministic builds from the same normalized inputs and configuration.
- One hundred percent retention of planted active goals, permissions, prohibitions, and unresolved conflicts in the selected budget profile, or an explicit build failure.
- Zero planted-secret transmission across the export boundary in the security fixture set.
- Every lossy statement links to source identity and a transformation receipt.
- Every omission is typed, counted, and visible in both machine and human surfaces.
- Stale, superseded, contradictory, untrusted, and unknown facts remain distinguishable.
- Cross-adapter round trips declare and test semantic loss instead of implying parity.
- Every advertised ambient-bootstrap tier is verified against actual host capabilities, and every successful start produces a bootstrap witness before ordinary task execution.
- Mandatory bootstrap failure is visible and classified; it never degrades silently to an unverified context state.
- Continuity evaluation measures resumed-task correctness, correction burden, tool-use success, latency, resource use, and reproducibility alongside compression ratio.
- Keyboard-only, screen-reader, low-bandwidth, offline, small-context, Windows, macOS, and Linux workflows have explicit acceptance coverage.
- Public releases are reproducible, signed or attestable, secret-scanned, licensed, documented, and backed by conformance fixtures.

## Candidate adoption capabilities to test, not assume

The audits must evaluate rather than automatically accept these product ideas:

- One-command and guided `switch provider` handoff.
- A local continuity flight recorder for decisions, corrections, evidence, and worktree state.
- A Context Doctor for conflicts, staleness, secret risk, unreachable references, and target-budget fit.
- A preview answering, “What will the next model know?” with semantic diff and omission explanations.
- A continuity readiness probe that makes the receiving model prove it recovered critical state before it can proceed.
- Branch-aware three-way continuity merge for parallel sessions and worktrees.
- Personal, project, team, and organization policy layers with explicit precedence.
- Selective-disclosure capsules and sealed evidence archives.
- CI freshness gates and review comments when instructions or decisions change without a capsule update.
- SDKs, JSON Schema, fixture zoo, conformance CLI, and a `Canon Compatible` program.
- Clipboard, file, standard input/output, MCP resource, A2A artifact, accessible HTML, and printable Markdown delivery surfaces.
- Emergency handoff, offline operation, and exact-budget compilation for constrained local models.
- A host-neutral Canon Bootstrap Protocol with startup discovery, freshness checks, readiness probes, and receipts.
- Platform-native startup hooks or instruction adapters where supported, plus truthful guided fallbacks where proprietary app lifecycles are closed.

## Execution DAG

1. Complete the six evidence lanes independently.
2. Validate every report against the handoff contract and evidence standard.
3. Reconcile overlaps, contradictions, I0 boundaries, and active-branch facts.
4. Produce the expanded architecture, capability portfolio, risk register, and release maturity model.
5. Obtain operator review of the design specification.
6. Produce a file-level implementation plan with tests-first tasks and review checkpoints.
7. Implement only after that plan is accepted.

## Definition of audit completion

The audit phase is complete only when all six reports pass validation, evidence conflicts are recorded rather than hidden, the active I0 work is integrated as a dependency rather than duplicated, and the operator receives a coherent design with explicit tradeoffs and decisions.
