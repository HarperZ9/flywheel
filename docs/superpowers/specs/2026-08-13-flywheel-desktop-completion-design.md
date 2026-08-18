# Flywheel Desktop Completion Design

Version: 1.0-approved
Last updated: 2026-08-14
Status: Approved for implementation planning and subagent-driven execution.
Eventual repository path: docs/superpowers/specs/2026-08-13-flywheel-desktop-completion-design.md

## 1. Decision

Flywheel Desktop will center on one server-owned, continuously persisted Evidence Journey. The desktop will present three equal lenses over the same facts and event head:

- Rescue: what broke, what is recoverable, and the safest next action.
- Diagnose: what the evidence supports, contradicts, or leaves missing.
- Verify: which checks ran, which receipts support them, and what may be accepted.

Lenses may reorder explanations and actions, but must not change facts, claims, checks, verdicts, missing evidence, stage, or head. Python owns evidence admission, events, projections, checks, receipts, verdicts, permissions, and capabilities. Flutter owns presentation, accessible interaction, view state, and recoverable local drafts. Flutter must not derive evidence truth or treat receipt presence as verification. This preserves the engine and desktop boundary in AGENTS.md:10-17 and desktop/CLAUDE.md:3-19.

The exact delivery order is normative:

1. Server-owned Journey persistence and continuous check events.
2. Journey-first Flutter.
3. Broader desktop truth, safety, work-loss, and permission repairs.
4. Focused navigation, accessibility, and recovery.
5. Contextual Incident Compiler, Frontier Claims, and Domain Packs after backend contracts.
6. Windows release integrity.

No later phase may become an implementation prerequisite for an earlier phase. Python containment is an independent capability gate and does not reorder these phases. The approved rollout likewise places Journey before incidents, Frontier work, and packs: docs/superpowers/plans/2026-08-12-unified-evidence-journey-rollout.md:60-80.

## 2. Accepted transport baseline

Commit 665ef5e is the terminally accepted Evidence Journey CLI and Gateway Transport baseline. It supersedes the earlier a990fe6 baseline through additional URI metadata hardening. It exposes strict start, project, check, export, and recheck actions: harness/evidence_route.py:14-24 at 665ef5e.

The integration must preserve all accepted transport properties:

- strict, bounded JSON; exact field allowlists; fixed typed errors
- recursive rejection of secret-shaped data, secret-bearing names, host paths, decoded file URI references, and secret-bearing HTTPS query or fragment names
- admission of structurally valid public HTTPS metadata
- typed safe relative references, including nested references, contained beneath one evidence root
- strict validation of downstream results and fixed non-echo messages
- no provider, endpoint, model, or network dispatch from evidence routes
- pre-admission Python refusal with UNVERIFIABLE, EXECUTION_CONTAINMENT_UNAVAILABLE, zero oracle calls, no candidate read, no child process, and no receipt

The public metadata and result boundary is implemented in harness/evidence_route.py:69-160; safe reference containment is in harness/evidence_route.py:173-207; the fixed unexpected-failure boundary is in harness/evidence_route.py:275-290, all at 665ef5e. URI security coverage is in tests/test_evidence_route_uri_security.py:27-113 at 665ef5e. Python refusal occurs before candidate admission in harness/evidence_packet.py:81-107, returns the typed null from harness/python_execution_containment.py:1-43, and is covered against read, spawn, receipt, and false PASS or FAIL in tests/test_evidence_packet_containment.py:88-145, all at 665ef5e.

Acceptance of this transport proves its tested parsing, metadata, reference, error, routing, and Python-refusal behavior. It does not prove durable server custody, opaque Journey references, compare-and-swap, idempotency, restart recovery, continuous check events, cancellation, Flutter integration, general Python containment, or release readiness. The accepted Journey is currently a deterministic value object: harness/evidence_journey.py:229-300 at 665ef5e.

## 3. Server-owned Journey contract

The server will generate an opaque journey_ref after authentication. Its wire form is jrn_ plus 32 lowercase hexadecimal characters. Clients must never supply or infer a storage path. A legacy journey_id may remain a display label but must not select storage.

Every mutation must:

1. pass the accepted strict JSON, public metadata, safe-reference, authentication, and ownership checks
2. take an exclusive per-Journey lock and reread the authoritative head
3. compare expected_event_head; on mismatch append nothing and return HEAD_CONFLICT
4. bind the canonical request digest to client_request_id
5. atomically write an immutable hash-chained event, rebuild the projection, then atomically replace and flush the head
6. acknowledge only after the event and head are durable

A retry with the same idempotency key and digest returns the original result. Reuse with a different digest returns IDEMPOTENCY_MISMATCH. Recovery must deterministically complete or quarantine orphan writes, rebuild indexes from immutable events, preserve the last authoritative head, and record its outcome. Storage failure returns STORE_COMMIT_FAILED; it never reports saved.

