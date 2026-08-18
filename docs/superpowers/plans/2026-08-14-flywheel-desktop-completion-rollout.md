# Flywheel Desktop Completion Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved Flywheel Desktop Completion design in six ordered, independently reviewable phases ending in immutable signed Windows installed acceptance.

**Architecture:** A durable Python Journey service owns facts, events, permissions, checks, receipts, and projections; Flutter renders typed projections and keeps only recoverable device-local drafts and view state. Contextual extensions consume accepted capability contracts, and the Windows pipeline binds the exact source, payload, signatures, installation, and acceptance evidence without changing product evidence semantics.

**Tech Stack:** Python 3.11+ standard library accept path, canonical JSON and SHA-256, pytest, Flutter 3.44.6, Dart 3.6+, Windows PowerShell, PyInstaller 6.21.0, Inno Setup 6, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-13-flywheel-desktop-completion-design.md`

## Global Constraints

- No learned model on the accept path.
- No receipt, no accept; denominators and `does_not_prove` are mandatory.
- No later phase may become an implementation prerequisite for an earlier phase.
- Python containment is an independent capability gate and does not reorder these phases.
- Flutter must not derive evidence truth or treat receipt presence as verification.
- Write, exec, plugin, and network access default to denied; secrets use opaque credential handles and never enter Journey events.
- Telemetry is off by default.
- Missing containment must retain the accepted EXECUTION_CONTAINMENT_UNAVAILABLE null and must never fall back to ordinary execution or claim sandboxing.
- No provider, endpoint, model, or network dispatch from evidence routes
- New Python and Dart files stay at or below 300 physical lines.
- The verifier path keeps zero third-party runtime dependencies.
- Existing public paths, secrets, private artifacts, and historical receipts never enter fixtures.
- Each implementation task uses RED, GREEN, focused regression, gates, review, then a narrow commit.
- No public release is permitted before all six phases pass, even if it uses the non-executing profile.

---

## Execution contract

The previously chosen execution mode is **subagent-driven**. Execute one fresh implementation worker per numbered task, then run specification review and code-quality review before the next task. Tasks inside a phase are serial at their shared-file boundaries; no two active workers edit the same source, test, workflow, or record file.

```text
Phase 1 Journey persistence
  -> Phase 2 Journey-first Flutter
    -> Phase 3 truth and safety repairs
      -> Phase 4 navigation, accessibility, recovery
        -> Phase 5 contextual extensions
          -> Phase 6 immutable Windows release acceptance
