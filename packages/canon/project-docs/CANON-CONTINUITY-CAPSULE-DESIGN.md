# Canon Continuity Capsule Design

Status: APPROVED FOR IMPLEMENTATION PLANNING

Date: 2026-08-30

Scope: Synthesis of the validated Canon Pillar audit set. The operator approved this architecture on 2026-08-30. The approval authorizes detailed implementation planning; execution follows the reviewed plan handoff. It does not authorize edits to the active I0 worktree, publication, deployment, package registration, provider claims, or release work.

## Executive Product Thesis

Canon should become a local-first continuity capsule and record format for AI agent work. Its job is not to make memory feel magical; its job is to make handoff state inspectable, deterministic, portable, reversible, and honest about what was freshened, compressed, omitted, blocked, or lost.

The product promise is narrow and strong: before a supported new chat, project, app session, harness run, API request, or local endpoint task begins ordinary work, Canon attempts to freshen the relevant continuity state, produces a visible bootstrap result, and records a witness. That promise is enforceable only where Canon or the host can actually block first work. Everywhere else it must be labeled Native advisory, Guided, or Unsupported.

Recommended near-term product shape: **ship the deterministic local spine first: `canon.atom/v1`, `canon.capsule/v1`, generated `CANON.md`, Context Doctor, preview, readiness probe, bootstrap witness, import review, rescue handoff, undo, adapter descriptors, and conformance fixtures. Do not ship public ecosystem or enforced-provider claims until the fixtures prove them.**

## Source Attribution

| Source | Role in this synthesis | Key contribution |
|---|---|---|
| `P: project-docs/SPEC-CANON-PILLAR-20260830.md` | Governing spec | Objective, ambient bootstrap lifecycle, capsule direction, audit gates, no-implementation boundary. |
| `P: project-docs/audits/2026-08-30/CORE-SCHEMA-I0-AUDIT.md` | Core/schema/I0 lane | Current Canon baseline, atom/capsule proposals, I0 protected-inventory boundary, precedence/freshness model, conformance fixtures. |
| `P: project-docs/audits/2026-08-30/PLATFORM-ADAPTER-MATRIX.md` | Platform lane | Support-tier vocabulary, adapter contract, per-host import/export surface, loss cases, cross-platform failure modes. |
| `P: project-docs/audits/2026-08-30/SECURITY-PRIVACY-THREAT-MODEL.md` | Security/privacy lane | Trust labels, default-deny import, FilesBackend path blocker, archive safety, disclosure, retention, concurrency, telemetry constraints. |
| `P: project-docs/audits/2026-08-30/CONTINUITY-BENCHMARK.md` | Benchmark lane | `canon_continuity_gauntlet_v1`, planted normative/secret fixtures, readiness probes, metrics, round trips, artifact layout, local 14B/32B blockers. |
| `P: project-docs/audits/2026-08-30/COMMUNITY-RELEASE-PILLAR-AUDIT.md` | Community/release lane | Naming/package collision risk, release maturity ladder, governance, licensing, conformance program, CI/SBOM/signing requirements. |
| `P: project-docs/audits/2026-08-30/UX-ACCESSIBILITY-FEATURE-BLUEPRINT.md` | UX/accessibility lane | User journeys, surface blueprint, minimum lovable workflows, accessibility gates, conservative closed-app copy. |
| `P: project-docs/audits/2026-08-30/VALIDATION-REPORT.md` | Cross-lane validator | Pass-with-conditions verdict, V-C1 adapter mismatch, V-C2 stale external claims, V-C3 local-model evidence conflict, V-C4 blocked full workspace index evidence. |

## Verified Current Baseline

| Area | Verified current state | Claim state |
|---|---|---|
| Canon package | Local package metadata is `name = "canon"`, `version = "0.0.0"`, Python `>=3.11`, FSL-1.1-MIT, no runtime dependencies, no console scripts. | C: verified by `pyproject.toml` and validation spot-check. |
| Tests | `python -m pytest -p no:cacheprovider` in the repository root passed `407 passed in 1.45s` during this synthesis. | C: verified. |
| Record core | `canon.record/v1` exists with five kinds: `personality-block`, `episodic-memory`, `synthesized-persona-l3`, `adr-decision`, `research-artifact-ref`. | C: verified, `P: src/canon/schema.py`. |
| Scopes | Current record scopes are exactly `global` and `workspace`; `repo` is deliberately absent. | C: verified, `P: src/canon/schema.py`. |
| Existing surfaces | Current catalog rows are Claude Code global `CLAUDE.md`, Claude Code workspace `CLAUDE.md`, Codex workspace `AGENTS.md`, and Hermes workspace `SOUL.md`. | C: verified, `P: src/canon/registry.py`. |
| Current fidelity tools | Canon has deterministic schema round trips, textblock/vault fidelity, drift checks, persona thesis basis checks, and V4 reconcile gates. | C: verified by Canon source/tests and `CLAUDE.md`. |
| Missing pillar features | No implemented `canon.capsule/v1`, `canon.atom/v1`, generated `CANON.md`, `.canonpack`, bootstrap witness, readiness probe, adapter descriptors, user CLI, MCP server, desktop launcher, browser companion, IDE extension, import wizard, or preview UI was observed outside planning docs. | C: verified by bounded `rg` spot-check and audit validation. |
| I0 | The active I0 worktree is a protected full-history inventory/reference pipeline with untracked design, CLI, source, and tests. It is not mainline product state and must not be edited or promoted automatically. | C: verified by Core and validation; C: blocked for private real-run outputs. |
| Workspace map | A broad index inventory can provide workspace orientation, but the complete retained Index workspace graph/context evidence remains blocked for this design and must not be treated as a full source map. | C: blocked per validation condition V-C4. |
| Registry/provider facts | Package registry, provider, and competitor facts are time-sensitive. The community/platform lanes list current checks, but public decisions require fresh retained receipts. | C: conditional pending fresh receipts. |
| 14B/32B release evidence | Release docs mark endpoint gates and benchmark evidence pending/missing; a 14B CI artifact exists with no uplift claimable at that N. Treat as a release evidence conflict. | C: blocked until release-owner reconciliation. |

## Planned Capability Baseline

