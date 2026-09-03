# Continuation: native surface for the remaining action routes

Hand-off for the 0.3.11 release branch. The task this document set out is
finished: every route the gateway dispatches now has a native surface, and the
coverage gate is an equality at zero. What follows records the finished state,
the traps still worth reading before touching this area, and what is left
before a tag.

## Where this stands

| Check | Value |
|---|---|
| Route coverage | 133 of 133 reachable routes (100.0%) |
| Routes with no native surface | 0, baseline frozen at 0 |
| Dead routes | 0 |
| Desktop suite | 687 passed, 4 skipped |
| `flutter analyze` | clean |
| Repo gates | file gate, verifier stdlib, claim language, public instructions, UI coverage all PASS |

Reproduce the work list at any time:

```
python scripts/check_ui_coverage.py --list
```

The gate fails in both directions. A route that loses its surface fails it, and
a route that gains one fails it too until the baseline moves, because a stale
baseline is a gate that has stopped measuring. At zero the second direction
becomes an equality: a new route without a surface fails immediately.

## What was built

Fifteen routes had no surface. Six POST only because they carry a request body
and are semantically reads, so each got a view. Nine mutate, reach the network,
or spawn a process, so each goes through the operator-grant flow.

Read surfaces, a view and no grant:

```
/api/evidence   /api/governance/classify   /api/retrieve
/api/scaffold   /api/store/query           /api/frontier
```

Granted surfaces, one action each:

| Route | Action | Panel |
|---|---|---|
| `/api/bench/run` | `bench.run` | `bench_run_panel.dart` |
| `/api/capability` | `capability.probe` | `frontier_panel.dart` |
| `/api/import` | `import.config` | `import_config_panel.dart` |
| `/api/invent` | `invent.round` | `invent_panel.dart` |
| `/api/lane` | `lane.call` | `lane_call_panel.dart` |
| `/api/lean` | `lean.check` | `lean_check_panel.dart` |
| `/api/packs/admit` | `packs.admit` | `pack_admit_panel.dart` |
| `/api/store/entity` | `store.put` | `store_entity_panel.dart` |
| `/api/suite` | `suite.audit` | `suite_audit_panel.dart` |

Two routes in that list are read-shaped and still granted. `/api/capability`
runs a real generation against a live endpoint and costs whatever that endpoint
costs. `/api/frontier` only reads the table those probes wrote, so the probe is
granted and the table is not.

The `bench.run` question is settled. There is one route and one action.
`/api/bench/run` appears in `action_for_path`, so a bare body is refused with
422 before any task runs, and `bench_run_panel.dart` is the only surface.

Two of the fifteen were GET, not POST, contrary to the first reading of the
work list: `/api/governance/classify` and `/api/frontier`.

## The infrastructure controls, added after that

`harness/infra/` had eleven modules and no way to reach any of them from the
app. Six routes and one destination close that. `harness/infra_route.py` holds
the handlers and `desktop/lib/views/infra_view.dart` is the destination.

| Route | Shape | Surface |
|---|---|---|
| `/api/infra/trust-model` | read | `TrustModelPanel` |
| `/api/infra/bom` | read | `RunBomPanel` |
| `/api/infra/egress` | read | `EgressPanel` |
| `/api/infra/credential-scan` | `infra.credential_scan`, scope `secrets` | `CredentialScanPanel` |
| `/api/infra/isolation` | `infra.isolation`, scope `network` | `IsolationProbePanel` |
| `/api/infra/kill` | `infra.kill`, scopes `exec network secrets` | `KillSwitchPanel` |

The three that act are granted for concrete reasons. A credential scan reads
where secrets live. An isolation probe leaves the machine on purpose. The kill
switch tries to stop a running agent, and it needs two different authorities
before the engine will even prepare it.

Two facts on the kill receipt are not the same fact and the panel shows both.
`seal_body.executed` records that two authorities confirmed the request.
Whether anything ran is `any_executed`, and without `FLYWHEEL_KILL_SWITCH_LIVE`
in the engine's environment every action reports `executed: false` with its
reason. Collapsing those two into one pill would report a shutdown that never
happened.

Two comparisons live in the engine rather than in Dart, because a second
implementation of a comparison is a second chance to disagree with the first.
The trust model returns `single_point_agreement` alongside its declared and
derived lists, and the egress read returns `verdict_counts` alongside its
receipts.

## The grant flow to follow

Build a `GatewayOperation.exact(action:, clientRequestId:, operation: {...})`,
pass it through `authorizeGatewayOperation`, or `authorizeGatewayStream` for a
streaming route, in `desktop/lib/widgets/operation_grant_sheet.dart`, and act
only inside the callback once the operator has granted it.

Server-side, the action names and their field sets live in `_FIELDS` in
`harness/gateway_operation.py`. An action not in that table cannot be
expressed, and a field not in its set is refused during canonicalization before
any worker starts. `GRANTABLE_ACTIONS` is derived from that same table, so the
prepare route and the dispatcher cannot disagree.

The client does not restate `_FIELDS`. It mirrors only what it must render
before the engine answers: the destination kind and ref, and the scope list.
`desktop/lib/models/gateway_operation_internals.dart` holds that mirror and
`desktop/test/action_route_grants_test.dart` locks it against
`harness/gateway_operation_shape.py`. An extra field therefore builds on the
client and is refused at prepare, which is the right division of labour: the
engine owns field-set exactness.

