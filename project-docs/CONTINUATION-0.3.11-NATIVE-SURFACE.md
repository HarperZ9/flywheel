# Continuation: native surface for the remaining action routes

Hand-off for the 0.3.11 release branch. Everything described here is on
`release/0.3.11` and pushed. The branch is 28 commits ahead of `main`, the
working tree is clean, and every gate is green.

## Where this stands

| Check | Value |
|---|---|
| Route coverage | 112 of 127 reachable routes (88.2%) |
| Routes with no native surface | 15, all POST |
| Python suite | 5,899 passed, 23 skipped, 0 failed |
| Desktop suite | 666 passed, 4 skipped |
| `flutter analyze` | clean |
| Repo gates | file gate, verifier stdlib, claim language, public instructions, UI coverage all PASS |
| Disproof gate | PASS, rewitness MATCH |

Reproduce the work list at any time:

```
python scripts/check_ui_coverage.py --list
```

That gate is frozen at 15 and fails in both directions. A route that loses
its surface fails it, and a route that gains one fails it too until the
baseline is lowered, because a stale baseline is a gate that has stopped
measuring.

## The task

Give a native surface to the 15 POST routes below. Each changes state, so
each needs the operator-grant flow rather than a plain button.

```
/api/bench/run          /api/capability        /api/evidence
/api/frontier           /api/governance/classify  /api/import
/api/invent             /api/lane              /api/lean
/api/packs/admit        /api/retrieve          /api/scaffold
/api/store/entity       /api/store/query       /api/suite
```

Not all of these are equally risky. Several are POST only because they take a
request body, and are semantically reads: `/api/store/query`, `/api/capability`,
`/api/scaffold`, `/api/retrieve`, `/api/frontier`, `/api/governance/classify`.
Classify each one before building it. A read that happens to POST needs a view.
A route that mutates needs a grant.

The genuinely mutating set, on current reading: `/api/import`, `/api/invent`,
`/api/packs/admit`, `/api/store/entity`, `/api/bench/run`, `/api/lean`,
`/api/suite`, `/api/evidence`, `/api/lane`. Verify rather than trust this list.

## The grant flow to follow

Three existing call sites do this correctly. Copy the shape:

- `desktop/lib/ide/agent_panel.dart` around the `_operation` and `_run` pair
- `desktop/lib/views/agent_view.dart`
- `desktop/lib/views/compare_view.dart`

The helper is `authorizeGatewayStream` in
`desktop/lib/widgets/operation_grant_sheet.dart`. The pattern is: build a
`GatewayOperation.exact(action:, clientRequestId:, operation: {...})`, pass it
through `authorizeGatewayStream`, and only start the stream inside the
callback once the operator has granted it.

Server-side, the allowed action names and their field sets live in
`_FIELDS` in `harness/gateway_operation.py`. An action not in that table
cannot be expressed, and a field not in its set is rejected during
canonicalization before any worker starts.

## Open question to resolve first

`bench.run` exists as an operation action in `_FIELDS`, and `/api/bench/run`
is separately dispatched in `_post`. That means there may be two routes to the
same capability with different gating. Establish which one is authoritative
before building a surface for it. Do not surface both.

## Traps that already cost time on this branch

**A dead branch is not a dead route.** `_route_operation` in `harness/gateway.py`
claims `/api/agent` and `/api/operations/`, and returns True before
`_gateway_method` calls its fallback. So the `/api/agent` branch inside `_post`
never executes. Reading that branch and reasoning from it is how the effort
dial sat unreachable for a release, and how an implementation was written
against a path that could not run. The route itself is live because the
operation route serves it. `tests/test_ui_coverage_gate.py` holds this
distinction; do not collapse it.

**A call site is not a witness.** `parity.py` reported `live-agent-stream` as
WITNESSED for months because `_check_witness` tested `ref in gateway_src`, and
the call `self._sse_agent(...)` matched while no such method existed. The check
now requires a `def` for an identifier and a dispatch comparison for a path.

**Coverage is easy to measure wrong.** Three attempts on this branch produced
30.1%, 100%, and 77.3% before the AST gate settled it at 88.2%. The failure
modes were: a quote-anchored regex missing the client's `'$baseUrl/api/...'`
form, a bare `/api` reference prefix-matching every route, and regex fragments
from a dispatcher counted as routes. Use the gate, not a fresh grep.

**File size gates bind.** `harness/gateway_operation_process.py` sits at exactly
300 lines with no grandfather entry, so it cannot grow by even one line.
`harness/gateway.py` is grandfathered and may not exceed its frozen count. Put
new engine code in a new module and keep the touch in the large file minimal.
Dart files are held under 300 lines by the same convention.

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

1. `python scripts/check_ui_coverage.py` passes with the baseline lowered to
   the new gap, ideally 0.
2. `python -m pytest tests/ -q` green.
3. `flutter analyze` clean and `flutter test` green in `desktop/`.
4. The four other repo gates pass, plus `python -m harness.cli_entry gate`.
5. Every new mutating surface goes through `authorizeGatewayStream`. A button
   that mutates without a grant is a defect, not a shortcut.

## Known defects left open

- A load-dependent test flake: `tests/test_infra_lean_adapter.py::test_check_lean_source_valid_proof`
  passes alone and fails under `pytest -n auto`, because a 30-second timeout
  collides with parallel workers. A test whose verdict depends on machine load
  is a defect by this repo's own standard, not something to mark flaky.
- The dead `/api/agent` branch in `_post` should be removed once nothing
  references it, so no one reasons from it again.
- The effort dial reaches the agent surface only. The chat and companion
  surfaces still send no dial.
- `project-docs/records/2026-07-25-file-gate-burndown.md` records
  `harness/tool_call_receipt.py` at 347 lines; it is 289. The burndown drifted.

## Before tagging

`v0.3.11` triggers PyPI publication and the Windows installer build on a `v*`
tag. The installer has never been built at this version and the desktop app
gained two destinations. Build and smoke-test the installer before the tag
exists, not after.