```

- [ ] Record `git rev-parse HEAD` and `git status --short` before P1-T1; require the accepted `665ef5e` transport to be an ancestor and a clean task boundary.
- [ ] Execute each phase plan in order; do not begin the next phase until its acceptance receipt is reviewed and rechecked.
- [ ] After every task, run its focused tests, `python scripts/check_file_gate.py`, and `git diff --check` before the scoped commit.
- [ ] After every phase, run the full phase gate, archive hashes and commands in its record, and accept or revert before dispatching the next worker.
- [ ] Do not invoke a provider, live service, publication, deployment, or release-upload path while implementing or reviewing these plans.

## Canonical interface vocabulary

| Name | Exact meaning |
|---|---|
| `journey_ref` | Server-generated storage selector matching `^jrn_[0-9a-f]{32}$`; never a path or client choice. |
| `expected_event_head` | Client CAS input: the last acknowledged 64-hex event hash, or `null` only for creation. |
| `event_head_sha256` | Authoritative server projection head shared unchanged by Rescue, Diagnose, and Verify. |
| `client_request_id` | Caller-generated idempotency key bound durably to one canonical request SHA-256. |
| `operation_ref` | Server-generated `op_` plus 32 lowercase hex characters for an exact check or external operation. |
| `grant_ref` | Server-generated `grn_` plus 32 lowercase hex characters for one exact, expiring, one-use authorization. |
| `owner_ref` | Stable opaque per-user identity persisted independently of the rotatable bearer token; it is copied internally to event `actor_id` and omitted from public projections/exports. |
| receipt state | Exactly `missing|present_unchecked|MATCH|DRIFT|TAMPERED|UNVERIFIABLE`; presence is never `MATCH`. |

## Phase index, dependencies, and source ownership

| Phase | Plan and ordered tasks | Exclusive source ownership | Depends on |
|---|---|---|---|
| 1 | [Journey persistence](2026-08-14-flywheel-desktop-completion-phase-1-journey-persistence.md), P1-T1 through P1-T7 | `harness/journey_*`, `harness/operation_grants.py`, durable route/CLI adapters, matching Python tests and Phase 1 record | accepted transport commit `665ef5e` |
| 2 | [Journey-first Flutter](2026-08-14-flywheel-desktop-completion-phase-2-journey-flutter.md), P2-T1 through P2-T6 | Journey Dart models/client/controller/draft stores/widgets, startup wiring, matching Flutter tests and Phase 2 record | P1 receipt `MATCH` |
| 3 | [Truth and safety](2026-08-14-flywheel-desktop-completion-phase-3-truth-safety.md), P3-T1 through P3-T7 | chat/code/plan/receipt/permission/operation/connection repairs and matching tests/record | P2 receipt `MATCH` |
| 4 | [Navigation and accessibility](2026-08-14-flywheel-desktop-completion-phase-4-navigation-accessibility.md), P4-T1 through P4-T6 | navigation catalog/controller/search, accessible shared controls, Recovery Center, matching tests/record | P3 receipt `MATCH` |
| 5 | [Contextual extensions](2026-08-14-flywheel-desktop-completion-phase-5-contextual-extensions.md), P5-T1 through P5-T6 | capability contract, Incident/Frontier/Pack backend and contextual Journey panels, fixtures/tests/record | P4 receipt `MATCH` |
| 6 | [Windows release](2026-08-14-flywheel-desktop-completion-phase-6-windows-release.md), P6-T1 through P6-T6 | release manifest/inventory/signing/install scripts, installer and workflows, matching tests/record | P5 receipt `MATCH` and signing/release inputs admitted |

Within a phase, the task plan is the ownership ledger. A receiving worker may modify a file owned by an earlier task only when its `Consumes` block names that interface and its `Files` block explicitly lists the modification.

## One-to-one requirement ledger

| Requirement | Only implementation owner | Acceptance evidence |
|---|---|---|
| R01: preserve v1 path-style refs while v2 uses opaque selectors | P1-T1 | selector-boundary and accepted-v1 regression vectors |
| R02: genesis sentinel, CAS, idempotency, locking, fsync, and acknowledge-after-durability | P1-T2 | crash-point and 20-race denominators with zero loss/duplicates |
| R03: bearer auth is not identity; stable owner plus minimal exact Journey grant | P1-T3 | token-rotation, owner-isolation, TTL, one-use, lock/burn tests |
| R04: backup-first migration and legacy custody honesty | P1-T4 | byte-preservation, `custody_before_import:false`, rollback receipt |
| R05: continuous check events, abandoned-start recovery, and Journey-check cancellation | P1-T5 | lifecycle/terminal-event matrix and accepted Python null regression |
| R06: authenticated transport/CLI without changing `665ef5e` | P1-T6, accepted by P1-T7 | route/CLI/public-helper characterization plus exported packet recheck |
| R07: defensive Journey contracts and exact client bodies | P2-T1/P2-T2 | malformed/unknown-value and request-body fixtures |
| R08: durable drafts, startup resume, equal lenses, Journey-first shell | P2-T3 through P2-T6 | restart/conflict/offline/lens-equality and 29-destination regressions |
| R09: chat admission, draft retention, and receipt honesty P0 | P3-T1 | no-model/error/navigation/restart prompt matrix |
| R10: dirty Code close/crash protection P0 | P3-T2 | file/workspace/route/app-close and digest-conflict matrix |
| R11: all mutation/external/plugin scopes default denied P0 | P3-T3 | absent/wrong/expired/reused/exact-once grant matrix |
| R12: agent defaults and real server-terminal Stop P0 | P3-T4 | owned-process, descendant, unavailable-cancel, terminal-state matrix |
| R13: Forge-to-Run binds PRP, prompt, gates, and seal P0 | P3-T5 | one-byte/order/ID/hash drift vectors with zero dispatch |
| R14: one receipt-proof wire schema and pure Dart inclusion recompute P0 | P3-T6 | cross-language known-answer/mutation vectors |
| R15: six connection states, system scaling, and critical-action access P0 | P3-T7 | typed transition, 2.0x1.2, semantics/keyboard/focus matrix |
| R16: exactly 29 existing destinations plus Journey in five groups | P4-T1/P4-T2 | 30-ID catalog, search/palette/reachability/history receipt |
| R17: complete accessibility and six-kind Recovery Center | P4-T3 through P4-T6 | semantic-action denominator, 200%, contrast, motion, recovery matrix |
| R18: exact extension capability negotiation grants no permission | P5-T1 | `flywheel.evidence-capabilities/v1` negative/stale/unknown vectors |
| R19: contextual Incident proposal cannot self-accept | P5-T2 | deterministic graph and zero append/execute/lesson calls |
| R20: Frontier maps all eight legacy axes losslessly into four independent groups | P5-T3 | values/nulls round-trip and no composite/novelty inference |
| R21: packs bind schema, fixtures, license, limits, and containment | P5-T4 | data-only admission, mutation QA, executable-lock matrix |
| R22: extensions remain contextual with backend re-authorization | P5-T5, accepted by P5-T6 | absent capability hides surface; exact stale-head/grant denials |
| R23: pinned identity, default-reject payload, notices/privacy/font/SBOM/provenance | P6-T1/P6-T2 | release-policy, manifest, inventory, and drift gates |
| R24: per-user retention/migration, signed immutable graph, clean installed acceptance | P6-T3 through P6-T6 | supported-target install/restart/upgrade/rollback/repair/uninstall packet |
| R25: no phase reordering and no publish/deploy authority | rollout final gate | six chained phase receipts and an unpublished no-clobber candidate |

## Interface handoffs

| From | To | Consumed interface and format | Acceptance condition |
|---|---|---|---|
| P1-T2/T3 | P1-T4 through Phase 6 | `flywheel.evidence-journey-event/v2`, `flywheel.evidence-journey-head/v2`, `flywheel.evidence-journey-projection/v2`; strict canonical JSON | restart replays to the same head and projection hash |
| P1-T3 | P1-T5, Phase 3 | `flywheel.operation-grant/v1`; Python dataclasses plus strict JSON | exact owner/Journey/head/digest/tool/arguments/scopes/refs/expiry/nonce match and one durable consumption |
| P1-T6 | Phase 2 | `/api/journeys/{create,list,resume,append,check,cancel,export}` request/response envelopes | accepted transport regressions stay green; errors remain `flywheel.evidence-transport-error/v1` |
| P1-T7 | Phase 5/6 | `flywheel.evidence-packet/v1` manifest plus immutable public-safe packet files | clean-directory stdlib recheck is `MATCH`; packet digest/schema is bound in every capability/release consumer |
| P2-T1/T2 | P2-T3 through Phase 5 | Dart `JourneyProjection`, `JourneyMutationAck`, `JourneyFailure`, and `GatewayJourneyApi` | defensive parse; server facts and head unchanged across lenses |
| P2-T3 | Phase 3/4 | `JourneyDraftStore` and `JourneySessionStore` device-local records | delete only after durable acknowledgement; restart restores active Journey |
| P3-T3/T4 | Phase 4/5 | exact-scope grant client and `OperationSnapshot` lifecycle | no default mutation and no terminal UI state before server terminal event |
| P3-T5 | Phase 6 | forged-plan binding fields `prp_id`, `prompt_sha256`, `gates_sha256`, `seal_sha256` | run refuses any drift before dispatch |
| P4-T2/T5 | Phase 5/6 | stable route IDs, `RecoveryItem`, `RecoveryAction`, and recovery journal schema | only opaque public refs; recovery never mutates evidence without admission |
| P5-T1 | P5-T2 through P5-T5 | `flywheel.evidence-capabilities/v1` rows with exact `id,schema,state,operations,journey_schema,packet_schema,containment_class,limits,reason,contract_sha256,acceptance_receipt_sha256` | panel renders only for `read_only|data_only|execution_locked|available`; advertisement grants no permission |
| P6-T1 | P6-T2 through P6-T6 | `flywheel.release-identity/v1` | tag/source/Python/Dart/PE/Inno/API/profile/policy hashes agree |
| P6-T4/T5 | P6-T6 | `flywheel.windows-release-manifest/v1`, signed candidate set, and `flywheel.windows-installed-acceptance/v1` | payload is allowlisted/provenance-bound and every supported target/scenario/signature rechecks |

## Phase review gates and acceptance receipts

| Phase | Mandatory gate | Acceptance receipt |
|---|---|---|
| 1 | full evidence/Journey Python suite, stdlib closure, accepted URI/containment regressions, crash-recovery matrix | `project-docs/records/2026-08-14-desktop-phase-1-journey-persistence.md` plus rechecked packet hash |
| 2 | focused Journey Flutter suite, `flutter analyze`, `flutter test`, lens equality and restart/draft recovery | `project-docs/records/2026-08-14-desktop-phase-2-journey-flutter.md` |
| 3 | every P0 failing-before/passing-after regression, Python/Flutter full gates, zero false verification or unauthorized mutation | `project-docs/records/2026-08-14-desktop-phase-3-truth-safety.md` |
| 4 | 30-route reachability, keyboard/semantics flows, 200 percent scale, high contrast, reduced motion, typed recovery | `project-docs/records/2026-08-14-desktop-phase-4-navigation-accessibility.md` |
| 5 | capability-negative tests, deterministic Incident graph, independent Frontier axes, admitted Pack QA, no executable-pack bypass | `project-docs/records/2026-08-14-desktop-phase-5-contextual-extensions.md` |
| 6 | signed clean-install/operate/restart/upgrade/rollback/repair/uninstall matrix on the exact candidate | `project-docs/records/2026-08-14-desktop-phase-6-windows-release.md` and `flywheel.windows-installed-acceptance/v1` packet |

Every phase record names source commit and tree digest, completed and deferred scope, interface/schema versions, fixtures, commands and exit codes, artifact hashes, risks, limitations, `does_not_prove`, and receiving-owner acceptance. A release-blocking deferral leaves the phase unaccepted.

## Rollback points

- [ ] Treat every numbered task commit as a rollback point; before the next task starts, a rejected task is reverted with `git revert --no-edit HEAD`, then its focused and phase-to-date gates rerun.
- [ ] At each phase boundary, tag the acceptance packet inside the record by source commit and packet SHA-256; rollback reverts phase commits in reverse order without deleting Journey or draft state.
- [ ] Store/schema rollback never rewrites v1 bytes or v2 events. An incompatible binary opens read-only repair mode and preserves the authoritative head.
- [ ] Phase 5 capability rollback changes an accepted capability to absent/rejected and hides its panel; it does not delete Journey facts.
- [ ] Phase 6 candidate rollback discards the unpublished candidate artifact set. Existing release assets are immutable and are never overwritten.

## Final acceptance sequence

- [ ] Confirm all six phase records identify the same dependency chain and no later phase became an earlier prerequisite.
- [ ] Run `python scripts/check_file_gate.py`, `python scripts/check_verifier_stdlib.py`, `python scripts/check_claim_language.py`, `python scripts/check_public_instructions.py`, `python -m harness.cli_entry gate`, and `python -m pytest tests/ -q`; expect exit 0 and gate PASS/rewitness MATCH.
- [ ] Run `flutter analyze` and `flutter test` in `desktop/`; expect exit 0.
- [ ] Recheck the final acceptance packet from a clean directory; expect `MATCH` for the exact source and installed artifact hashes.
- [ ] Keep the signed candidate unpublished until an explicit, separate publish authorization is recorded; this plan authorizes planning and implementation, not publication or deployment.
