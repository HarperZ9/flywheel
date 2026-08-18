# Desktop Phase 2 Journey Flutter acceptance

Date: 2026-08-15

Verdict: PASS for the bounded Phase 2 implementation described here. This is a
code acceptance record, not a release or deployment approval.

## Boundary and provenance

Phase 2 started after the Phase 1 record-only commit
`473d4cdc1d732a38985d4136ddc0ef85d4031a5b`, tree
`cecd57095e1798241b1f97807d047b5291ef3b6e`. The final independently reviewed
code boundary is `a9873bdcf6c5f3bbecbf4d8c92bb582124558684`, tree
`7d7e113d33497ef6b2df3b63cd30560c56e49dd5`.

Phase 2 used one or more code commits for each task, followed by this separate
record-only commit. This file is the sole payload of the record-only commit. It
does not claim its own commit or tree because that would be self-referential.
The exact subject `docs: record phase 2 final acceptance` binds that later
provenance in Git history.

| Task | Commit | Tree | Subject |
|---|---|---|---|
| P2-T1 | `4773349e1afd23ef683776a554cccae58961819d` | `98bfdcb0180220d57123564989419a07b3196f37` | `feat: model durable journey projections` |
| P2-T1 fix | `551f05605b578f777009a2f4b6425afc232db516` | `5c956c7af615de6e275a62a88096db0347dcefad` | `fix: harden journey model contracts`. |
| P2-T2 | `aa241e34e80afc2ad3d05ae2be5f2e7a71642082` | `bce3c4ae4c46e6825796e9cabe74f1ebf587f9c7` | `feat: add typed journey client` |
| P2-T2 fix | `5a3e50a5ac1a9ad9b679a9f4540f75b80723ec43` | `16316797c2b3485cb29bc8cb1b69097af5a3e0d6` | `fix: preserve typed journey transport errors`. |
| P2-T3 | `080001ac7a8badf29a312081c2b67360f1673028` | `427bfd16083a15ff956474198049ccab6b9fef4b` | `feat: preserve journey drafts locally` |
| P2-T3 fix 1 | `1887659aeaba884de232efc272226d1bc40cefb4` | `38df0afba355c22bc2530258bc705d7eb005b8dd` | `fix: harden journey local custody` |
| P2-T3 fix 2 | `7dc14c7f66ff632edf5562deafb46ab050cbae4d` | `9109698958268ce5b1d2ba089b8926214641a872` | `fix: close journey store persistence bounds`. |
| P2-T4 | `5550ef40b0e10151426710d19196d57cca4aaa67` | `baee6f8ebd70f8f6063f6cdb97156b156498ad6d` | `feat: coordinate journey resume and append` |
| P2-T4 fix 1 | `dd04a5580b72551f5a565768ce661439bd505bca` | `1529e4b633d113cd43e41bfa5f1ff09f3bfa8bde` | `fix: isolate journey controller state` |
| P2-T4 fix 2 | `9bf08dc6c35df153022446fd700c2a5c59d41651` | `7afdf226b2518b83579aef9b71581e49a174820d` | `fix: preserve journey lens refresh`. |
| P2-T4 fix 3 | `c87f59a60a3348297e0a642770de59dc7ddf2fff` | `43207ea607c4ce5efac35b80f2f069aa4ddcbbc3` | `fix: preserve pending journey selection` |
| P2-T4 fix 4 | `cd0acd39a0ca2a92ada35406dd32607aa2a469f9` | `f5f90a0555d767ecd5ee7ee6abeef93cc886ca58` | `fix: close journey selection state machine` |
| P2-T4 fix 5 | `58c2c1faa6f08a0a3e0923f335a2322850b6fbb9` | `c6ede1f882de5cbe115e2b3de5f93d29dde6fd54` | `fix: guard journey refresh generations`. |
| P2-T5 | `0cd059fd988b95c04680baacf6aa29f89bfd843a` | `4739f2f539037520e26e6ddf90d6351a8fcd4d05` | `feat: render three journey lenses` |
| P2-T5 fix | `defb2b686222431fd6c120d47cfb1b231f373843` | `0d6cdd1a9d631b79e3f38364c176bda7c4a1cf26` | `fix: preserve journey lens accessibility`. |
| P2-T6 | `3e70d0ea2fd26a5423a21f957699dbe8cca5c372` | `f59f92e2d953661a9fb5aec453c76cd639a90ba7` | `feat: make journey the desktop home` |
| P2-T6 fix | `a9873bdcf6c5f3bbecbf4d8c92bb582124558684` | `7d7e113d33497ef6b2df3b63cd30560c56e49dd5` | `fix: close desktop shell lifecycle`. |