Journey stages remain intake -> decomposed -> preflight -> running -> concluded -> exported. Operational events do not consume stage transitions. Each check first commits check_requested. A denied permission, unavailable oracle, unsupported capability, or missing containment commits check_blocked. An admitted run commits check_started before execution and exactly one terminal check_completed, check_failed, or check_cancelled event. Recovery must close every abandoned start with a typed terminal event unless it can prove reattachment to an owned active process. Pre-admission Python refusal creates no receipt, preserving 665ef5e.

## 4. Ownership, states, and errors

| Layer | Owns | Must not own |
|---|---|---|
| Flutter | Drafts, view and focus state, accessible UX, typed API client | Evidence admission, verdicts, receipt truth, event heads |
| Transport | Strict public JSON, fixed errors, safe refs, route boundary | Storage durability or UI state |
| Journey service and store | Admission, transitions, CAS, immutable events, projections, recovery | Uncontained execution |
| Oracle and packet services | Admitted checks, raw outcomes, export, strict recheck | Journey storage or implicit code execution |
| Permission service | Exact-scope grants, consumption, cancellation authority | UI-only consent state |
| Release system | Payload identity, provenance, signatures, installed acceptance | Product evidence semantics |

| Domain | Required states |
|---|---|
| Connection | starting, online, degraded, offline, auth_required, version_mismatch |
| Journey | six canonical stages; operations idle, appending, checking, exporting, rechecking, conflicted, blocked, failed |
| Verdict | PASS, FAIL, UNDECIDED, UNVERIFIABLE |
| Receipt | missing, present_unchecked, MATCH, DRIFT, TAMPERED, UNVERIFIABLE |
| Draft | clean, dirty, saving, saved, save_failed, recovery_available |
| Permission | not_requested, requires_approval, approved_once, denied, expired |
| Execution | proposed, approval_required, queued, running, cancel_requested, cancelled, completed, failed |
| Containment | unavailable, read_only, process_contained, policy_rejected |

Receipt presence starts at present_unchecked; only verification may produce MATCH. The accepted flywheel.evidence-transport-error/v1 envelope and codes remain stable. New durable behavior adds INVALID_JOURNEY_REF, JOURNEY_NOT_FOUND, HEAD_CONFLICT, IDEMPOTENCY_MISMATCH, STORE_BUSY, STORE_COMMIT_FAILED, INVALID_TRANSITION, RECEIPT_MISSING, RECEIPT_SCHEMA_MISMATCH, CHECK_TIMEOUT, PERMISSION_REQUIRED, PERMISSION_DENIED, APPROVAL_EXPIRED, CANCEL_UNAVAILABLE, UNSAVED_WORK, ENGINE_DEGRADED, AUTH_REQUIRED, and VERSION_MISMATCH. Errors must not expose secrets, host paths, tracebacks, candidate-controlled text, provider details, or raw exceptions.

## 5. Permission, cancellation, privacy, and containment

Every mutating or external call requires a short-lived, one-use grant bound to authenticated actor, exact Journey and head, canonical operation digest, tool, arguments, scopes, admitted data refs, expiry, and nonce. Any difference invalidates the grant. Global checkboxes are not approval. Write, exec, plugin, and network access default to denied; secrets use opaque credential handles and never enter Journey events.

Stop must request server cancellation for an exact operation. The server must signal its owned process tree, wait for a bounded terminal state, seal the result, and commit it. Flutter remains cancel_requested until that terminal event. Closing a view does not cancel. If cancellation cannot be guaranteed, return CANCEL_UNAVAILABLE; do not label observation detachment as Stop. Leave running remains absent until leases and reattachment have an accepted contract.

State is per user. Journey metadata excludes tokens, keys, raw environments, credentials, and unrelated files. Public projections apply the accepted metadata boundary. Exports show inventory and redaction preview and omit usernames and host paths by default. Drafts stay device-only until submitted. Telemetry is off by default. User-data ACLs permit writes only to the owner and required operating-system account. Deletion distinguishes drafts, append-only Journey tombstones, exports, and uninstall retention.

A non-executing evidence profile may ship after all six phases. It may persist and project Journeys, record blocked checks, verify hashes, schemas, signatures, Merkle proofs, packets, and admitted data-only checks, and render contract-gated read-only extensions. It must disable arbitrary Python, user tests, shell or build runners, agent write or exec, plugin calls, executable packs, and Incident-generated execution. Missing containment must retain the accepted EXECUTION_CONTAINMENT_UNAVAILABLE null and must never fall back to ordinary execution or claim sandboxing. General containment requires low-privilege identity, filesystem and executable allowlists, operating-system network denial, descendant termination, resource limits, minimal environment, secret isolation, enforcement receipts, adversarial tests on supported Windows versions, fail-closed initialization, and no bypass route.

