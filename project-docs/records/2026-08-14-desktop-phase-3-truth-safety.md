# Desktop Phase 3 truth safety acceptance

Date: 2026-08-23

Verdict: PASS for the bounded Phase 3 implementation described here. This is
a code acceptance record, not a release or deployment approval. The honest
product status remains non-executing beta: phases 4 through 6 are open and
no public release is permitted before all six phases pass.

## Boundary and provenance

Phase 3 work on this branch started from the 0.3.10 release boundary
`fcf972f431f9091960ad1cfd377b6fa89005cf06`, tree
`5c2ed10b5497daa400e2e1eb55eee2727cb4e738`, branch `release/0.3.10`. The
implementation branch is `feat/p3-t6-receipt-proof`.

Tasks P3-T1, P3-T2, P3-T4, and P3-T5 landed before this branch in the
commits recorded in git history; P3-T6 and P3-T7 landed on this branch.

| Task | Commit(s) | Subject |
|---|---|---|
| P3-T1 | `4bb9850` | `fix: preserve chat drafts and receipt truth` |
| P3-T2 | `eff84df` | `fix: guard dirty code buffers` |
| P3-T3 | `f7c8e57` + `gateway_operations.py` custody path | exact grants (see scope note) |
| P3-T4 | `7e2cd14` (+ serialization/custody fixes) | `fix: make stop a terminal server action` |
| P3-T5 | `7941bfe`, `899109f`, `479ec38`, `379f2df` | `fix: bind runs to forged plan evidence` |
| P3-T6 | `c119091` | `fix: verify receipt inclusion in desktop` |
| P3-T7 | this record's sibling code commit | `test: close desktop truth and safety P0s` |

Scope note on P3-T3: the planned `harness/gateway_grants.py` module was not
created. The exact-grant requirement was satisfied through the Phase 1
grant store (`f7c8e57` binds journey mutations to exact grants) and the
P3-T4 operation supervisor, which binds start/cancel to owner, journey,
head, request id, and grant before dispatch. Chat/provider, plugin, and
workflow routes outside the operation path are NOT yet grant-gated; that
residual is listed under deferred scope.

## P0 matrix: failing-before and passing-after

| P0 | Failing-before evidence | Passing-after evidence |
|---|---|---|
| Chat preserves no-model prompt; receipt presence never reads verified | Plan §6 P0 line; RED `flutter test test/chat_truth_test.dart test/chat_draft_test.dart` exit 1 before `4bb9850` | Same command exit 0 at `4bb9850`; still green in the final cumulative run |
| Dirty buffers survive close/navigation/crash with Save/Discard/Cancel | RED `flutter test test/code_draft_store_test.dart test/code_close_guard_test.dart` exit 1 before `eff84df` | Same command exit 0 at `eff84df`; still green in the final cumulative run |
| Agent write/exec default false; Stop is terminal, not Detach | RED `pytest tests/test_gateway_operations.py` import-fail; RED `flutter test test/operation_stop_test.dart test/agent_permission_defaults_test.dart` before `7e2cd14` | Both exit 0 at `7e2cd14`; still green in the final cumulative runs |
| Plan Run binds the complete forged contract and rejects drift | RED `pytest tests/test_plan_run_contract.py` import-fail before `7941bfe` | Command exit 0 at `7941bfe` plus hardening commits; still green |
| Receipt-proof schemas agree; Dart recomputes inclusion before MATCH | RED `pytest tests/test_receipt_proof_route.py` ModuleNotFoundError; RED `flutter test test/receipt_proof_test.dart test/receipts_view_truth_test.dart` exit 1 (loading failure + false verified label) before `c119091` | Both exit 0 at `c119091` (12/12 + 3/3); still green in the final cumulative runs |
| Connection distinguishes degraded/offline/auth/startup/version | RED `flutter test test/connection_state_test.dart` exit 1 (loading failure; scaler composed 1.2 not 2.4) before the T7 code commit | Exit 0, 9/9, including the 2.4x composition assertion |
| Mouse-only controls gain semantics and keyboard paths; scaling composes | Pointer-only GestureDetectors at side_rail.dart `_iconBtn`/`_RailItem`, chat_sidebar delete, tab_bar tabs/close, file_tree rows/refresh, lint sheet filters, open panel recents, split divider drag-only, graph canvas tap-only (source lines recorded in the plan) | `flutter test test/critical_accessibility_test.dart` exit 0, 6/6: Enter activation on a rail item, arrow/Home/End on the resizer, arrow nudge on the divider, arrow cycling plus Escape on the graph canvas, semantic labels present, scaler composition |