The receiving gate admitted every final task boundary before dependent work
began. Independent review recorded terminal `SPEC PASS` and
`QUALITY APPROVED` for the final P2-T4, P2-T5, and P2-T6 boundaries. Earlier
task acceptance is also bound by the next task's exact accepted starting
boundary. The receiving owner authorized this record only after terminal P2-T6
acceptance.

| Final task boundary | Review and receiving-gate status. |
|---|---|
| P2-T1 `551f05605b578f777009a2f4b6425afc232db516` | Accepted. P2-T2 started from this exact boundary. |
| P2-T2 `5a3e50a5ac1a9ad9b679a9f4540f75b80723ec43` | Accepted. P2-T3 started from this exact boundary. |
| P2-T3 `7dc14c7f66ff632edf5562deafb46ab050cbae4d` | Accepted. P2-T4 started from this exact boundary. |
| P2-T4 `58c2c1faa6f08a0a3e0923f335a2322850b6fbb9` | Terminal `SPEC PASS` and `QUALITY APPROVED`. |
| P2-T5 `defb2b686222431fd6c120d47cfb1b231f373843` | Terminal `SPEC PASS` and `QUALITY APPROVED`. |
| P2-T6 `a9873bdcf6c5f3bbecbf4d8c92bb582124558684` | Terminal `SPEC PASS` and `QUALITY APPROVED`. Record creation authorized. |

## Accepted contracts

The client consumes the exact public schema values
`flywheel.evidence-journey-projection/v2`,
`flywheel.evidence-journey-list/v2`,
`flywheel.evidence-journey-mutation-ack/v2`,
`flywheel.evidence-journey-export/v2`,
`flywheel.grant-proposal/v1`,
`flywheel.operation-grant-approval/v1`, and
`flywheel.evidence-transport-error/v1`. Device-only custody uses the closed
`flywheel.desktop-journey-drafts/v1` and
`flywheel.desktop-journey-session/v1` envelopes. Journey export requires the
`flywheel.evidence-journey-custody/v2` profile.

`JourneyApi` exposes typed prepare, one-time approval, create, list, resume,
append, check, cancel, and export calls over a supplied authenticated
`GatewayClient`. Cancel returns `JourneyCancelResult`, not a synthetic mutation
acknowledgement. `JourneyController` owns startup, draft custody, serialized
grant and mutation flow, acknowledgement generations, typed recovery, and
projection refresh. `JourneyView` is render-only. `FlywheelShell` constructs
one dependency graph and makes Journey the first of 30 reachable destinations.
No client model, controller, view, or shell promotes local data into server
truth or recomputes evidence truth.

## TDD and command evidence

Commands are shown with `flutter` on `PATH` to keep this public record
machine-neutral. The arguments, working directory (`desktop/`), exits, and
denominators match the recorded runs.

| Task | Initial tests-only RED command | Exit and reason | Final focused or affected GREEN |
|---|---|---|---|
| P2-T1 | `flutter test test/journey_models_test.dart test/journey_lens_consistency_test.dart --no-pub` | 1, missing model imports | 0, 15/15. |
| P2-T2 | `flutter test test/journey_api_test.dart test/journey_api_error_test.dart --no-pub` | 1, missing API import | 0, 15/15 focused. Final affected gate: 75/75. |
| P2-T3 | `flutter test test/journey_draft_store_test.dart test/journey_session_store_test.dart --no-pub` | 1, missing store imports | 0, 21/21. |
| P2-T4 | `flutter test test/journey_controller_test.dart test/journey_restart_test.dart --no-pub` | 1, missing controller import | 0, 47/47 across the three controller tests. |
| P2-T5 | `flutter test test/journey_view_test.dart test/journey_accessibility_smoke_test.dart --no-pub` | 1, missing view and widget imports | 0, 14/14. |
| P2-T6 | `flutter test --no-pub test/journey_shell_test.dart test/widget_test.dart` | 1, zero tests loaded because shell imports were missing | 0, 7/7. |