## Traps that already cost time on this branch

**A dead branch is not a dead route.** `_route_operation` in `harness/gateway.py`
claims `/api/agent` and `/api/operations/`, and returns True before
`_gateway_method` calls its fallback. An `/api/agent` branch inside `_post`
would never execute. Reading such a branch and reasoning from it is how the
effort dial sat unreachable for a release. The branch is gone and a comment
stands where it was, so nobody adds it back. The route itself is live because
the operation route serves it. `tests/test_ui_coverage_gate.py` holds this
distinction; do not collapse it.

**A prepare allowlist that restates the engine drifts silently.**
`gateway_grant_post` carried its own thirteen-action set. Every action route
added on this branch, plus `capability.probe` and `bench.run`, answered 404 at
`/api/gateway-grants/prepare/<action>`: the surface built, the sheet opened, and
the grant could never be obtained. The allowlist is now `GRANTABLE_ACTIONS`, and
`tests/test_grantable_actions.py` holds the two together in both directions.

**A call site is not a witness.** `parity.py` reported `live-agent-stream` as
WITNESSED for months because `_check_witness` tested `ref in gateway_src`, and
the call `self._sse_agent(...)` matched while no such method existed. The check
now requires a `def` for an identifier and a dispatch comparison for a path.

**Coverage is easy to measure wrong.** Three attempts on this branch produced
30.1%, 100%, and 77.3% before the AST gate settled it. The failure modes were a
quote-anchored regex missing the client's `'$baseUrl/api/...'` form, a bare
`/api` reference prefix-matching every route, and regex fragments from a
dispatcher counted as routes. Use the gate, not a fresh grep.

**A prefix dispatch hides a whole family from the coverage gate.** The first
version of the infra dispatch read `if p.startswith("/api/infra/")`. The gate
extracts route literals from `_Handler`, so it saw one entry, `/api/infra`, and
its prefix match then counted a single client reference anywhere beneath that
path as covering all six routes. Six routes, one witness, gate green. Both
dispatch blocks name each route in full instead, and a comment above them says
why so the shorter form does not come back.

**File size gates bind, and they bind tests too.**
`harness/gateway_operation_process.py` sits at exactly 300 lines with no
grandfather entry, so it cannot grow by even one line. `harness/gateway.py` is
grandfathered and may not exceed its frozen count. Appending two tests to
`tests/test_gateway_operation_grants.py` pushed it to 338 and broke the gate
three ways; the new tests live in their own file instead. Put new engine code
in a new module and keep the touch in the large file minimal. Dart files are
held under 300 lines by the same convention.

**Two files may not declare the same widget.** `project_panels.dart` already
declared `StorePanel`, and a second declaration analyzed clean because no single
file imported both. The entity panel is `StoreEntityPanel` in
`store_entity_panel.dart` for that reason.

## Conventions that are not negotiable here

- Color is verdict-only. Levels, states, and categories read by weight and
  hairline, never by hue.
- Every gateway-facing model parses defensively. A missing field degrades; it
  never crashes and never invents a default that reads as real data.
- Honest nulls stay visible. An empty registry reads as empty, an offline lane
  states the lane's own reason, and a view that cannot show DRIFT is not
  shipped.
- Credential presence only, never values. The app does not collect keys.
- The engine decides; the client renders. Do not recompute a verdict, rank a
  tier, or compose a second summary over something the engine already
  summarized.

## Definition of done

1. `python scripts/check_ui_coverage.py` passes at baseline 0. Met.
2. `python -m pytest tests/ -q` green. Met.
3. `flutter analyze` clean and `flutter test` green in `desktop/`. Met.
4. The four other repo gates pass, plus `python -m harness.cli_entry gate`.
5. Every mutating surface goes through the grant flow. A button that mutates
   without a grant is a defect, not a shortcut. Met.

## Defects closed on this branch

- The load-dependent Lean flake. `check_lean_source` separates a check that ran
  out of budget from a check that came back, so a valid proof is never read as
  DRIFT and an invalid one is never read as MATCH, whatever the machine load.
  The two tests state that invariant directly rather than asserting a verdict a
  slow worker can change.
- The dead `/api/agent` branch in `_post` is removed, with a comment in its
  place recording why nothing belongs there.
- The effort dial reaches the companion surface as well as the agent surface,
  and `companion_receipt_strip.dart` shows whether the dial the operator set was
  the dial that got applied.
- The prepare allowlist defect described above.

## Honest nulls kept

- The chat surface sends no effort dial, and that is not an omission.
  `chat.complete` is one generation with `max_tokens`, `temperature`, and
  `seed`; there is no candidate budget for a dial to nominate. A control that
  changes nothing is worse than no control.
- `harness/tool_call_receipt.py` is 347 lines, which is what
  `project-docs/records/2026-07-25-file-gate-burndown.md` records. An earlier
  copy of this document claimed the burndown had drifted. It had not. The claim
  was inverted, and it is deleted rather than carried forward.

## Before tagging

`v0.3.11` triggers PyPI publication and the Windows installer build on a `v*`
tag. The installer has never been built at this version and the desktop app
gained two destinations. Build and smoke-test the installer, and the Android
build, before the tag exists rather than after.