| Capability | Baseline today | Proposed target |
|---|---|---|
| Portable continuity artifact | Current managed instruction regions only. | Deterministic `canon.capsule/v1` plus human `CANON.md`, optional `.canonpack` by reference. |
| Rich continuity semantics | Five memory/decision/artifact record kinds. | `canon.atom/v1` with active goals, permissions, prohibitions, constraints, frontier state, conflicts, unknowns, evidence refs, omissions, transform receipts, adapter capabilities, bootstrap probes, and witnesses. |
| Startup freshening | No implemented ambient bootstrap. | Host-specific bootstrap state machine with witness and readiness proof before ordinary work where enforceable, advisory/guided warning where not. |
| User workflow | No tracked CLI/MCP/desktop/browser/IDE workflow. | CLI first, MCP read-only resources/tools second, desktop/browser/IDE after core fixtures prove behavior. |
| Loss handling | Backend declared drops and fidelity ledgers exist in narrow paths. | Every target adapter declares loss, every lossy transform has a receipt, every omission is typed/countable/visible. |
| Security and privacy | Good local patterns, but no capsule trust/disclosure/retention model and one critical FilesBackend blocker. | Default-deny import, trust labels, disclosure labels, secret/PII policy, retention/tombstone/purge model, safe archive preflight, concurrency locks, FilesBackend validation fix. |
| Evidence | Main suite passes; audit reports are planning evidence. | Dry-plan gates, continuity gauntlet, adapter round trips, local endpoint gates, live runs only after approval. |
| Public release | New public prototype with name/package/license/governance/CI gaps. | Public alpha only after naming, license split, security/community docs, CI, fixtures, and example CLI are approved. |

## Design Principles

1. Evidence before claims. Local facts need files, tests, commands, or receipts. External facts need fresh retained primary-source receipts before public or release decisions.
2. Deterministic floor first. Capsule compile, preview, doctor, and export must work without a hosted model.
3. Critical continuity is not compressible by default. Active goals, permissions, prohibitions, critical constraints, unresolved conflicts, current frontier, and explicit unknowns are retained or compilation fails.
4. Adapters are capabilities, not promises. Every support tier is derived from descriptors and conformance fixtures, not optimistic UX copy.
5. Local-first and reversible. Preview before writes, write only approved Canon-owned regions or artifacts, record undo receipts, and avoid deleting user material.
6. Raw history is protected inventory. I0 may produce references and aggregate receipts; promotion to continuity atoms is a separate reviewed operation.
7. Trust is scoped. Signatures prove integrity only until a pinned key, scope, expiry, replay, and source-state policy say they prove more.
8. Accessibility is a contract. CLI, Markdown, HTML, MCP, desktop, browser, IDE, mobile, and CI surfaces must expose equivalent state without color-only, mouse-only, JSON-only, or animation-only meaning.
9. Honest nulls stay visible. Unknown, blocked, stale, untrusted, unsupported, and contradictory are different states.

## Non-Goals

- No implementation authorization in this document.
- No public package release, package reservation, deploy, PR, default-branch commit, or compatibility mark.
- No claim that Canon is currently a public ecosystem standard.
- No claim that closed ChatGPT or Claude apps enforce Canon before first model work.
- No claim that OpenCode, Gemini CLI, Cursor, or GitHub Copilot are stronger than Guided/unknown until descriptor evidence and fixtures land.
- No automatic ingestion of raw chats, protected files, browser profiles, `.env` files, private databases, or unpublished protected material.
- No local 14B/32B readiness or uplift claim until endpoint gates and release evidence are reconciled.
- No provider parity claim. Same API shape, app project files, or instruction markdown does not imply equal semantics.

## Architecture and Data Flow

```text
Allowed local sources and host exports
  -> source inventory, continuity flight-recorder events, and state receipts
  -> protected I0 references, Canon records, Mneme receipts, Relay checkpoints, Index refs, Flywheel receipts
  -> atom projection and policy evaluation
  -> capsule compiler
  -> canon.capsule/v1 manifest
  -> generated CANON.md and optional .canonpack reference archive
  -> target adapter preview/import/bootstrap
  -> readiness probe
  -> bootstrap witness
  -> ordinary work only after visible bootstrap result
```

Data boundaries:

- `canon.record/v1` remains the current storage envelope.
- `canon.atom/v1` is the continuity semantics layer above records.
- `canon.capsule/v1` is the deterministic target/profile manifest.
- `CANON.md` is the generated human-readable transfer surface bound to the capsule digest.
- `.canonpack` is an optional archive/reference carrier, never mandatory for the receiving model's context.
- Bootstrap witnesses are event receipts. They include time and observed host behavior; the deterministic capsule manifest does not.

## Artifact Roles

### `canon.atom/v1`

Role: typed continuity unit used for policy, budget, freshness, conflict, and readiness checks.

Proposed atom classes:

| Class | Purpose | Critical by default |
|---|---|---|
| `instruction` | Durable operating instruction. | Sometimes, if normative. |
| `active-goal` | Current task/project objective. | Yes. |
| `permission` | Explicit allowed action or authority grant. | Yes. |
| `prohibition` | Disallowed action or safety boundary. | Yes. |
| `constraint` | Non-permission requirement such as no deploy, no commit, no edit. | Yes when hard. |
| `decision` | Accepted decision and rationale. | Usually no, unless current blocking decision. |
| `frontier-state` | Current working state and next unblocked action. | Yes for active work. |
| `evidence-ref` | Reference to source artifact without raw body copy. | No, unless required to verify a critical atom. |
| `episodic-fact` | Remembered event or fact with provenance/freshness. | No by default. |
| `synthesized-persona` | L3 persona synthesis. | No by default; cannot carry unreviewed normative authority. |
| `conflict` | Unresolved contradiction or incompatible directive. | Yes. |
| `unknown` | Explicitly retained gap. | Yes when attached to active work. |
| `omission` | Budget, policy, safety, or reachability omission. | Receipt, visible. |
| `lossy-transform` | Summary, compaction, projection, redaction, or migration receipt. | Receipt, visible. |
| `bootstrap-probe` | Readiness challenge/check item. | Yes for supported bootstrap. |
| `bootstrap-witness` | Event receipt for bootstrap attempt. | Receipt, visible. |
| `adapter-capability` | Target adapter tier and constraints. | Yes for advertised support. |

Minimum fields:

```json
{
  "atom_schema": "canon.atom/v1",
  "type": "active-goal",
  "id": "stable-id",
  "layer": "session|project|workspace|personal|team|organization|imported-history",
  "scope_key": "path-clean-or-opaque-key",
  "precedence_rank": 0,
  "status": "active|retired|superseded|stale|untrusted|unknown|blocked",
  "classification": "normative|descriptive|derived|receipt",
  "critical": true,
  "value": {},
  "source_refs": [],
  "source_span_refs": [],
  "freshness": {},
  "trust": {},
  "disclosure": {},
  "hashes": {}
}
```

### `canon.capsule/v1`

Role: deterministic manifest compiled for a target adapter, surface, disclosure profile, and budget profile.

Minimum top-level fields:

```json
{
  "schema": "canon.capsule/v1",
  "capsule_id": "sha256:<manifest-bytes>",
  "profile": "needle|handoff|archive|custom",
  "target": {
    "adapter": "codex|claude-code|chatgpt|opencode|api|local|mcp|a2a",
    "surface": "CANON.md|AGENTS.md|CLAUDE.md|SOUL.md|inline|mcp-resource|artifact",
    "integration_tier": "enforced|native-advisory|guided|unsupported",
    "host_enforcement_observed": false
  },
  "source_state": {
    "records_digest": "sha256:...",
    "inventory_digest": "sha256:...",
    "context_envelope_digest": "sha256:...",
    "mneme_snapshot_digest": "sha256:...",
    "relay_checkpoint": "sha256:...",
    "worktree_digest": "sha256-or-typed-null"
  },
  "compatibility": {
    "record_schema_min": "canon.record/v1",
    "capsule_schema": "canon.capsule/v1",
    "requires_features": []
  },
  "budget": {
    "profile": "needle|handoff|archive|custom",
    "max_tokens": 0,
    "estimated_tokens": 0,
    "estimator": "known|unknown",
    "policy": "critical-atoms-lossless"
  },
  "layers": [],
  "atoms": [],
  "records": [],
  "conflicts": [],
  "unknowns": [],
  "omissions": [],
  "lossy_transforms": [],
  "freshness": [],
  "integrity": {
    "canonicalization": "json-sorted-compact-lf",
    "manifest_sha256": "sha256:..."
  },
  "receipts": [],
  "does_not_prove": []
}
```

Determinism rule: identical source bytes, source declarations, compiler version, profile, target adapter descriptor, and budget config produce byte-identical capsule bytes. Wall-clock times, observed host behavior, probe responses, and user approvals are witness fields, not manifest fields.

### `CANON.md`

Role: readable transfer artifact generated from `canon.capsule/v1`, suitable for CLI preview, clipboard, project files, instruction files, app uploads, and human review.

Required deterministic section order:

1. Capsule identity
2. Target and integration tier
3. Freshness, trust, and unknowns
4. Active goals
5. Authority, permissions, prohibitions, and constraints
6. Current frontier and working state
7. Decisions and rationale
8. Conflicts requiring resolution
9. Canonical instructions
10. Evidence references
11. Omissions
12. Lossy transforms
13. Bootstrap readiness probe
14. Does-not-prove

Binding rule: `CANON.md` must include the capsule digest and either a sidecar capsule reference or a constrained machine carrier for small profiles. The visible prose is reviewable, but the capsule manifest is authoritative.

### Optional `.canonpack`

Role: portable archive/reference bundle for records, evidence indexes, receipts, redaction receipts, adapter descriptors, and fixture outputs.

Policy:

- Default to by-reference evidence, not raw private content.
- Parse manifest before extraction.
- Extract only into a newly created explicit temp directory.
- Reject absolute paths, `..`, drive-qualified paths, alternate data streams, symlinks, junctions, reparse points, duplicate normalized names, case-fold collisions, oversize files, decompression bombs, unsupported compression, and digest mismatch before any unsafe read/write.
- Never auto-promote `.canonpack` content into startup instructions.

## Authority, Scope, Precedence, Conflict, and Freshness

### Authority

Authority is represented by explicit atoms, not by vague memory text. `permission`, `prohibition`, `constraint`, `instruction`, and `active-goal` atoms must be source-bound, freshness-labeled, trust-labeled, and classified as normative when they govern behavior.

Critical authority atoms are retained in Needle and Handoff profiles or compilation fails. Model-synthesized unreviewed text cannot create, remove, or weaken authority.

### Scope

Current `canon.record/v1` scopes remain `global` and `workspace`. Richer scope belongs in `canon.atom/v1` or a future migration, not by silently widening `canon.record/v1`.

Proposed atom layers:

1. `session`
2. `task`
3. `project`
4. `repo`
5. `workspace`
6. `personal`
7. `team`
8. `organization`
9. `imported-history`

### Precedence

Recommended default precedence:

1. Active task/session instruction
2. Explicit operator/user instruction
3. Project/repository instruction
4. Workspace instruction
5. Organization/team policy
6. Personal/global preference
7. Imported historical memory
8. External or untrusted reference

Conflict rule: a lower-precedence descriptive fact may remain as evidence, but it cannot override a higher-precedence normative atom. A lower-precedence prohibition cannot be erased by a higher-precedence summary unless the operator explicitly resolves it.

### Conflict

Contrary normative atoms produce a `conflict` atom. Unresolved conflicts are critical. They cannot be omitted under budget, collapsed to newest-wins, or resolved by a model summary. Valid resolutions are `approved`, `edited`, `rejected`, and `pending`; missing, expired, unknown, or out-of-vocabulary resolution fails closed.

### Freshness

Freshness states:

- `current`
- `stale`
- `superseded`
- `contradictory`
- `untrusted`
- `unknown`
- `blocked`

Freshness is based on source-state identities and recheck receipts where available, not only timestamps. A source that cannot be reached is `unknown` or `blocked`, never silently current.

## Ambient Bootstrap Protocol

Every supported new chat, project, app session, harness run, API request, or local endpoint task must attempt continuity freshening before ordinary work. The implementation must distinguish what it can enforce from what it can only advise or guide.

Exact state machine:

| State | Name | Required behavior | Failure transition |
|---|---|---|---|
| S0 | `detect_entry` | Detect session, chat, project, workspace, branch, target adapter, target surface, and instruction-state entry. | `unsupported_lifecycle` if no safe entry route exists. |
| S1 | `resolve_layers` | Resolve personal, organization, team, project, repo, workspace, session, and imported-history layers supported by current schema/policy. | `missing_authority`, `source_unreachable`, or `index_unavailable`. |
| S2 | `collect_source_state` | Collect record digests, inventory digests, instruction-surface hashes, worktree state, relevant receipts, adapter descriptor, and source reachability without reading protected content by default. | `local_state_unavailable`, `secret_quarantine`, or `source_unreachable`. |
| S3 | `preflight` | Check schema validity, trust, freshness, conflicts, budget, disclosure, target fit, dirty worktree policy, locks, and adapter tier evidence. | `stale_evidence`, `conflict`, `budget_incompatible`, `authority_untrusted`, `tier_mislabeled`, or `source_changed`. |
| S4 | `compile_or_reuse_capsule` | Compile deterministic capsule or reuse only when source digests, profile, adapter descriptor, disclosure policy, and compiler version match. | `capsule_nondeterministic`, `critical_atom_loss`, `omission_invisible`, or `secret_quarantine`. |
| S5 | `present_context` | Present the capsule, generated `CANON.md`, unknowns, omissions, support tier, and does-not-prove text in the target-appropriate surface. | `presentation_unavailable` or `unsupported_content_type`. |
| S6 | `readiness_probe` | Probe critical goals, permissions, prohibitions, constraints, frontier, conflicts, unknowns, and first safe action. | `readiness_failed`, `readiness_blocked`, or `readiness_false_pass`. |
| S7 | `emit_witness` | Write an append-only bootstrap witness with capsule identity, source-state identity, target, tier, checks, omissions, lossy transforms, readiness result, failure code, and event time. | `witness_unavailable`. In Enforced tier this is terminal. |
| S8 | `release_to_work` | Allow ordinary work only after a visible bootstrap result. | If capsule changes before critical work, return to S2 with `source_changed`. |