Every review repair added a failing regression before production changes. The
recorded repair REDs exited 1 for unsafe parsing, mutability, transport,
store admission, controller races, accessibility, and shell disposal.
The final repair RED retained five prior shell passes. Two new cases failed.
Delayed gateway ownership observed zero cleanup. Delayed lane installation
attempted state work after disposal.

The final cumulative command was:

```text
flutter test --no-pub test/journey_models_test.dart test/journey_lens_consistency_test.dart test/journey_api_test.dart test/journey_api_error_test.dart test/journey_draft_store_test.dart test/journey_session_store_test.dart test/journey_controller_test.dart test/journey_controller_isolation_test.dart test/journey_restart_test.dart test/gateway_auth_test.dart test/journey_view_test.dart test/journey_accessibility_smoke_test.dart test/journey_shell_test.dart test/widget_test.dart
```

It exited 0 with 125/125. `flutter test --no-pub` exited 0 with 298/298
across the full desktop suite. `flutter analyze --no-pub` exited 0 with no
issues. Formatting checked the six final P2-T6 files with zero changes. The
repository file gate reported 69 grandfathered files across three trees, zero
new violations, and zero grown violations.

## Behavioral evidence

| Boundary | Accepted test evidence. |
|---|---|
| Restart | A new app instance resumed the stored opaque Journey ref and lens with the exact head and facts. Drafts survived restart. |
| Lens equality | Rescue, Diagnose, and Verify retained equal server evidence and event head. Wrong-ref or changed-core projections were rejected. |
| Conflict | Typed `HEAD_CONFLICT` retained and rebased the same request ID only after refresh. Ambiguous attempts reused their persisted attempted head. |
| Acknowledgement | Draft deletion required a valid acknowledgement plus a re-read matching request ID and payload digest. Post-ack refresh remained required. |
| Failure | Auth, version, store, invalid-response, and local custody failures retained accepted evidence and exposed fixed recovery actions. Offline shell status did not replace evidence. |
| Selection races | Acknowledgement generations kept the newest Journey and lens visible. Required post-ack refresh still ran. |
| Journey UI | Shared evidence stayed outside the three lens presentations. Keyboard and semantics activation, honest nulls, full-head semantics, reduced motion, and narrow layout were covered. |
| Destinations | Journey plus all 29 prior labels were reachable through their original view mappings. Unknown labels rendered only the existing empty state. |
| Lifecycle | Initialization occurred once. Settled disposal released controller, client, and owned process once. Delayed process acquisition cleaned up after unmount, and delayed lane installation performed no disposed-state work. |

## Ceilings

| Task | Maximum task file lines | Maximum production function | Maximum named test or helper. |
|---|---:|---:|---:|
| P2-T1 | 300 | 33 | 67. |
| P2-T2 | 300 | 26 | 79. |
| P2-T3 | 300 | 41 | 53. |
| P2-T4 | 300 | 40 | 62. |
| P2-T5 | 299 | 54 | 66. |
| P2-T6 | 285 | 31 | 59. |

The pre-existing `gateway_client.dart` was grandfathered and shrank from 680
to 677 lines. No task file grew beyond its assigned ceiling. Production
functions remained at or below 60 lines and named tests/helpers at or below 80.

## SHA-256 inventory at the reviewed code boundary