## 6. Phase requirements and acceptance

| Phase | Normative scope | Exit condition |
|---|---|---|
| 1. Journey persistence | Integrate 665ef5e; add opaque refs, durable events and head, CAS, idempotency, recovery, listing, resumption, append, check lifecycle, cancellation contract | No acknowledged loss, duplicate logical event, silent overwrite, unclosed check request, or weakening of accepted transport behavior |
| 2. Journey-first Flutter | Make Journey the home; render equal Rescue, Diagnose, Verify projections; resume active Journey; retain local drafts until acknowledgment | Same facts and head in all lenses; restart resumes; failed or conflicted append preserves draft; Flutter derives no verdict |
| 3. Truth, safety, work loss, permission | Repair the P0 inventory below | Every defect has failing-before and passing-after regression evidence; no false verified label, default mutation, silent work loss, or fake Stop |
| 4. Navigation, accessibility, recovery | Add five groups, stable routes, search, keyboard and semantics, system-aware scaling, focus and recovery center | All destinations remain reachable; critical flows work by keyboard and screen reader at 200 percent scaling, high contrast, and reduced motion |
| 5. Contextual extensions | Add Incident Compiler, Frontier Claims, and Domain Packs only behind versioned backend capabilities | No empty or uncontracted surface; deterministic Incident graph; independent Frontier axes; admitted pack manifest, fixtures, license, limits, and containment class |
| 6. Windows integrity | Produce immutable manifest-bound, signed artifacts and installed-product evidence | Signed installer passes clean install, operation, persistence, upgrade, rollback, repair, uninstall, ACL, privacy, license, and provenance gates |

Phase 3 P0 inventory:

- Chat must preserve a no-model prompt, represent a missing receipt, and never label receipt presence verified.
- Code must retain dirty buffers across navigation and require Save, Discard, or Cancel on closure, with digest-aware crash recovery.
- Agent write and exec default to false; Stop must replace observation-only Detach semantics.
- Plan Run must bind the complete forged prompt, PRP identity, gates, and seal and reject drift.
- Dart and gateway receipt-proof schemas must agree; Flutter must recompute inclusion before MATCH.
- Plugin and agent mutations must require exact-scope grants.
- Connection must distinguish degraded, offline, authentication, startup, and version mismatch.
- Mouse-only controls must gain semantics and keyboard actions; application scaling must combine with the system scaler rather than replace it.

The current defects are evidenced in desktop/lib/views/agent_view.dart:128-130, desktop/lib/widgets/chat_composer.dart:65-70, desktop/lib/widgets/chat_thread.dart:98-143, desktop/lib/views/code_view.dart:52-59,236-248, desktop/lib/ide/agent_panel.dart:46-58,148-157, desktop/lib/views/plan_view.dart:99-152, desktop/lib/views/receipts_view.dart:257-295, harness/gateway.py:1273-1296,2082-2091, and desktop/lib/main.dart:82-101,127-137,212-238.

## 7. Navigation, accessibility, and recovery

The five groups are:

- Work: Journey, Plan, Workflows, Projects
- Chat: Chat, Compare, Models, Companion
- Code: Code, Eval, Audit, Lint
- Evidence: Receipts, Science, World, Memory, Governance, Usage
- Advanced: Studio, Graph, Feeds, Discourse, Academy, Lessons, Instruments, Lanes, Train, Uplift, Family, Plugins

All 29 current destinations remain reachable through grouping, search, and command palette: desktop/lib/main.dart:165-195. Stable route IDs replace label routing; history preserves Journey, selection, view, and scroll state; deep links carry only opaque public refs. Every pointer action needs a semantic keyboard equivalent and visible focus. Verdicts and connection states use text and iconography, not color alone. The UI respects system scaling, reduced motion, and high contrast.

The Recovery Center lists unsent chat drafts, dirty code snapshots, pending Journey requests, interrupted operations, incomplete migrations, and failed updates. Restore offers only actions valid for the typed state and never changes server evidence without a newly admitted event.

## 8. Contextual extensions

Incident Compiler appears only for an active Journey when the capability endpoint advertises its exact schema. It produces a proposed claim and check graph that cannot self-accept. Read-only compilation may precede containment; generated execution may not.

Frontier Claims appears inside Diagnose and Verify only after server-owned identification, verification, policy, and value axes exist. Axes and nulls remain independent and never collapse into a composite score. Flutter only renders them.

Domain Packs require versioned Journey and packet schemas, claim and oracle types, deterministic fixtures, declared data and execution capabilities, containment class, license, resource limits, and public-metadata policy. Data-only packs may be admitted separately; executable packs remain locked until containment.