Failure semantics:

- Enforced: any required failure before S8 is terminal and ordinary work must not begin.
- Native advisory: Canon presents a visible advisory witness and readiness result, but cannot prove host-level blocking. The UI/copy must say this.
- Guided: the user or controller initiates import/paste/launcher flow. Canon records what it prepared and whether the receiving surface showed a witness.
- Unsupported: Canon provides export-only or report-only fallback and must not claim fresh session state.

### Readiness Behavior

Probe schema: `canon.readiness-probe/v1`.

The receiving model or harness must enumerate:

1. active goal ids,
2. allowed writes,
3. forbidden writes/actions,
4. unresolved conflict ids,
5. explicit unknown ids,
6. source evidence already read,
7. first safe action,
8. conditions that must stop the run,
9. secret-handling policy without revealing secret values.

Pass rule: all critical ids and statuses match deterministic oracle/capsule ids; no raw secret appears; first safe action is in scope; unsupported/advisory behavior is not mislabeled as enforced.

Failure rule: readiness failure is acceptable evidence only if it is visible, typed, and prevents ordinary work in Enforced tier or visibly downgrades advisory/guided flows.

### Witness Behavior

Witness schema: `canon.bootstrap-witness/v1`.

Required witness fields:

- run id,
- capsule id and manifest sha256,
- source-state digests,
- target adapter/surface/session,
- claimed support tier and observed enforcement basis,
- event timestamp,
- checks with verdicts and evidence refs,
- omissions and lossy transforms,
- readiness prompt/response hashes,
- missing or mismatched critical ids,
- failure codes,
- does-not-prove statements.

Witnesses must be append-only, path-clean, idempotent by run id, safe for public redaction, and bound to source-state. Enforced starts fail closed if the witness cannot be written.

## Support-Tier Policy

Definitions:

- Enforced: Canon or the host controls a pre-first-work gate and can block ordinary work until bootstrap succeeds or visibly fails.
- Native advisory: the host automatically loads instructions, project files, memory, connector output, or plugin guidance, but Canon cannot prove technical blocking.
- Guided: Canon supplies a launcher, import flow, first message, clipboard/file handoff, MCP prompt, or A2A task that the user or controller initiates.
- Unsupported: no safe documented integration exists; Canon may export but cannot claim import/bootstrap semantics.

Policy:

- **No fixture, no Enforced tier.**
- **No retained primary evidence or descriptor, no stronger-than-Guided claim for contested hosts.**
- ChatGPT and Claude apps are Native advisory at most unless a verified blocking lifecycle exists.
- Platform descriptors become source of truth only after primary evidence and conformance fixtures are retained. Otherwise the conservative UX labels apply.
- Current provider docs, registry names, retention tables, and package facts are time-sensitive and require fresh receipts before public copy or release decisions.

## Current Conservative Adapter Matrix

| Surface or route | Current design tier | Rationale and loss notes |
|---|---|---|
| Canon local Python API | Unsupported for user-facing bootstrap; library foundation only. | No tracked CLI/MCP/app entry point. |
| Canon-owned OpenAI/API runner | Enforced candidate after fixture. | A controlled runner can refuse the first model request until bootstrap passes, but this is not current Canon code. |
| Raw OpenAI API without Canon-owned runner | Unsupported for ambient bootstrap. | API callers construct state; provider API does not create Canon startup lifecycle by itself. |
| Generic local OpenAI-compatible endpoint wrapper | Enforced candidate after wrapper and endpoint fixtures. | Endpoint alone has no instruction hierarchy or startup hook; wrapper can gate requests. Local 14B/32B remain blocked until endpoint gates exist. |
| Claude Code | Native advisory now; Enforced candidate only after a blocking pre-first-work proof. | `CLAUDE.md`, hooks, memory, settings, and MCP help, but no audited proof of full startup blocking. |
| Codex CLI / local Codex / Codex in app | Native advisory now; Enforced candidate only through a verified wrapper or native hook. | `AGENTS.md` loads before work, but prompt/context loading is not a technical gate. Existing Canon catalog has Codex workspace `AGENTS.md` only. |
| Claude web/desktop/mobile apps | Native advisory at most; Guided for export/import. | Project instructions/knowledge can carry `CANON.md`; no blocking startup hook verified. |
| ChatGPT web/desktop/mobile/projects/Work | Native advisory at most; Guided for export/import. | Project files, instructions, local Work, plugins/connectors, and Actions can carry context; no blocking app lifecycle verified. |
| OpenCode | Guided/unknown pending retained descriptor and fixture. | Platform lane reports native advisory sources, UX lane marks Guided until audited. V-C1 resolves conservatively here. |
| Gemini CLI | Guided/unknown pending retained descriptor and fixture. | Platform lane reports native advisory sources, UX lane marks Guided until audited. V-C1 resolves conservatively here. |
| Cursor | Guided/unknown pending retained descriptor and fixture. | Rules/AGENTS/MCP may carry context, but no verified blocking lifecycle in the synthesis evidence. |
| GitHub Copilot | Guided/unknown or Unsupported by surface pending retained descriptor and fixture. | Instruction support differs by environment; no readiness witness or blocking bootstrap verified. |
| MCP hosts / Canon MCP server | Guided generically; Enforced only inside a host that gates on Canon. | MCP can expose typed resources/prompts/tools but cannot compel host/model use by itself. |
| A2A agents | Guided generically; Enforced only when the controller refuses task dispatch until bootstrap passes. | Capsule can travel as an artifact and witness, but protocol does not define Canon precedence or universal startup hook. |

## Primary User Journeys