## Command evidence

Final cumulative desktop command (exit 0):

```text
flutter test --no-pub
```

498 passed, 4 skipped, 0 failed. `flutter analyze --no-pub` exit 0, no
issues.

Final Python commands (exit 0):

```text
python -m pytest tests/test_receipt_proof_route.py tests/test_gateway.py -q
python -m pytest tests/test_desktop_status.py tests/test_gateway.py -q
python -m pytest tests/test_endpoints.py tests/test_agent_tools.py -q
python scripts/check_file_gate.py
python scripts/check_verifier_stdlib.py
python scripts/check_claim_language.py
python scripts/check_public_instructions.py
```

Full-suite run: `python -m pytest tests/ -q` fails exactly two tests,
`tests/test_context_envelope.py` (schema and fingerprint). Both fail
identically at the release base `fcf972f` (verified in a clean worktree),
so they are pre-existing and out of Phase 3 scope; no other failure.

## SHA-256 inventory at this record's code boundary

| Artifact | SHA-256 |
|---|---|
| `desktop/lib/models/receipt_proof.dart` | `bd702f021b700f6c4f1cf3de1e27e83c47ca7730cccaada9a615d90bce550ac9` |
| `desktop/lib/widgets/receipt_proof_panel.dart` | `9929f127e2c7be0e3a596f0f6245772405fd0826dc2422b3a0ac47b7a3207852` |
| `desktop/lib/views/receipts_view.dart` | `35496c87662779462357c58c066e88f6f94bd6fe14c647bcb4e2ab12ddc4957f` |
| `harness/receipt_proof.py` | `a481874a8c13c8e574b68accd20c5b6347867e41059575ceba475c5e95c5009e` |
| `harness/desktop_status.py` | `3179eccd2c350a76b77c32439a960b95c693c47299c1e41f795907356ffe7217` |
| `desktop/lib/models/connection_state.dart` | `7d80507c936606de949f9bc2453a2b43c67a84042312a5fa77216368436d8ecf` |
| `desktop/lib/services/gateway_status.dart` | `75efbcd4f3b6ebd2a431e2d30f46e3daef9051fd1c390c2a3428607da871537c` |
| `desktop/lib/widgets/system_text_scaler.dart` | `05ceaef81ecb81afea5b197a45454e71bfef89f8c5c9d0cb5745dc2296dfe7d8` |
| `desktop/lib/accessibility/accessible_action.dart` | `f3fdff7c73eeefd4df70ed8e8fabf8b3a309db38933848c0f05be34e5fe11e94` |
| `desktop/lib/widgets/rail_item.dart` | `4c7be15af7f3478c2da3a8f6453e38490de6f57af044bb4b6eccb7dd343cf27c` |
| `desktop/lib/widgets/rail_resizer.dart` | `878b33c5f1c199c06b0cd70d181e8d06cc3b715ff4b6a2ab1040400344e7d2a8` |
| `desktop/lib/widgets/fw_verdict.dart` | `0717a9957f45b73ec51dff50fb2d522c33d0ffec369d0ce1755f0143f8830c0f` |
| `desktop/lib/widgets/fw_layout.dart` | `ed916bbd8b50ec67306254ca13c4e43feff37d650e6f3528052f6f848b60a014` |
| `desktop/lib/app.dart` | `eba1c694f958ab7cc063b97cd24ba24267437d8130ca6cd3eef88a0acd1eeae4` |
| `desktop/lib/shell/flywheel_shell.dart` | `cc99afe87d8153ac0cb31dc9c0fa476d3d4e19625f7dc042327ba36ffcc0b72a` |
| `desktop/lib/widgets/side_rail.dart` | `21d1cf3e8bcc77e5c8432fbddbf16058f7d8d855c50c00df6dababb25fa8dd2e` |
| `desktop/test/connection_state_test.dart` | `9f23a32b0ef1307bdfdb7a70e421e7d27cfef1c74b8c7fc7106e1d47c70d2afe` |
| `desktop/test/critical_accessibility_test.dart` | `be746f92c1dd989b25820c4279cddac5ae9455c00a5479a05361e382cd1204cb` |
| `tests/test_receipt_proof_route.py` | `2d8bfb7510fbde290fc58577a8063adca1319f352163527fc75c50eb97384f6b` |
| `tests/test_desktop_status.py` | `7591a9c7cc47328676f1ab92c662764302d9d3819c475c6d6af769315550c8b0` |
| `desktop/test/receipt_proof_test.dart` | `35a31e1e62144d8f52fe9ebb21b262b7841e65cd616c10b23434132a87f24a47` |
| `desktop/test/receipts_view_truth_test.dart` | `b850a18ed5d7b7c9fe9637b1b00e54ed033f262a7714273113c40ba38236f746` |