## 9. Migration

Integrate the accepted 665ef5e transport without weakening its validators or nulls. Do not rewrite v1 Journey values. Import each as a legacy snapshot with its digest, then create a v2 genesis event that cites the snapshot and states that earlier continuous custody is not proved. Do not invent operational history. Existing chats, workspaces, settings, and receipts remain legacy references unless the user imports them.

Store migrations are versioned, deterministic, idempotent, journaled, backup-first, and atomic. Failure restores the prior head and version pointer while preserving diagnostics. Unsupported newer schemas open read-only with safe export; mutation returns VERSION_MISMATCH. Packet migration creates a derived packet and never changes original bytes. Upgrade and rollback preserve newly committed events; an incompatible binary rollback enters read-only repair mode. Per-user uninstall preserves Journeys and drafts by default.

## 10. Windows release integrity

Build and test jobs use read-only repository permission. A separate protected publish job receives release-write permission only after verification. Existing release assets cause failure; publication never overwrites them. Unified tag, package, desktop, executable, installer, API, manifest, and release-title versions are required: AGENTS.md:24-32.

The release must use pinned toolchains, a default-reject payload manifest, complete hashes, SBOM, third-party notices, font provenance, privacy inventory, and signed provenance. Authenticode-sign and timestamp the installer and shipped executables, then verify signatures before packaging, after download, and after installation. Reject secrets, credentials, local databases, caches, models, weights, training data, unrelated corpora, host paths, and undeclared libraries. Current workflow overwrite behavior and broad release permission must be removed: .github/workflows/desktop-release.yml:22-24,110-122.

A clean Windows virtual machine must test per-user install and ACLs, bundled authenticated loopback engine, Journey persistence across restart, packet export, Stop and process cleanup, upgrade, one-version rollback, repair, uninstall with explicit data retention, manifest and signature agreement, absence of unexpected services or telemetry, privacy notice, licenses, and fonts. Source tests and a Windows build do not prove installed acceptance: .github/workflows/desktop-ci.yml:17-48.

## 11. Success thresholds and blockers

| Measure | Threshold |
|---|---|
| Acknowledged event loss, duplicate logical events, silent head overwrite | Zero |
| Check requests without one terminal outcome after recovery | Zero |
| Prompt or dirty-buffer loss in accepted close, crash, restart cases | Zero |
| False verified labels or unauthorized mutations | Zero |
| Lens consistency | Identical fact IDs, checks, verdicts, stage, conclusion, and head |
| Accessibility | Every critical flow keyboard reachable and screen-reader usable at 200 percent scale |
| Release identity | Every payload listed, hashed, signed where executable, and provenance-bound |
| Installed release | Every release-blocking installed E2E scenario passes on the signed candidate |
| Upgrade and rollback | One supported version each with zero Journey loss |

Any of these blocks release: path-selectable or escaping Journey refs; acknowledge-before-durability; lost or rewritten events; unclosed checks; presence-only verification; stale or global grants; execution bypass; fake Stop; silent prompt or buffer loss; secret, host-path, or hidden-payload export; manifest drift; unsigned or mismatched binaries; Journey loss on upgrade or rollback; broad user-data ACLs; containment fallback; or sandbox claims without the full boundary.

## 12. Non-goals and limitations

Non-goals are evidence logic in Dart, replacement copies of all current tools, another general coding-agent race, autonomous mutation, cloud Journey custody, cross-device sync, collaboration, leases, machine-wide first release, automatic background update, fabricated custody for legacy data, composite trust scores, or early top-level destinations for contextual extensions.

This architecture is approved, but the written specification still awaits review and desktop completion implementation has not begun. The accepted transport is deterministic and file-scoped, not a durable Journey store. General Python containment, signing infrastructure, supported Windows versions, and font redistribution evidence remain unresolved implementation or release inputs. No public release is permitted before all six phases pass, even if it uses the non-executing profile.

## 13. Handoff and completion

The future implementation plan must assign one owner per work package and supply detailed file ownership, dependency steps, exact tests, and rollback commands. Each handoff must identify source commit and workspace digest, completed and deferred scope, interface versions and fixtures, commands and receipts, artifact hashes, risks, limitations, and receiving-owner acceptance. A release-blocking deferral prevents phase completion; chat statements do not replace receipts.

Desktop completion requires all six phases, equal server-projected lenses, zero listed truth and work-loss defects, exact one-use grants, real terminal Stop, a technically and visibly distinct non-executing profile, arbitrary execution locked until containment, and a fresh hash-bound acceptance packet for the exact source and installed artifacts. Until then, use a narrower evidenced status such as non-executing beta, containment-blocked, or rejected release candidate.