1. First run: user runs a preview-only setup, sees what Canon can read, chooses whether to install markers or only generate artifacts, and receives an undo checkpoint for any write.
2. Fresh session entry: a supported host starts or a project opens; Canon resolves layers, compiles/reuses capsule, runs readiness, writes witness, and exposes whether the start is enforced, advisory, guided, or unsupported.
3. Provider switch: user selects source and target; Canon runs Context Doctor, budget fit, semantic diff, and preview; export/import happens only after review.
4. Emergency rescue: provider quota or session access fails; Canon compiles a local handoff from reachable records/receipts and marks remote-only freshness as `blocked/quota`, `blocked/offline`, or `unknown`.
5. Import review: user imports another agent/project/app setup; Canon classifies each instruction, hook, connector, setting, record, secret, conflict, unsupported field, and needed auth before any write.
6. "What will the next model know?": user previews exact `CANON.md`, capsule metadata, token/byte budget, included items, omitted items, lossy transforms, unknowns, and readiness challenge.
7. Semantic continuity diff: user compares two capsules by meaning, not only bytes: goals, permissions, prohibitions, conflicts, decisions, unknowns, evidence refs, and transform receipts.
8. Branch/session merge: user reconciles parallel session capsules with explicit conflict handling and no silent overwrite.
9. Team/CI freshness gate: a PR or project open detects instruction/decision changes without a fresh capsule/witness and blocks or warns according to policy.
10. Continuity flight recorder: Canon-enabled hooks, launchers, adapters, and tools append local receipts for operator corrections, decisions, frontier changes, tool outcomes, and repository state. Raw prompts, responses, and transcript bodies remain off by default and require an explicit private capture policy.

## Prioritized Capability Portfolio

| Horizon | Capability | Minimum lovable detail | Exit gate |
|---|---|---|---|
| Now | `canon.atom/v1` and `canon.capsule/v1` schema/validators | Positive and negative fixtures for critical atoms, omissions, transforms, freshness, trust, adapters, probes, witnesses. | Deterministic fixture pass and fail-closed invalid cases. |
| Now | Generated `CANON.md` | Deterministic human surface with capsule digest, support tier, active state, conflicts, omissions, readiness, and does-not-prove. | Render twice and compare bytes; digest/body drift detected. |
| Now | CLI spine | `init`, `compile`, `preview`, `doctor`, `export`, `import review`, `rescue`, `undo`; `--json`, `--no-color`, stdin/stdout, stable exit codes. | Fresh clone local example works with no secrets and no network. |
| Now | Context Doctor | Checks schema, freshness, drift, reconcile, source reachability, secret quarantine, budget, adapter tier, dirty worktree, concurrency. | Every fixture failure maps to one code and one recovery action. |
| Now | Readiness proof and bootstrap witness | Probe critical state, verify exact ids/statuses, emit append-only witness before work where enforceable. | Witness exists before ordinary artifact timestamps. |
| Now | Omission and transform receipts | Every omission typed/countable/visible; every lossy summary/projection/redaction/migration hash-bound. | Critical omissions fail build. |
| Now | Secret/protected-path gate | Synthetic canaries, `.env`, keys, browser profiles, private DBs, PII fixtures, no model/export leak. | Zero planted-secret transmission. |
| Now | Adapter descriptor schema | `canon.adapter/v1` with tier, evidence, import/export, hierarchy, lifecycle, limits, auth/privacy, known unknowns. | No advertised tier above fixture proof. |
| Now | MCP read-only preview/doctor | Resources for current capsule, manifest, omissions, receipts, preview; tools for compile/check with read-only default. | Tool outputs contain typed errors and no secrets. |
| Now | Emergency handoff | `rescue --target` works offline from local state and marks remote-only sources unknown/blocked. | Network-disabled fixture succeeds with visible omissions. |
| Now | Undo | Region-scoped before/after receipt, restore command, drift refusal. | Previous Canon-owned bytes restored exactly or rollback refuses. |
| Next | Local continuity flight recorder | Append-only, content-addressed events from Canon-enabled hooks and tools for decisions, corrections, frontier state, evidence refs, repo/worktree identity, and handoffs; raw conversation capture off by default. | Replay deterministically rebuilds the same normalized event ledger; secret fixtures never enter event payloads; disabled mode writes nothing. |
| Next | Desktop/launcher | First-run wizard, provider switch, preview, Context Doctor, undo timeline, cross-machine status. | Keyboard and screen-reader acceptance pass. |
| Next | Browser/app companion | Guided handoff for closed apps, copy/import checklist, visible capsule/witness status. | No claim of enforcement for closed apps without proof. |
| Next | IDE extension | Branch/session panel, semantic diff, merge review, source-control-adjacent readiness. | Merge fixtures cover stale base and conflict visibility. |
| Next | Team/org layers and CI | Policy-layer diff, PR comments, freshness gate, owner/source labels. | Role-aware fixtures and accessible CI artifacts pass. |
| Next | Local endpoint gates | Endpoint profile, generation gate, resource metrics, observed model id, fixed prompt hash. | 14B/32B runs admitted only after gate artifacts. |
| Later | Public conformance program | Fixture zoo, conformance CLI, reports, badges by artifact capability. | At least one clean-room reader passes before 1.0 claim. |
| Later | Cross-platform installers and OCI | pipx/uv, Homebrew/Scoop/winget/container, signed/attested builds. | Reproducible artifacts, SBOMs, checksums. |
| Later | Mobile/view-only review | Responsive static HTML/Markdown for approval, preview, omissions, readiness proof. | Touch, zoom, screen-reader gates pass. |
| R&D | Model-assisted synthesis | Optional refinement with source spans, transform receipts, and unreviewed quarantine. | Cannot carry normative authority until reviewed. |
| R&D | Automated closed-app lifecycle control | Screen/app companion experiments only where terms and lifecycle support permit. | Never advertised as enforced without host proof. |
| R&D | Semantic importance scoring | Budget compression aid after critical atoms are protected. | Negative controls prove no normative downgrade. |

## Accessibility Contract

Minimum release-blocking requirements:

- Keyboard-only operation for CLI prompts, desktop/browser/IDE workflows, preview, import review, diff, doctor, and undo.
- Screen-reader structure with headings, landmarks, status announcements, table summaries, and text equivalents for all badges/icons.
- No color-only state. Status labels use words such as Ready, Advisory, Blocked, Stale, Conflict, Unknown, Secret quarantined.
- WCAG 2.2 AA target for HTML/docs surfaces, 200 percent zoom without prose overflow, reduced-motion support, and no auto-advancing review steps.
- `NO_COLOR` and `--no-color` support in CLI; stable exit codes; JSON output for automation and Markdown/HTML for humans.
- Low-bandwidth/offline mode with no remote asset dependency for core flows.
- Plain-language primary UI. Schema terms get one-sentence explanations and are hidden behind detail disclosure until needed.
- Localization-ready strings, locale-aware dates/numbers, and RTL smoke coverage before stable docs/site claims.
- Cross-machine and mobile review states must distinguish missing local path from missing record.