| Artifact | SHA-256. |
|---|---|
| `desktop/lib/models/evidence_state.dart` | `274f3fe262520a9d060a3e0bdf286af936f610130a5dbbe16e49e848098901a5` |
| `desktop/lib/models/journey_models.dart` | `47b23e098601d7a1725a96ccbe0f1160a74eda0cc8d386cfaabed9b11b796d7d` |
| `desktop/test/journey_models_test.dart` | `bba2bfb8268b9eb9b45d43e5132363b33a2a4a1640b2bb23f731e2909f524e50` |
| `desktop/test/journey_lens_consistency_test.dart` | `1c4fb86a3eddad4c147e5656302189c5d344dc469c8d3f81423af89462bf83f2` |
| `desktop/lib/client/gateway_error.dart` | `0f4a115e754b0a6bc166e081040dd9a838e459eb3f15f78eb799040433f8fd5f` |
| `desktop/lib/client/gateway_client.dart` | `949d9f5ab80e500d73eb8571eefac6c308cec0f487b517b9864c4a315f993b67` |
| `desktop/lib/client/journey_api.dart` | `04589a7a2546fa519b402ab49e2154b8cab00cb761dec201ea208bd8226bd649` |
| `desktop/test/journey_api_test.dart` | `5d8e60e09cda577c131594e30223f65747c05eff001f6b9fd0b56b920ce15d06` |
| `desktop/test/journey_api_error_test.dart` | `f595163d7b7258385cee73e8fb0085d0682b535a1e41ea4a83cfe63f87b0011f` |
| `desktop/lib/services/journey_draft_store.dart` | `b87a760f39416ef748661dda983938c4222d3819c40bba25a6a0118a645c74e8` |
| `desktop/lib/services/journey_session_store.dart` | `b99271b4acf4e70666367d8801c2a2f6c85cd807fc3bd7aeddb504156262f231` |
| `desktop/test/journey_draft_store_test.dart` | `ad06affa9a295d1359bc97fb4599fe8254d9123f605b86becfa76c0036553d54` |
| `desktop/test/journey_session_store_test.dart` | `161925552db96a16bf7a9901031cabbdaf4d2ac327fbeed203ce2cec39cb8375` |
| `desktop/lib/controllers/journey_controller.dart` | `15bd9986dc68946bb1a291d6907c11a52998f6bb58eb54f7a04dccf7e0f268be` |
| `desktop/lib/controllers/journey_controller_support.dart` | `e63c9c52242f99f8700f56b2810f22c902766d0f3831df528402b1624221657f` |
| `desktop/test/journey_controller_test.dart` | `12956dd96e0ad6f495de5f6ac8823f0bd969ab223840b94fb3893b51a5ea2893` |
| `desktop/test/journey_restart_test.dart` | `e8f98bd2343a3bbb9815e5167941c62ba1a9545ccfe53dfa2ce53236218bf8ae` |
| `desktop/test/journey_controller_isolation_test.dart` | `3ddc49f9f2dae96da03871472557deafbb7f5daaaf8a7a25c1af72ce411a5a43` |
| `desktop/lib/views/journey_view.dart` | `82c44382fbe913feab1c032f005d71c4bea71873744ffc535762a9a3fc263637` |
| `desktop/lib/widgets/journey_lenses.dart` | `90d400d8f5389771058c116b195556eeb86c7b8d0f1cbc3c7b35edb87375a756` |
| `desktop/lib/widgets/journey_cards.dart` | `5f8ab11434b18d30707f7d451a83a7de3d1df04f28605077ec123a1ab3d650cd` |
| `desktop/test/journey_view_test.dart` | `2f96160957d6d28335cfc4eb571da286a40f7546125007523a6cf404252e1d52` |
| `desktop/test/journey_accessibility_smoke_test.dart` | `25ab37ce0879f6abbcd82efd95b24146bb25c9ab1ba8fac645ba6392fbccd8f1` |
| `desktop/lib/main.dart` | `ceed73c1d68b0d559aa34f5f8bfc07d97f624c46790c90e34212b27fd040cf9f` |
| `desktop/lib/app.dart` | `621dd45fef0f970d258619b90d770cfb97615196063e0a73740bd5f9cf319ce6` |
| `desktop/lib/shell/flywheel_shell.dart` | `b18e89be7cbf9d804831fbc6ed30c1d95a181d89e99c9d60e27c8876d8ba05f2` |
| `desktop/lib/shell/view_factory.dart` | `8e785b51a725af14af4496183c9d7e49b6e36b598df2be808fd9ec3b3c1a12a9` |
| `desktop/test/journey_shell_test.dart` | `d7a889e2e4ec7ed7882e05710fed79579d327b5dcf72477610f1a556f8f15802` |
| `desktop/test/widget_test.dart` | `c68437124c68637100cef2eb6f6797fa29cc335bca045f0eefb9e0fa033a3945` |
| Phase 2 governing specification | `575e0a47f7cf4531db9a6268831d653f4e60aec04c1a8baa4a8f4178e559bb6e`. |
| Phase 2 implementation plan | `01d0569d711d4d3a3dbcc3c58a0abad74f5da2a768c75b1211a4987867248643`. |
| Phase 1 public acceptance record | `48a4b310f5c856ee4abd4af7fcc8f447ba63a0bf9e9e705405dd4399b1e254f5`. |

