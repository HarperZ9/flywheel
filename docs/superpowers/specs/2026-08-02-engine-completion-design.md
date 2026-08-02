# Flywheel Engine Completion and Public Release Design

**Workflow ID:** `FW-2026-08-02-CLOSEOUT`

**Status:** APPROVED BY CONTINUATION

**Approval evidence:** The operator approved implementation in the recovered
ZCode session with "Let's implement the deferred tasks", "Let's implement the
deferred task", and the active goal listing the remaining enterprise-product
work. The current Codex goal explicitly requests a long-horizon one-shot
completion, verification, commit, push, live-remote update, and full public
documentation and outreach refresh.

## Objective

Finish the receipt-backed Flywheel engine and its capability environment as one
cohesive enterprise product. Close the remaining governance and cross-lane
integration gaps, verify the executable and model endpoint paths, preserve raw
benchmark evidence, bring mneme, relay, and plexus to an evidence-backed public
readiness state, and align every affected public surface with what the code can
currently prove.

## Product Boundary

Flywheel is the platform. Gather, Crucible, Index, Forum, Learn, Telos, and the
local-model proposer/verifier are lanes. Mneme, Relay, and Plexus are integral
infrastructure modules. State-domain material remains private and is not copied
into public repositories. Public claims must be backed by code, schemas, tests,
receipts, reproducible commands, or clearly labeled limitations.

## Global Constraints

- No secrets, `.env` data, tokens, private keys, browser profiles, protected
  corpus material, or private state-domain artifacts may enter a public diff.
- No production deployment or professional-network send is authorized by this
  design. Git commits, pushes, pull requests, merges, and GitHub Pages updates
  requested by the operator are in scope.
- Never force-push. Verify the exact remote base, head, and target before every
  merge or live-remote update.
- Wait for required CI to reach a terminal green state before calling a remote
  flow complete.
- No learned model decides an accept verdict. Checkers and explicit policy gates
  decide; models may propose.
- No receipt, no accept. Honest nulls, denominators, coverage, failure modes, and
  `does_not_prove` statements remain visible.
- TADR consequence tiers are distinct from verifier strength and incident
  severity.
- Existing public voice rules apply: two type families, verdict-only color,
  feature-first prose, ASCII punctuation, no em dashes, and no unsupported
  superlatives.
- Preserve unrelated working-tree changes. The existing modified
  `project-docs/wiki/sessions/2026-07-30-e184752b.md` is outside this workflow
  unless later evidence proves otherwise.

## Requirements

### R1. Recover and map the prior session

- Reconstruct user decisions, research, plan, todos, edits, tests, branches,
  commits, PRs, CI results, and incomplete flows from the ZCode database,
  rollout log, tool artifacts, subagent outputs, scratch areas, and git state.
- Record verified facts separately from inferred or unknown facts.
- Use Index for the workspace map and Forum for cross-domain routing.

### R2. Complete and harden governance integration

- Audit the existing TADR core, control baseline, signed-receipt, cloud IAM,
  native kernel, Lean adapter, and governance integration commits against the
  recovered design and the current code.
- Complete the TADR fields in the run BOM, incident sheet, correlator, and trust
  model where the approved design requires them.
- Complete `tadr-classification` and `tadr-control` proof-spine support with
  schemas or closed receipt kinds, mappers, conformance evidence, and tests.
- Provide a governance envelope at boot without breaking older boot packets.
- Provide authorized gateway access for tier classification, compliance, and
  generic lane tool calls. Fail closed on missing or insufficient authority.
- Provide the native Governance desktop view with defensive parsing, visible
  drift/null states, and clean Flutter analysis and tests.

### R3. Complete cross-lane and infrastructure interoperability

- Verify or complete the canonical lane roster and health/probe behavior.
- Bring Plexus manifests and live probe mode in line with all flagship lanes and
  the approved infrastructure modules.
- Verify Mneme replay/memory interop and Relay transport/injection robustness
  against the shared receipt and governance contracts.
- Prefer existing MCP, receipt, manifest, and adapter primitives over a new bus
  or duplicate framework.

### R4. Verify harnesses, endpoints, packaging, and benchmarks

- Locate and validate existing benchmark artifacts before adding new ones.
- Document reproducible Codex-harness, Flywheel-harness, and local-model methods
  on the same task set where evidence permits.
- Report task quality/completion, latency, resource or cost use, reliability,
  tool-use success, failure modes, denominators, limitations, and raw artifact
  paths.
- Verify local endpoint and agentic workflow support for available 14B, 32B, and
  other local models across practical Codex, Flywheel, Claude Code, and OpenCode
  adapters.
- Verify the executable path, model profiles, endpoint configuration, benchmark
  execution, and artifact reproduction. Build or repair only the gaps that
  evidence identifies.

### R5. Produce the required readiness and experimental record

