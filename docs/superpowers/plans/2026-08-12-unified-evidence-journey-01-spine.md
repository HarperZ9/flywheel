# Unified Evidence Journey 01 Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship one deterministic journey from software failure intake to a justified next action and portable offline recheck, with Rescue, Diagnose, and Verify views over one record.

**Architecture:** Append journey events beside the existing receipt ledger, then derive a current projection. Do not change ledger semantics. Reuse the oracle registry, receipt, and bundle implementations. Gateway and desktop code only transport or render server-derived facts.

**Tech Stack:** Python 3.11 standard library, existing Flywheel oracle/receipt/bundle/gateway, Flutter/Dart, pytest, Flutter test.

## Decisions fixed for this release

- The journey is an append-only event log projected over existing receipts; it does not extend receipt-ledger schemas.
- Attestations require `subject`, `role`, `scope`, `basis`, `issued_at`, and `expires_at`. `signature` is optional in v1, but unsigned is explicit and cannot satisfy a signed-attestation requirement.
- Journey becomes the first desktop destination and startup view. Chat remains available as an advanced action surface.
- `verdict`, evidence axes, and receipt state are server-owned. The client never recomputes them.

---

### Task 1: Strict evidence JSON boundary

**Files:**
- Create: `harness/evidence_json.py`
- Create: `tests/test_evidence_json.py`

- [ ] Write failing tests for duplicate keys, `NaN`/`Infinity`, wrong top-level type, depth and byte bounds, absolute/traversal/drive/UNC refs, symlink or junction escape, missing/non-regular artifacts, canonical key order, and stable SHA-256.
- [ ] Run `python -m pytest tests/test_evidence_json.py -q`; expect import failure.
- [ ] Implement this public boundary:

```python
def strict_load_json(raw: bytes | str, *, max_bytes: int = 1_048_576,
                     max_depth: int = 32) -> object: ...
def canonical_bytes(value: object) -> bytes: ...
def canonical_sha256(value: object) -> str: ...
def admit_artifact_ref(root: Path, ref: str, *, must_exist: bool = True) -> Path: ...
```

Use `object_pairs_hook` for duplicates, `parse_constant` to reject non-finite values, strict UTF-8, resolved plus case-normalized containment, and regular-file checks. Serialize neither the admitted root nor host paths.
- [ ] Run the focused test; expect PASS.
- [ ] Commit: `feat: add strict evidence boundary`.

### Task 2: Journey state machine and projections

**Files:**
- Create: `harness/evidence_journey.py`
- Create: `tests/test_evidence_journey.py`

- [ ] Write RED tests for exact `flywheel.evidence-journey/v1`, stages `intake|decomposed|preflight|running|concluded|exported`, invalid transitions, immutable events, atomic claim dependency cycles, four-way verdicts, honest-null reasons, denominator consistency, cited next-action basis, and expired/unsigned attestations.
- [ ] Add lens equality tests: Rescue, Diagnose, and Verify must expose the same `journey_id`, event-head hash, claim ids, verdicts, and receipt refs.
- [ ] Implement:

```python
def new_journey(*, journey_id: str, goal: str, intake: dict,
                created_at: str) -> dict: ...
def append_event(journey: dict, event: dict) -> dict: ...
def project_journey(journey: dict, *, lens: str) -> dict: ...
def verify_journey(journey: dict) -> dict: ...
```

Each event binds `prior_event_sha256`; projections may reorder detail but never change evidence. Advisory actions contain `basis_refs` and cannot mutate claim verdicts.
- [ ] Run `python -m pytest tests/test_evidence_journey.py -q`; expect PASS.
- [ ] Commit: `feat: add evidence journey state machine`.

### Task 3: Existing-oracle dispatch and packet recheck

**Files:**
- Create: `harness/evidence_packet.py`
- Create: `tests/test_evidence_packet.py`
- Modify: `harness/evidence_journey.py`
- Modify: `tests/test_evidence_journey.py`

- [ ] Write RED tests using `default_registry()` and a tiny software failure fixture. Cover registered code oracle, unknown oracle, timeout/unavailable, receipt drift, omitted raw evidence, tampered event chain, external-root escape, and clean-directory recheck.
- [ ] Implement:

