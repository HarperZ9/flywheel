# Desktop Phase 5 contextual extensions acceptance

Date: 2026-08-23

Verdict: PASS for the bounded Phase 5 implementation described here. This
is a code acceptance record, not a release or deployment approval.
Phase 6 remains open; no public release is permitted before all six
phases pass.

## Tasks and commits

| Task | Commit(s) | Subject |
|---|---|---|
| P5-T1 | `c83f409` + `84f9297` | `feat: define contextual evidence capabilities` |
| P5-T2 | `23c6b9a` (+ `9721eb9`, `8e955c1`) | `feat: compile incident proposals` |
| P5-T3 | `40fd7d1` | `feat: project independent frontier axes` |
| P5-T4 | `24c83b0` | `feat: admit versioned domain packs` |
| P5-T5 | `5893d0e` | `feat: add capability-gated journey extensions` |
| P5-T6 | `63c0028` + `de85874` + this record | `test: accept contextual journey extensions` |

## Accepted contracts

The fail-closed capability sheet (`flywheel.evidence-capabilities/v1`)
derives rows only from accepted contracts with accepted receipts, binds
each row's contract and receipt hashes, and holds executable operations
at `execution_locked` until process containment is accepted. The
operation vocabulary is allowlisted per contract schema. `authorize_`
`capability` is a pure read that never consumes a grant and never grants
by absence.

Incident compilation is deterministic over admitted facts only: source
facts must exist in the projection, the head must still match, edges
stay acyclic over known nodes, secret-shaped keys and host paths are
refused at the case boundary, and no proposal can self-accept. Frontier
claims project four independently hashed axes (identification,
verification, policy, value) with every legacy value and null
round-tripping verbatim, `NOT_FOUND_IN_CORPUS` never translated into
novel, unrecognized raw values preserved and named, and no composite
field anywhere. Domain packs admit as manifests with SPDX licenses,
numeric resource limits, deterministic oracle bindings, and typed
fixture expectations; QA reports denominator, detections, escapes, and
platform skips, and a planted false accept that escapes fails QA.
Executable packs require accepted containment.

The gateway serves the extension routes fail-closed: the server-side
contract registry is empty, so the sheet has zero rows and every
extension denies until contracts are accepted. The Dart decoders drop
malformed rows to hidden; the widgets render only advertised states,
state execution locks in plain text, and expose no accept or execute
control.

## Command evidence

```text
python -m pytest tests/test_evidence_extension_contracts.py -q      # 15/15
python -m pytest tests/test_incident_case.py tests/test_incident_proposal.py -q  # 16/16
python -m pytest tests/test_frontier_claim.py -q                    # 11/11
python -m pytest tests/test_domain_pack.py -q                       # 15/15
python -m pytest tests/test_evidence_extension_route.py -q          # 8/8
python -m pytest tests/test_contextual_extensions_acceptance.py -q  # 7/7
python -m pytest tests/ -q --tb=no                                  # 0 failures
python scripts/check_file_gate.py                                   # clean
flutter test --no-pub                                               # 568 passed, 4 skipped
flutter analyze --no-pub                                            # no issues
```

## SHA-256 inventory at this record's code boundary

| Artifact | SHA-256 |
|---|---|
| `harness/evidence_extension_contracts.py` | `406f7cb9c9a434e88fbdbc06749b84502122cf8821ce0d7e586e307fe8db6d56` |
| `harness/incident_case.py` | `50ab6aa13f89f4ad096e6ade242be23a8fad7ecf34e6136e10719b4c02c80e62` |
| `harness/incident_proposal.py` | `47aff0888b44963613f8cbe689b88827ce7372aa05e22354abed14e9fc65d16b` |
| `harness/frontier_claim.py` | `26e7142c22ff3ed1c12a115a4dc223d4ce3764cf79092baf97cbadaba0793cba` |
| `harness/frontier_claim_projection.py` | `ad798012cfd341b5a58efcb546885af19b51ef8f5502e7311c359852878bf263` |
| `harness/domain_pack.py` | `7bfba7ec0fbe497ad3c3111ffd96695e7d7d0ac0097c1caae55114b6792fd348` |
| `harness/evidence_extension_route.py` | `169044bfc649f56e3e5ea880627f22907e084709763631869b3c1302b4424570` |
| `desktop/lib/models/evidence_extensions.dart` | `4b7701f7032cab46c3213cdc7b9e33af6f5c5dc5579795a7aaaae80ffd2c0ddc` |
| `desktop/lib/client/evidence_extensions_client.dart` | `6eb547e431ffd75daf1f9fdd364921226fd8af6a882ff6a44109d0af69c212b1` |
| `desktop/lib/widgets/evidence_extensions.dart` | `a4901a5672c247f6132291eb81339f8efcdcf30405a59db7a0e73abf0d8653e1` |

## Limitations and does-not-prove

The server-side contract registry is empty by design: no Incident,
Frontier, or pack contract has been accepted yet, so the served sheet
has zero rows and the routes deny. The frontier axis event validates its
binding and delegates to a CAS command; the CAS dispatch itself is the
Phase 1 store's, exercised there. Domain pack QA runs the pack's own
fixtures; it does not certify the pack's claims. No live service,
provider, or network was used. Screen-reader behavior is covered at the
semantics level only. Phases 1-4 records stand; Phase 6 remains open and
is not a prerequisite claimed here.

## Rollback

```text
git log -1 --format=%H --fixed-strings --grep="docs: record phase 5 final acceptance"
git revert <record-only commit printed above>
git revert --no-edit de85874 63c0028 5893d0e 24c83b0 40fd7d1 8e955c1 9721eb9 23c6b9a 84f9297 c83f409
```

Rollback must not delete journey events, device-local drafts, or user
data.