## Security, Trust, Disclosure, Retention, and Concurrency Contract

### Default Security Posture

- Default-deny import: no external record, archive entry, generated instruction, or model summary becomes active until schema, trust, freshness, conflict, source-reachability, secret/PII, disclosure, and budget checks pass.
- Redact and classify before model exposure, export, or logging. Redaction is not permission to read protected files.
- Raw prompt, response, screen, microphone, and transcript capture is off by default. A continuity flight recorder may capture only scoped private content that the operator explicitly enables; metadata-only recording remains visible and disableable.
- Receipts prove what was checked and what they do not prove. They do not grant authority.
- Bootstrap adapters run read-only and root-confined by default. Write, exec, network, plugin, or secrets access requires explicit policy and must appear in the witness.

### Trust Labels

Use these labels in machine and human surfaces:

- `trusted-local`
- `signed-pinned`
- `signed-unknown-key`
- `unsigned-local`
- `imported-untrusted`
- `model-synthesized-unreviewed`
- `secret-quarantined`
- `stale`
- `public-exportable`
- `private-local-only`

Unknown-key signatures are integrity-only. Trusted imports require pinned keys scoped to principal, project, capability, expiry, source-state, and replay policy.

### Disclosure

Recommended profiles:

- Full local: local-only, maximum detail, still no secrets by default.
- Project only: default for ordinary handoff.
- No secrets: default for emergency export.
- Team-safe: excludes private personal records and local-only evidence.
- Public-safe: redacts private paths, raw transcripts, protected material, and sensitive identifiers.
- Need-to-know: minimal target-specific profile with critical atoms retained.

Every profile must show included/excluded counts, reasons, and source ids. If a critical atom is excluded by a disclosure profile, the build fails or requires explicit operator resolution.

### Retention and Deletion

Canonical policy must be decided before public alpha. The design requires:

- sensitivity labels per atom/record,
- retention periods or local-only defaults,
- tombstone records,
- purge receipts,
- derived-surface deletion coverage across SQLite, files, vault, managed surfaces, capsules, `.canonpack`, witnesses, backups, and exported artifacts,
- explicit policy for whether content hashes may remain after deletion.

Encryption at rest remains an operator decision. Until approved and implemented, Canon must state that current storage is plaintext.

### Concurrency

Bootstrap and import writes require:

- workspace/target-surface run locks,
- source-state digest captured before compile,
- compare-and-swap before write/import,
- append-only witnesses,
- stale-run abort on source change,
- distinct witnesses for concurrent chats,
- no partial success presented as clean,
- undo receipts for local region writes.

### FilesBackend Blocker

Security finding: `FilesBackend` derives paths from `record.scope` before semantic validation. Current `validate_record` rejects invalid scopes, but `FilesBackend.put` calls `guard_put`, and `guard_put` does not call full validation before `record_key(record)` and `_path(...)`.

Release gate: **Fix FilesBackend semantic validation before any external capsule import can write records.** Invalid scopes such as `..`, separator-bearing strings, drive-qualified values, or unknown scope names must fail before path derivation, and tests must prove no outside-root artifact is created.

## Benchmark and Evidence Plan

Suite id: `canon_continuity_gauntlet_v1`.

Modes:

- `dry_plan`: fixtures, capsules, manifests, expected artifacts, and gates without model calls.
- `endpoint_profile`: endpoint health/profile without generation unless authorized.
- `focused_run_after_approval`: bounded live runs only after explicit approval.
- `replay_verify`: re-verify artifacts, receipts, hashes, scorecards, gates without model calls.

Task sets:

| Set | Size | Purpose | Claim allowed |
|---|---:|---|---|
| `smoke` | 5 | One task per continuity family. | Wiring only. |
| `core` | 30 | Six tasks per family, cold/warm split, two compression variants, at least two providers. | Directional evidence. |
| `release` | 100+ | Balanced by family, provider, capsule budget, retrieval variant, cold/warm start. | Public/release claims only with denominators and intervals. |
| `stress` | 25 | Secret canaries, stale capsules, conflicting branches, wrong ids, missing sources, tampered receipts. | Negative-control coverage. |

Task families:

1. Provider migration.
2. Agent resume.
3. Repository continuity.
4. Parallel-session merge.
5. Ambient bootstrap.

Required metrics:

- critical fact retention, active goal retention, policy retention, conflict retention, unknown retention,
- resumed task correctness,
- source-span coverage,
- adapter loss declared,
- human correction count/minutes/tokens,
- unsafe first action rate,
- tool success and recovery rate,
- dirty work preservation,
- bootstrap latency and time to first safe action,
- token reduction and answer recall,
- receipt verification and replay match,
- secret leak count/rate,
- unsupported claim rate,
- local endpoint RSS/VRAM/tokens/sec/OOM/timeout where available.

Statistics:

- Wilson 95 percent intervals for proportions.
- Exact McNemar or paired bootstrap for paired comparisons.
- Bootstrap 95 percent intervals over task ids for latency, token reduction, correction burden, and resources.
- No uplift claim when the difference interval includes zero.

Executable dry-plan gates:

| Gate | Command shape | Required result |
|---|---|---|
| G0 | `canon continuity fixture-check <task_set>` | Schemas valid, oracle ids unique, negative controls present, synthetic canaries only. |
| G1 | `canon continuity build-capsule --profile handoff --twice --compare` | Byte-identical capsule and stable digest. |
| G2 | `canon continuity check-normative <capsule> <oracle>` | 100 percent active goals, permissions, prohibitions, conflicts, unknowns retained or build fails. |
| G3 | `canon continuity secret-scan <run_root>` | Zero raw canary values in capsules, prompts, scorecards, reports, logs. |
| G4 | `canon continuity verify-readiness <run_root>` | Readiness probe and witness precede ordinary work artifacts. |
| G5 | `canon continuity verify-sources <capsule>` | Source spans reachable or typed missing/stale/unverifiable. |
| G6 | `canon continuity roundtrip --matrix adapters.json` | No silent loss; declared losses match expected limits. |
| G7 | `canon continuity compare-admit <scorecard>` | Same task id, prompt hash, metric schema, execution policy, model/harness identity basis. |
| G8 | `canon continuity score <run_root>` | Deterministic oracle pass or typed failure. |
| G9 | `canon continuity merge-check <merge_receipt>` | Conflicts visible, no silent overwrite, no forbidden write. |
| G10 | `canon continuity ci <scorecard>` | Denominators and 95 percent interval method present. |
| G11 | `canon continuity claim-check <scorecard.md>` | Does-not-prove language present. |
| G12 | `canon continuity replay-verify <run_root>` | Receipts, hashes, score rows re-derive. |