## Ceilings

All new production files are at or below 300 physical lines. The touched
grandfathered files shrank: `receipts_view.dart` 308 to 254, `fw.dart` 315
to 262, `side_rail.dart` 369 to 259, `tokens.dart` 190 to 173,
`gateway.py` 2253 to 2240. `endpoints.py` was split rather than grown
(`endpoints_http.py`, `endpoint_opencode.py` extracted). The file gate
reports 69 grandfathered files across three trees, zero new, zero grown.

## Completed and deferred scope

Completed: the receipts-proof/v2 contract with pure-Dart inclusion
recomputation; typed connection phases with a read-only status route and
composed text scaling; semantic keyboard-activatable actions across rail,
tabs, file tree, chat sidebar, split divider, graph canvas, lint filters,
and open panel; the P0 matrix above closed with regression evidence.

Deferred, out of Phase 3 scope: grant-gating of chat/provider, plugin, and
workflow routes outside the operation path (the residual P3-T3 slice);
stable route IDs, search, and the Recovery Center (Phase 4); Incident
Compiler, Frontier Claims, Domain Packs (Phase 5); signing, SBOM, and
installed-Windows acceptance (Phase 6). System-level assistive validation
(screen reader, high contrast, 200 percent live) was exercised only
through widget-level semantics and keyboard tests.

Adjacent work landed on this branch outside the Phase 3 plan: the
`ox-alpha` provider slot routed through OpenRouter with a null-content
refusal (`5850c9e`) and native tool calling plus the verification tool
registry (`f2a63bd`). Both carry their own tests; neither gates Phase 3.

## Rollback

```text
git log -1 --format=%H --fixed-strings --grep="docs: record phase 3 final acceptance"
git revert <record-only commit printed above>
git revert --no-edit <T7 code commit> c119091
```

Rollback must not delete journey events, device-local drafts, or user
data.

## Does not prove

This acceptance does not prove live gateway durability, installed Windows
behavior, containment, signing, or release readiness. It does not prove
system screen-reader behavior, high contrast, or 200 percent scaling on
real hardware. The two pre-existing `test_context_envelope.py` failures
are recorded, not fixed. No publication, deployment, or release action
occurred. Receiving-owner acceptance: operator-approved session direction
("complete the 9 todos", "continue"); formal receiving-owner sign-off
remains open per the plan's evidence envelope.