## Completed and deferred scope

Completed scope includes defensive Journey v2 parsing and a typed fixed-route
client. It also includes canonical draft/session custody and restart-safe
controller behavior. Three equal-evidence lenses render through one shell-owned
desktop graph with Journey as home. Existing destinations remain available.
Server, route, dependency, theme, token, and lockfile contracts remain unchanged.

Deferred scope includes first-run Journey creation or selection and automatic
relisting after an offline first start. It also includes complete connection
states, stable routes, shell accessibility, and system assistive validation.
Responsive navigation, recovery behavior, extension containment, and installed
Windows validation remain deferred. No publication, deployment, or release
action occurred.

## Record-only gates

The procedure writing gate exited 0 with zero hard violations. Claim-language,
public-instruction, file-ceiling, working-diff, secret, host-path, and private
provenance scans exited 0. The file gate retained its accepted denominator of
69 grandfathered files across three trees, with zero new or grown violations.
No product test was rerun for this record-only commit. The 298/298 result above
belongs to the reviewed code boundary.

## Rollback

First locate the record-only commit by its exact subject. Revert the hash
printed by this lookup.

```text
git log -1 --format=%H --fixed-strings --grep="docs: record phase 2 final acceptance"
git revert <record-only commit printed above>
```

Use the following reverse-order command for the complete Phase 2 code boundary.
Start from a clean tree. Inspect any conflict before continuing.

```text
git revert --no-edit a9873bdcf6c5f3bbecbf4d8c92bb582124558684 3e70d0ea2fd26a5423a21f957699dbe8cca5c372 defb2b686222431fd6c120d47cfb1b231f373843 0cd059fd988b95c04680baacf6aa29f89bfd843a 58c2c1faa6f08a0a3e0923f335a2322850b6fbb9 cd0acd39a0ca2a92ada35406dd32607aa2a469f9 c87f59a60a3348297e0a642770de59dc7ddf2fff 9bf08dc6c35df153022446fd700c2a5c59d41651 dd04a5580b72551f5a565768ce661439bd505bca 5550ef40b0e10151426710d19196d57cca4aaa67 7dc14c7f66ff632edf5562deafb46ab050cbae4d 1887659aeaba884de232efc272226d1bc40cefb4 080001ac7a8badf29a312081c2b67360f1673028 5a3e50a5ac1a9ad9b679a9f4540f75b80723ec43 aa241e34e80afc2ad3d05ae2be5f2e7a71642082 551f05605b578f777009a2f4b6425afc232db516 4773349e1afd23ef683776a554cccae58961819d
```

Rollback must not delete Journey events, device-local drafts or sessions, or
user data.

## Does not prove

This acceptance does not prove live gateway behavior or server durability. It
does not prove first-run chooser behavior or automatic offline relisting.
It does not prove full connection states, system accessibility, stable routes,
containment, or installed Windows behavior. It does not prove claim correctness, evidence
completeness, receipt authenticity, or origin authenticity. It does not prove
publication, deployment, or release readiness. The controlled tests used
fakes, injected files, and local widget fixtures. No live network or service
was part of this Phase 2 acceptance.