Local model rule: 14B/32B quality runs are blocked until endpoint profile and endpoint generation gate artifacts exist for the exact artifact tested, and until release ownership reconciles the 14B CI artifact with release docs. Do not claim readiness from model root or weight presence.

## Release and Community Maturity Ladder

| Level | Name | Gates | Current status |
|---|---|---|---|
| 0 | Local prototype | Tests pass, internal docs exist, no public release claims. | Current mainline fits here: 407 tests pass and docs exist. |
| 1 | Public alpha | Non-colliding name, security/contribution/governance docs, alpha CLI, permissive spec/fixtures, CI dry run, example capsule. | Not met. |
| 2 | Implementer beta | JSON Schema, fixture zoo, conformance CLI, signed prereleases, docs site, adapter tier matrix, migration policy. | Not met. |
| 3 | Stable toolchain | Semver 1.0 contracts, stable CLI/MCP/SDK, cross-platform installers, SBOM/signing/attestations, security response, accessibility gates. | Not met. |
| 4 | Ecosystem standard | Multiple implementations, public compatibility reports, neutral governance or published RFC process, provider-neutral adapter registry, retirement criteria. | Not met. |
| 5 | Durable standard | LTS/security branches, independent conformance lab or foundation-style custody, broad package/distro availability, sustained adoption metrics. | Not met. |

Definition of release stages:

- Public alpha: a user can install a non-colliding alpha CLI, run a deterministic local example, preview a capsule, see omissions, and read security/community docs. Claims are limited to local prototype behavior and alpha stability.
- Beta: implementers can use published JSON Schema, fixture zoo, conformance CLI, adapter descriptors, migration policy, signed prereleases, and docs. At least one clean-room read-only reader should pass before moving toward stable.
- 1.0: semver-stable capsule schema, CLI JSON contract, MCP resources, SDK public API, conformance fixtures, security policy, migration path, accessibility gates, release provenance, and at least one independent or clean-room implementation pass.
- Ecosystem standard: multiple maintained implementations, public conformance reports, neutral or RFC-style governance, provider-neutral adapter registry, published retirement criteria, and sustained adoption/support metrics.

## Delivery Waves

These waves are planning-level gates, not file-by-file implementation authorization.

| Wave | Focus | Prerequisites | Exit gate |
|---|---|---|---|
| 0 | Operator decisions and blocker triage | This proposal reviewed. | Decisions recorded for naming, scope model, Enforced wording, disclosure defaults, trust keys, retention, telemetry, I0 boundary, FilesBackend priority. |
| 1 | Schema and fixtures | No product release. | `canon.atom/v1`, `canon.capsule/v1`, omission, transform, readiness, witness, adapter descriptor schemas have positive/negative fixtures. |
| 2 | Deterministic local spine | Wave 1 fixtures. | CLI compile/preview/doctor/export/rescue/import-review/undo works locally; `CANON.md` and capsule builds are byte-stable. |
| 3 | Security hardening | FilesBackend fix, trust/disclosure decisions. | Secret, PII, path, `.canonpack`, symlink/junction, replay, unknown-key, retention/tombstone, concurrency gates pass. |
| 4 | Adapter and protocol interop | Adapter descriptors and core conformance. | Codex, Claude Code, API runner, MCP, A2A, and local endpoint wrapper descriptors produce honest tier reports and round-trip loss ledgers. Contested hosts stay Guided/unknown until proved. |
| 5 | UX and accessibility surfaces | Stable local CLI and schema. | Accessible Markdown/HTML preview, desktop/launcher prototype, browser guided flow, IDE panel, and CI annotations pass accessibility gates. |
| 6 | Benchmark evidence | Dry-plan gates and adapter descriptors. | Smoke live runs only after explicit approval; no capability claims beyond denominators/intervals. |
| 7 | Public alpha prep | Naming/license/governance/security/CI approved. | Non-colliding package family, public docs, security policy, contribution files, CI, secret scan, SBOM plan, example fixtures. |
| 8 | Beta/1.0 maturation | Alpha feedback and conformance stability. | Signed prereleases, installer strategy, SDK/MCP contract, clean-room reader pass, migration policy, release provenance. |

## Capability-Environment Artifacts To Leave Behind

- `canon.atom/v1`, `canon.capsule/v1`, `canon.omission/v1`, `canon.transform-receipt/v1`, `canon.readiness-probe/v1`, `canon.bootstrap-witness/v1`, and `canon.adapter/v1` schemas.
- Positive and negative fixture zoo with planted normative constraints, secret canaries, stale/conflict/unknown cases, adapter loss cases, malicious archive cases, and local endpoint profiles.
- Conformance CLI and machine-readable conformance report format.
- Context Doctor finding taxonomy, exit codes, and recovery text.
- Deterministic `CANON.md` renderer/verifier and drift detector.
- Bootstrap witness store and replay verifier.
- Adapter descriptor registry with support tier, source evidence, last verified date, limits, auth/privacy boundaries, owner, and retirement trigger.
- Continuity benchmark harness and artifact layout.
- Release claim checker with does-not-prove templates.
- Accessibility test harness for CLI, Markdown, HTML, desktop/browser/IDE where applicable.
- Public-safe docs examples and sanitized dogfood receipts.
- Bounded Index snapshot process with timeout receipts, because full workspace graph evidence remains blocked.

## Risks

| Risk | Severity | Control |
|---|---|---|
| Overclaiming enforced bootstrap on advisory/guided hosts | Critical | Tier descriptors, fixture requirement, conservative copy, witness `host_enforcement_observed`. |
| Critical goals or prohibitions lost during compression | Critical | Critical atom retention gate, readiness probe, negative controls. |
| Secret or private transcript leakage | Critical | Protected-path denial, redaction before exposure, I0 reference-only boundary, secret canaries. |
| FilesBackend path traversal | Critical | Validate scopes before path derivation, reject traversal/drive/separator values, outside-root tests. |
| Stale or replayed capsule imported as current | High | Source-state digest, expiry, nonce/sequence, replay cache, supersession checks. |
| Unknown-key signature treated as trust | High | Pinned trust store and `signed-unknown-key` quarantine. |
| `.canonpack` archive attack | High | Manifest-first preflight, safe extraction, size/ratio limits, digest checks. |
| Cross-session race or partial write | High | Locks, compare-and-swap, append-only witness, partial-write receipt, undo. |
| External registry/provider claims drift | High | Fresh retained receipts before naming/package/provider public claims. |
| Local 14B/32B release evidence misread | High | Endpoint gates and release-owner reconciliation before use. |
| Accessibility becomes late polish | High | Accessibility gates in alpha/beta/stable definitions and CI. |
| FSL license blocks standard adoption | High | Operator decision on split: permissive specs/fixtures/conformance, runtime policy explicit. |
| Compatibility mark creates legal/support risk | High | Defer or rename mark until governance, fixtures, and legal/name review exist. |

