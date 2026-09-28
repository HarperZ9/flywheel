# Plan: Rowan's flagship remote for clean upkeep

> Status: PLAN. Nothing here is built. Sequenced after 1.0-ready
> (see [RELEASE-1.0-READINESS.md](../RELEASE-1.0-READINESS.md)). This document
> designs the work and marks the decisions the operator still owns. It does not
> authorize a build.

Author cursor date: 2026-09-11.

## The ask

Operator directive: "Rowan will also need a flagship remote to ensure clean
upkeep." Rowan is the assistant that operates Flywheel and the face of the
product. A flagship remote for clean upkeep is a first-class surface through
which Rowan keeps a running Flywheel instance healthy and maintained, from the
operator's phone or another machine, bound to the same accountability spine as
every other Rowan operation.

Two readings of "clean upkeep" are possible, and they converge on the same need:

- Upkeep of a running instance: health, lifecycle, orphan cleanup, receipt and
  grant integrity.
- Upkeep the operator can drive remotely, so a phone can check and repair a
  workstation without a desk session.

The plan serves both. The disambiguation the operator owns is how much remote
actuation to allow, not whether the surface is about maintenance.

## What already exists, so this extends rather than invents

The transport and the operation spine are already in the repo. A remote-upkeep
surface reuses them.

Transport:

- relay: a remote MCP server over OAuth that lets Claude on a phone drive the
  local agent loop. Submodule, source not checked out in every worktree.
  Documented in `docs/REMOTE-ACCESS.md`. Remote shell exec is off by default
  behind `RELAY_ALLOW_REMOTE_EXEC`.
- The local gateway HTTP API with bearer auth. Private routes require a
  configured token and resolve an owner (`harness/gateway.py`, `_authorized` at
  line 805). Relay run state is already surfaced at `/api/relay/status`,
  `/api/relay/result`, `/api/relay/remote`.
- The Android companion pairs with the gateway and starts supervised Rowan
  operations through the same Journey-bound controller as the desktop shell. A
  mobile approval inbox reads owner-scoped grant proposals
  (`docs/mobile-approval-inbox-backend.md`).

Operation spine:

- The grant-bound `agent.run` lifecycle Rowan drives through the shared
  operation host (`desktop/lib/controllers/rowan_operation_controller.dart`,
  `harness/gateway_operations.py`). A walkthrough and a real operation take the
  same admitted path.
- One-use, exact-scope operator grants (`harness/operation_grants.py`).
- Sealed, content-addressed tool-call receipts, chain-linked and offline
  verifiable (`harness/tool_call_receipt.py`).
- TADR governance tiers with a no-inflation gate
  (`harness/governance/tadr_tier.py`).
- Operations bound to the operator's authenticated CLI identity
  (`harness/gateway_cli_runtime.py`).

Maintenance operations that already run, scattered:

- Per-lane MCP `status` and `doctor` probes, with a STALE verdict when a lane
  has no health tool (`harness/lanes.py` around line 114).
- Gateway lifecycle: `flywheel up` and `flywheel down`
  (`harness/cli_entry.py`).
- Read-only connection facts at `/api/desktop/status`
  (`harness/desktop_status.py`).
- Orphan and stray-process reaping: `harness/proc_kill.py`,
  `harness/operation_supervisor.py`, and the installed launch-acceptance census
  under `desktop/tool/`.

## The concrete gap

There is no unified upkeep command or endpoint that binds these signals into one
accountable report. There is no `flywheel doctor`. Health is spread across lane
MCP tools, gateway lifecycle, the desktop status route, and the launch-acceptance
census, each reachable on its own. A remote for clean upkeep needs that unified
surface first. The remote is the second half, not the first.

## Design, phased

### Phase A: the upkeep spine, local first

Build one upkeep surface that aggregates the existing health signals into a
single report with a witnessing-spine verdict (MATCH, DRIFT, UNVERIFIABLE):

- A `flywheel doctor` CLI command and a matching `/api/upkeep/report` gateway
  route.
- The report gathers lane readiness, gateway lifecycle state, desktop status,
  the orphan and stray-process census, receipt-chain integrity, and grant-store
  health, and gives each a verdict rather than a raw dump.
- Every upkeep read produces a tool-call receipt through the existing primitive,
  so the report itself is re-verifiable offline. This matches the platform's
  re-derivable-correctness wedge: the product is a report a stranger can
  re-walk, not a status page you have to trust.
- Read-only by default. TADR tier for a read is T1.

Phase A is independently useful. A local `flywheel doctor` earns its place even
if the remote never ships. It also closes a real 1.0 rough edge: today an
operator diagnosing a sick instance has to know four separate surfaces.

### Phase B: the remote

Expose the Phase A spine over the transports that already exist:

- A relay MCP tool pair, `upkeep.report` (read) and `upkeep.run` (actuate), so a
  phone can request a report and see the verdict.
- Any actuation, restarting a lane, reaping an orphan, rotating a token, is a
  grant-gated operation, not a bare call. It flows through the one-use grant
  path and shows up in the mobile approval inbox for the operator to approve on
  the phone. TADR tier for actuation is T2, so the no-inflation gate applies.
- Rowan drives the whole thing through the shared operation host, the same
  admitted path as every other operation. No new operation lifecycle.
- Honest nulls stated on the surface: what the remote can read, what it can
  actuate, and that nothing actuates without an approved grant.

### Phase C: the flagship polish

- A desktop and Android upkeep panel, verdict-only color, one action to run
  upkeep and read the verdict back.
- The signed upkeep report is the deliverable Rowan reads aloud or shows: a
  re-verifiable receipt of the instance's health at a moment in time.

## Boundaries and non-goals

- Not a new transport. Reuse relay and the gateway API.
- Not remote shell exec by default. It stays off behind
  `RELAY_ALLOW_REMOTE_EXEC`, and the upkeep surface does not turn it on.
- Not remote actuation without a grant. Every repair is one-use, approved on the
  inbox, and receipted.
- Not built until 1.0-ready. Phase A can begin as normal 0.x development once
  the 1.0 open items are closed; the remote layer follows.

## Sequencing

After 1.0. Phase A is the prerequisite and stands on its own. Phase B and C are
the flagship remote. None of it blocks the 1.0.0 cut, and none of it should
start before the three 1.0 open items are closed (installer publish, the chat
draft store fix, the STATE.md catch-up).

## Decisions the operator owns

1. Remote actuation scope. Read-only upkeep only, or grant-gated remote repair
   too (restart a lane, reap an orphan, rotate a token)? The plan assumes
   grant-gated repair is in scope but off until each grant is approved.
2. Surface priority. Desktop-first upkeep panel, or Android-first, given the
   phone is the natural home for a remote? This depends on how far the Android
   companion has matured, which is outside this worktree.
3. Naming. `flywheel doctor` matches the per-lane `doctor` convention already in
   the code. Confirm that is the command name before Phase A starts.