- Workspace context map.
- Tool integration report.
- Harness architecture and endpoint report.
- Benchmark methodology and Codex-versus-Flywheel comparison.
- Local-model benchmark summary.
- Mneme, Relay, and Plexus readiness reports with shipped changes.
- 14B/32B naming and publishing plan without publishing models before gates.
- Experimental outcome document.
- Capability catalog and roadmap updates.
- Next recursive improvement loop with system and capability-environment gains.

### R6. Refresh public documentation and release surfaces

- Inventory every affected repository's README, usage guide, changelog, examples,
  API/CLI/MCP references, security posture, troubleshooting, integration paths,
  ownership, limitations, and release notes.
- Update only claims that can be verified against current code or commands.
- Keep CLI, MCP, HTTP, Python/Node/Rust API, desktop, and package surfaces aligned.
- Update the GitHub profile and portfolio only after the referenced repository
  states are live and verified.

### R7. Rebuild public outreach, demos, and decks

- Inventory existing prospect packages, value analyses, demos, screenshots,
  recording scripts, and slide decks before creating replacements.
- Produce one coherent narrative for individual, organizational, open-source,
  and closed-source workflows, with separate evidence and limitation slides.
- Reuse the public design and voice canon and scrub local paths, private data,
  credentials, and unverified claims.
- Render and inspect visual artifacts at their intended sizes before release.

### R8. Review, integrate, and close the live flow

- Use test-first development for every new behavior or bug fix.
- Run repo-local full suites and public-surface, writing, secret, packaging, and
  reproducibility gates proportional to each change.
- Perform task-level and final cross-repository reviews.
- Commit intentionally on non-default branches, push, create PRs, wait for CI,
  merge with expected-head protection, fetch the merged defaults, and verify
  live commit identity. Never stop at "push succeeded".
- Update the spec, capability catalog, roadmap, and evidence ledger to reflect
  actual shipped state, deviations, remaining limits, and the next loop.

## Architecture

The architecture remains a receipt-backed composition rather than a new
monolith. Each lane or infrastructure module retains its focused CLI/MCP/API
surface. Flywheel composes them through a canonical manifest, a gated MCP client,
context and governance envelopes, and proof-spine receipt kinds. The native
desktop reads those engine surfaces and never duplicates policy or verification
logic. Plexus discovers and probes capabilities. Mneme persists and replays
witnessed memory. Relay carries typed envelopes across boundaries. Independent
checkers and conformance vectors keep public claims re-derivable.

## Data Flow

1. Index maps code, docs, repositories, and dependency evidence.
2. Gather records research inputs and provenance.
3. Forum routes work and records the causal ledger.
4. Flywheel boots context plus governance state and admits a lane/tool call.
5. The lane proposes or transforms state.
6. Crucible or another independent checker measures the submitted artifact.
7. Proof Surface validates the closed receipt contract.
8. Relay transports typed receipts; Mneme stores and replays the witnessed chain;
   Plexus updates capability discovery and health.
9. Docs, demos, decks, and release reports render only verified public state.

## Error Handling

- Missing optional dependencies or endpoints produce typed unavailable or
  unverifiable results, not fabricated success.
- Missing, malformed, expired, or insufficient authorization fails closed.
- A down lane degrades the roster and reports evidence; it does not crash the
  whole platform.
- Schema drift, stale manifests, failed probes, and replay mismatches remain
  explicit and block release claims that depend on them.
- CI, remote, or deployment failures remain active work until terminal or
  honestly blocked with receipts.

## Coordination Plan

| Workstream | Scope | Depends on | Handoff |
|---|---|---|---|
| A | Flywheel and Proof Surface gap audit | R1 | Markdown evidence report |
| B | Mneme, Relay, Plexus readiness audit | R1 | Markdown evidence report |
| C | Flagship lane docs and interop audit | R1 | Markdown evidence report |
| D | Harness, endpoint, packaging, benchmark audit | R1 | Markdown evidence report |
| E | Outreach, demo, deck, profile, portfolio audit | R1 | Markdown evidence report |
| F | Referenced research verification | R1 | Markdown source and claim map |
| G | Implementation and task reviews | A-F | Commits, tests, review reports |
| H | Cross-repo integration and live remote closure | G | PR/CI/merge receipts |

Every handoff must name verified facts, assumptions, exact artifact paths,
commands or sources, gaps, and acceptance checks. Discovery agents are read-only.
Implementation agents own explicit repositories or files and must not revert
other work.

## Acceptance Criteria

- Every explicit requirement maps to an artifact and a fresh verification
  receipt in the completion checklist.
- No required repo has unreviewed workflow-owned changes or an open workflow PR.
- Required local suites pass, required GitHub checks are green, and merged live
  defaults resolve to the expected commits.
- Public docs and visual artifacts contain no secret-shaped content, local-only
  paths, stale product identities, unsupported claims, or em dashes.
- The final experimental outcome distinguishes result, limitation, and next
  falsifiable action.
- The updated spec reports actual implementation status and any deviation from
  this design.