```python
def run_journey_check(journey: dict, claim_id: str, oracle_id: str,
                      candidate: Path, context: dict) -> dict: ...
def pack_journey_packet(out_dir: Path, *, journey: dict,
                        artifact_root: Path) -> dict: ...
def verify_journey_packet(packet_dir: Path) -> dict: ...
```

Wrap existing oracle results. Keep `PASS|FAIL|UNDECIDED|UNVERIFIABLE` exact. Pack through `harness.bundle`; add journey/event-head/pack-manifest facts to criteria and `does_not_prove`.
- [ ] Run `python -m pytest tests/test_evidence_journey.py tests/test_evidence_packet.py tests/test_oracle_registry.py tests/test_bundle.py -q`; expect PASS.
- [ ] Commit: `feat: bind journeys to oracle packets`.

### Task 4: CLI and gateway transport

**Files:**
- Create: `harness/evidence_cli.py`
- Create: `harness/evidence_route.py`
- Create: `tests/test_evidence_cli.py`
- Create: `tests/test_evidence_route.py`
- Modify: `harness/cli_entry.py`
- Modify: `harness/gateway.py`

- [ ] Write RED tests for `journey start`, `project`, `check`, `export`, and `recheck`; JSON stdout; metadata-only arguments; exact nonzero exits; and gateway routes `/api/evidence/start|project|check|export|recheck`.
- [ ] Assert malformed bodies, missing refs, unsupported lenses, and unregistered oracles return typed 4xx results without traceback. Assert no route invokes a provider or network client.
- [ ] Implement thin dispatch to route handlers. Shrink existing files to offset every dispatch line; do not grow grandfathered ceilings.
- [ ] Run `python -m pytest tests/test_evidence_cli.py tests/test_evidence_route.py tests/test_cli_launch.py -q`; expect PASS.
- [ ] Build a wheel in a temporary directory, install it in a clean venv, and run `flywheel journey --help`; expect exit 0 without a checkout.
- [ ] Commit: `feat: expose evidence journey interfaces`.

### Task 5: Progressive-disclosure desktop journey

**Files:**
- Create: `desktop/lib/models/evidence_models.dart`
- Create: `desktop/lib/client/gateway_evidence.dart`
- Create: `desktop/lib/views/journey_view.dart`
- Create: `desktop/test/evidence_models_test.dart`
- Create: `desktop/test/journey_view_test.dart`
- Modify: `desktop/lib/client/gateway_client.dart`
- Modify: `desktop/lib/main.dart`

- [ ] Write RED model tests for exact axes, null reasons, evidence refs, and rejection of unknown verdicts. Write widget tests for Journey-first startup, equal lens ids/verdicts, answer-first disclosure, next action plus rollback, expandable evidence, and offline recheck status.
- [ ] Add `part 'gateway_evidence.dart';`; implement typed transport methods only. Build a Journey destination using existing typography and verdict-only color. Preserve Chat and every current destination.
- [ ] Run `flutter analyze` and `flutter test`; expect PASS.
- [ ] Commit: `feat: make evidence journey the desktop entry`.

### Task 6: Release acceptance packet

**Files:**
- Create: `benchmarks/fixtures/evidence-journey/software-failure-v1.json`
- Create: `tests/test_evidence_journey_e2e.py`
- Create: `project-docs/records/2026-08-12-evidence-journey-spine.md`

- [ ] Execute the fixture from intake through existing code oracle, conclusion, three lenses, export, and clean-directory recheck. Plant one false-accept and one false-reject mutation.
- [ ] Record runtime, counts, null reasons, packet hash, and `does_not_prove`. Do not claim broader domain validity.
- [ ] Run `python -m pytest tests/test_evidence_* tests/test_bundle.py tests/test_oracle_registry.py -q`, full `tests/`, all static gates, `flutter analyze`, and `flutter test`.
- [ ] Run the packet recheck from a clean temporary directory; expect MATCH.
- [ ] Request spec and quality review, fix every material finding, rerun evidence, and commit: `test: verify evidence journey spine`.
