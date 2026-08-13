# Unified Evidence Journey 05 Interchange Enterprise Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import external observability and evaluation artifacts as evidence, export bounded views, and add organization-grade review, ownership, retention, signatures, contests, and supersession without delegating Flywheel verdicts.

**Architecture:** Strict adapters normalize external data into nominal evidence records. Native journey packets remain authoritative. An append-only review queue applies human attestations and governance events; retention removes eligible private payloads while preserving hashes, tombstones, and decision history.

**Tech Stack:** Python standard library verifier path, journey/frontier/domain-pack primitives, existing receipts/bundles/ledger, Flutter/Dart, pytest.

## Fixed boundaries

- OpenTelemetry, MLflow, Phoenix, Langfuse, and generic JSONL scores import as evidence only.
- Imported scores, labels, and provider identities never become Flywheel verdicts or attested model identity.
- Raw papers/datasets/traces remain private by default; exported packets include only allowed refs and redacted presentation artifacts.
- Retention is policy-driven and append-only in history. Deletion leaves a hash-bound tombstone and cannot rewrite prior receipts.

---

### Task 1: Evidence interchange envelope and strict adapters

**Files:**
- Create: `harness/evidence_interchange.py`
- Create: `tests/test_evidence_interchange.py`

- [ ] Write RED tests for OpenTelemetry spans, MLflow evaluations, Phoenix traces, Langfuse observations, and generic JSONL. Cover duplicate keys, non-finite scores, oversize/deep input, unknown fields, secret values, credential URLs, host paths, embedded code, score-to-verdict escalation, and provider identity spoofing.
- [ ] Implement:

```python
def import_evidence(raw: bytes, *, format_id: str, source_facts: dict) -> dict: ...
def export_evidence_view(records: list[dict], *, format_id: str,
                         policy: dict) -> bytes: ...
```

Every record carries source format/version/hash, imported field mapping, omissions, redactions, nominal evidence kind, and `does_not_prove`. No adapter imports third-party runtime packages on the verifier path.
- [ ] Run focused tests; expect PASS.
- [ ] Commit: `feat: add bounded evidence interchange`.

### Task 2: Review queue and attestations

**Files:**
- Create: `harness/evidence_review.py`
- Create: `tests/test_evidence_review.py`

- [ ] Write RED tests for queue states `pending|claimed|reviewed|contested|expired|superseded`, stable owner identity, role/scope/basis, issue/expiry, conflict declaration, omissions, signature state, two-reviewer requirements, revoked signer, concurrent claim, and model-authored attestations.
- [ ] Implement pure transitions plus storage over content-addressed review events. Unsigned attestations remain usable only where pack policy explicitly allows them; model-authored statements stay proposals.
- [ ] Add a reviewer workload projection with counts and age intervals, not a reviewer score.
- [ ] Run focused frontier/journey review tests; expect PASS.
- [ ] Commit: `feat: add evidence review queue`.

### Task 3: Retention, residency, contest, and supersession

**Files:**
- Create: `harness/evidence_retention.py`
- Create: `tests/test_evidence_retention.py`

- [ ] Write RED tests for retain-until, legal hold, residency label, export permission, private-by-default source, tombstone, contest, correction, supersession, checker revocation, attestation expiry, and recheck-due proposals.
- [ ] Assert retention cannot delete outside the admitted store, follow links, erase ledger history, remove held evidence, or make an old receipt look current.
- [ ] Implement `plan_retention`, `apply_retention`, `contest_claim`, and `supersede_claim`. `apply_retention` requires an operator-approved plan hash and returns per-item outcomes.
- [ ] Run focused tests; expect PASS.
- [ ] Commit: `feat: govern evidence lifecycle`.

### Task 4: Organization packets and signed review path

**Files:**
- Create: `harness/organization_packet.py`
- Create: `tests/test_organization_packet.py`
- Modify: `harness/evidence_packet.py`

- [ ] Write RED tests for organization/project/owner ids, policy hash, pack approvals, reviewer roles, signature-required claims, residency/retention summary, contests, supersessions, unresolved evidence, and independent recheck.
- [ ] Reuse existing receipt signing where configured. If a signing key is absent, emit explicit unsigned state and refuse policies requiring signatures. Never serialize key material, environment values, or credential paths.
- [ ] Export one bounded packet with a native authoritative manifest and optional external views. Tampering any view must not alter the native verdict; tampering the native packet must fail recheck.
- [ ] Run packet, receipt, bundle, and signing regressions; expect PASS.
- [ ] Commit: `feat: seal organization evidence packets`.

### Task 5: Enterprise routes, CLI, and desktop review surfaces

**Files:**
- Create: `harness/evidence_enterprise_route.py`
- Create: `harness/evidence_enterprise_cli.py`
- Create: `tests/test_evidence_enterprise_route.py`
- Create: `tests/test_evidence_enterprise_cli.py`
- Create: `desktop/lib/views/evidence_review_view.dart`
- Create: `desktop/test/evidence_review_view_test.dart`
- Modify: `harness/gateway.py`
- Modify: `harness/cli_entry.py`
- Modify: `desktop/lib/main.dart`

- [ ] Write RED tests for import, queue claim/release, attest, contest, supersede, retention plan/apply, organization export, and offline recheck. Every mutating operation requires exact current event-head and policy hashes.
- [ ] Write widget tests for overloaded reviewer triage, senior-engineer diagnosis, independent verifier detail, unresolved/conflicted states, retention preview, and signature status. No composite trust or reviewer score.
- [ ] Implement thin dispatch and server-owned projections. Offset frozen-file growth.
- [ ] Run focused Python and Flutter tests plus clean-wheel help; expect PASS.
- [ ] Commit: `feat: expose governed evidence exchange`.

### Task 6: Interoperability and enterprise acceptance study

**Files:**
- Create: `benchmarks/fixtures/evidence-interchange/corpus-v1.json`
- Create: `tests/test_evidence_interchange_corpus.py`
- Create: `project-docs/records/2026-08-12-evidence-interchange-enterprise.md`

- [ ] Build deidentified fixtures for each adapter with pass/fail/timeout/provider-error/skip/not-run source labels, artifact refs, receipt drift, absent denominators, secret plants, and identity spoofing. Verify that source labels remain evidence and never decide native verdicts.
- [ ] Exercise two-reviewer attestation, contest, supersession, legal hold, permitted retention, denied retention, signed and unsigned policies, bounded export, and clean-directory recheck.
- [ ] Measure import mapping coverage, rejected/malformed count, redactions, queue age/count, signature denominator, recheck success, retention outcomes, resource use, and `does_not_prove`.
- [ ] Run full Python/Flutter/static/package/secret/path gates and the complete Unified Evidence Journey corpus. Export and recheck the release packet.
- [ ] Request security, spec, and quality review, remediate every material finding, rerun evidence, and commit: `test: verify enterprise evidence controls`.
