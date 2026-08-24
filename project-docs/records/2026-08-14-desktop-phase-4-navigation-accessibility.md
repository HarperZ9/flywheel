# Desktop Phase 4 navigation accessibility acceptance

Date: 2026-08-23

Verdict: PASS for the bounded Phase 4 implementation described here. This is
a code acceptance record, not a release or deployment approval. Phases 5
and 6 remain open; no public release is permitted before all six pass.

## Tasks and commits

| Task | Commit | Subject |
|---|---|---|
| P4-T1 | `1eaec6f` | `feat: add stable desktop routes` |
| P4-T2 | `764e929` | `feat: group and search desktop navigation` |
| P4-T3 | `b142410` | `fix: make desktop actions keyboard accessible` |
| P4-T4 | `fb20033` | `fix: honor assistive display preferences` |
| P4-T5 | `f5c2f81` | `feat: add typed recovery center` |
| P4-T6 | this record's sibling code commit | `test: accept accessible desktop recovery` |

## Accepted contracts

Thirty stable route ids in five groups (Work, Chat, Code, Evidence,
Advanced), frozen by `desktop/lib/navigation/destination_catalog.dart` and
its catalog test. `AppLocation` carries ids and opaque public refs only;
`parseDeepLink` rejects other schemes, hosts, extra segments, unknown
query keys, non-opaque refs, and journey refs on foreign destinations.
`NavigationController` awaits the unsaved-work guard before every commit
and restores full locations through back/forward.

The shell routes by id through `buildDestinationView(DestinationId, ...)`;
no view routes by display label. `FlywheelNav` is typed. The rail renders
from the catalog with a label filter, Ctrl+K opens the command palette
(filter, activate, Escape), and the view cache keys destination subtrees
by route id so PageStorage-backed scroll state survives switching.

The recovery center aggregates six typed kinds behind injected sources,
offers only advertised actions, keeps items until an explicit successful
action, and opens as an overlay from the rail footer rather than a
thirty-first destination. The failed-update and incomplete-migration
sources return honest empties until their records exist.

Display preferences read MediaQuery in one place: the composed text
scaler (system x user), a high-contrast token variant measured at 4.5:1
for ink on grounds and 3:1 for hairlines with verdict hues unchanged, and
a single motion decision point that zeroes durations when the OS asks.

## Command evidence

Final cumulative desktop command (exit 0):

```text
flutter test --no-pub
```

557 passed, 4 skipped, 0 failed. `flutter analyze --no-pub` exit 0.
`python scripts/check_file_gate.py` clean: 69 grandfathered across three
trees, zero new, zero grown. `python scripts/check_claim_language.py` and
`python scripts/check_public_instructions.py` exit 0.

New files are at or below 300 physical lines; the touched shell was
reduced from 337 to 237 lines by extracting the status coordinator and
the rail. RED evidence per task: P4-T1 compile failure (typed navigation
absent), P4-T2 behavioral failures (label routing, unfiltered search,
lost scroll), P4-T3 pointer-only failures, P4-T4 contrast and duration
failures, P4-T5 missing-model failures. All GREEN at the commits above.

## Limitations and does-not-prove

The focus ring's appearance follows the platform focus-highlight strategy
through FocusableActionDetector's internal state machine, which does not
surface transition callbacks under the widget test binding; ring
visibility was verified manually with keyboard traversal, and the tests
pin the focus semantics the ring depends on. Screen-reader behavior is
covered at the semantics level only; no live assistive display validated
this build. The interrupted-operation source surfaces snapshots only;
cancellation stays with the operation controller. Journey draft discard
requires a store acknowledgement, so the center cannot silently drop
custody. No publication, deployment, or release action occurred. Phases 5
and 6 are not prerequisites claimed here and remain open.

## Rollback

```text
git log -1 --format=%H --fixed-strings --grep="docs: record phase 4 final acceptance"
git revert <record-only commit printed above>
git revert --no-edit <T6 code commit> f5c2f81 fb20033 b142410 764e929 1eaec6f
```

Rollback must not delete journey events, device-local drafts, or user
data.