## Operator Decisions

| Decision | Recommended default | Tradeoff |
|---|---|---|
| Public name and mark | **Choose a non-colliding package/CLI/mark family before alpha; reserve "Canon" as internal or descriptive until legal/name review.** | Reduces launch confusion and registry conflict, but may give up the current short name. |
| Package family | **Do not publish Python as `canon` or expose a public `canon` CLI until collision policy is approved.** | Avoids install ambiguity, but may require renaming imports or adding compatibility aliases later. |
| License split | **Publish specs, schemas, fixtures, and conformance under permissive/open terms; decide runtime license separately.** | Maximizes implementer adoption while preserving runtime control if desired. |
| Enforced wording | **Reserve Enforced for native host hooks or Canon-owned wrappers with executable blocking fixtures.** | Conservative copy limits near-term claims, but prevents trust erosion and tier corrections later. |
| Scope model | **Keep `canon.record/v1` unchanged and put personal/team/org/session/repo semantics in `canon.atom/v1` or a future versioned migration.** | Preserves existing tests and adapters, but adds a new policy layer. |
| I0 integration | **Treat I0 as protected inventory/reference input only; require reviewed promotion receipts for any atom.** | Slower than auto-memory ingestion, but prevents stale/private history from becoming authority. |
| Default disclosure | **Use Project only for normal handoff, No secrets for emergency handoff, Public-safe for public artifacts.** | Safer default disclosure, but some handoffs may need explicit inclusion of more context. |
| Readiness proof | **Make readiness mandatory for provider switches and critical handoffs; allow advisory/manual proof for closed apps.** | Stronger safety for important work, but avoids blocking low-risk guided app flows where enforcement is impossible. |
| Marker/write surfaces | **Start with generated artifacts and Canon-owned regions only; marker installation requires explicit preview and undo.** | Reduces accidental instruction-file damage, but adds a setup step. |
| Trust keys | **Use scoped pinned keys for trusted imports; unknown-key signatures stay quarantined.** | Strong anti-laundering posture, but requires key management UX. |
| Retention | **Define tombstone/purge semantics before alpha; state plaintext storage until encryption is implemented.** | Honest privacy posture, but delays stronger enterprise claims. |
| `.canonpack` contents | **Default to by-reference evidence plus receipts; raw content only under explicit local/private disclosure profile.** | Safer portability, but offline full-fidelity imports need deliberate packing. |
| Telemetry | **Keep telemetry absent until an off-by-default, content-free event schema is approved.** | Preserves trust and simplicity, but delays usage analytics. |
| Receipt primitives | **Reuse Emet/Flywheel/Relay patterns through small adapter seams; do not vendor or depend until license/API review.** | Faster design leverage, but implementation must choose dependency strategy later. |
| 14B/32B evidence | **Keep release evidence blocked until endpoint gates exist and release ownership reconciles the 14B CI artifact with release docs.** | Avoids false readiness claims, but delays local-model benchmark use. |
| Full workspace index | **Use bounded source selections and timeout receipts until a retained full Index graph snapshot is available.** | Keeps work moving, but forbids complete-workspace architecture claims. |

## Public Release Definitions

Public alpha means:

- non-colliding name/package/CLI policy approved,
- security, contributing, conduct, governance, support, changelog, roadmap, and issue/PR templates drafted,
- alpha CLI can compile/preview/doctor/export/rescue/import-review/undo on local example fixtures,
- schemas and fixture zoo have initial public-safe examples,
- CI runs tests, docs checks, secret scan, package build dry-run, and conformance dry-run,
- adapter claims are descriptor-backed and conservative,
- no ecosystem-standard, provider-partnership, or broad enforced-bootstrap claim.

Beta means:

- JSON Schema, fixture zoo, conformance CLI, adapter matrix, docs site, signed prereleases, migration policy, and accessibility checks are in place,
- at least one clean-room or independent read-only capsule reader passes the fixture suite,
- package/install names remain stable enough for external implementers,
- public docs include troubleshooting for stale sources, secret quarantine, unsupported hosts, dirty worktrees, quota exhaustion, and offline use.

1.0 means:

- stable semver contracts for capsule schema, record migration, CLI JSON, MCP resources, SDK APIs, conformance fixtures, and generated `CANON.md`,
- release artifacts are reproducible, signed or attestable, SBOM-backed, secret-scanned, and built from clean tags,
- security response and retention/deletion policy are operational,
- at least one independent or clean-room implementation passes read/write or read-only conformance as applicable,
- accessibility gates pass for all public user workflows.

Ecosystem standard means:

- multiple maintained implementations,
- public compatibility reports tied to signed conformance artifacts,
- neutral governance or published RFC process,
- provider-neutral adapter registry with owners, last-verified dates, failure modes, and retirement criteria,
- documented long-term support and security branch policy,
- adoption metrics that justify standardization claims.

## Next Recursive Loop

Orient:

- Review this proposal against the six audit lanes and validation conditions.
- Record operator decisions for naming, scope, disclosure, trust, retention, telemetry, Enforced wording, and I0.

Map:

- Produce a bounded Index snapshot strategy with timeout receipts.
- Create the capability catalog for schemas, fixtures, adapters, CLI commands, witnesses, and release gates.

Diagnose:

- Fix the FilesBackend validation blocker before any import path.
- Reconcile V-C1 adapter tiers, V-C2 external receipts, V-C3 14B/32B release evidence, and V-C4 full workspace index evidence.

Convert:

- Turn report prose into schemas, fixtures, command contracts, and acceptance gates.

Prioritize:

- Wave 1 schema/fixtures, Wave 2 deterministic CLI spine, Wave 3 security hardening.

Design:

- Write a file-level implementation plan only after operator review. Include tests-first checkpoints and rollback behavior.

Execute:

- Implement without editing audit reports, protected I0 artifacts, or release metadata beyond approved scope.

Evaluate:

- Run dry-plan gates first; run live model/provider benchmarks only after explicit approval.

Catalog:

- Add adapter descriptors, conformance reports, capability artifacts, and release blockers to the capability catalog.

Roadmap Update:

- Move completed gates from proposal to shipped evidence. Keep blocked/null claims visible.

Recursive Reflection:

- Convert repeated friction into reusable checks only when future leverage exceeds maintenance cost.

Next Loop:

- After operator decisions, produce the implementation plan for the deterministic local spine: schema fixtures, compiler, `CANON.md`, doctor, preview, readiness, witness, and undo.
