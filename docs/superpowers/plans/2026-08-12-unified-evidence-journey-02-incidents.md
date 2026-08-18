# Unified Evidence Journey 02 Incident Compiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert witnessed failures into privacy-reviewed, reproducible incident cases, regression fixtures, lesson candidates, and independently verified mitigation evidence.

**Architecture:** Source adapters normalize existing audit, eval, cross-harness, provider, drift, contest, and operator evidence into `flywheel.incident-case/v1`. Compilation is deterministic. Proposed tests, lessons, and governance changes remain pending until explicit review; none are auto-admitted or executed.

**Tech Stack:** Python standard library, evidence journey spine, audit/eval receipts, cross-harness artifacts, lesson store, pytest.

## Fixed boundaries

- Only witnessed, hash-bound inputs can become incidents.
- Raw evidence remains referenced and private; exported cases use sanitized, minimized fixtures.
- Compilation never runs generated code, edits policy, or writes to the lesson store.
- A mitigation closes only after original-case replay, relevant negative controls, and independent packet recheck.

---

### Task 1: Incident schema and source normalization

**Files:**
- Create: `harness/incident_case.py`
- Create: `harness/incident_sources.py`
- Create: `tests/test_incident_case.py`
- Create: `tests/test_incident_sources.py`

- [ ] Write RED tests for exact schema, immutable source refs, failure class, boundary, preconditions, blast radius, observed/expected, minimization state, privacy state, proposed invariant, owner, recurrence/expiry/retirement, and source kinds `audit|eval|cross_harness|provider|drift|contest|operator`.
- [ ] Cover missing receipt, drifted receipt, secret-shaped content, host paths, duplicate JSON keys, unsupported source, and source hash mismatch.
- [ ] Implement:

```python
def normalize_incident_source(source: dict, *, root: Path) -> dict: ...
def new_incident_case(*, case_id: str, source: dict,
                      failure: dict, created_at: str) -> dict: ...
def verify_incident_case(case: dict, *, root: Path) -> dict: ...
```

Use explicit enums and relative refs. Preserve provider rejection separately from malformed output and unavailable routes.
- [ ] Run both focused files; expect PASS.
- [ ] Commit: `feat: define witnessed incident cases`.

### Task 2: Compiler, minimizer, and review gate

**Files:**
- Create: `harness/incident_compiler.py`
- Create: `tests/test_incident_compiler.py`

- [ ] Write RED tests for deterministic minimization, no semantic broadening, sanitized reproduction, proposed invariant, regression matrix, mitigation refs, and exact review states `draft|privacy_reviewed|behavior_reviewed|admitted|retired`.
- [ ] Plant adversarial cases: a secret only in a nested string, an absolute path, an unrelated event whose removal changes nothing, a removal that changes the failure, a fabricated expected result, and a stale source receipt.
- [ ] Implement:

```python
def compile_incident(source: dict, *, root: Path, case_id: str) -> dict: ...
def minimize_incident(case: dict, witness: Callable[[dict], bool]) -> dict: ...
def review_incident(case: dict, review: dict) -> dict: ...
```

The witness may only consume a registered, bounded replay adapter. Human review must name reviewer, scope, basis, issue/expiry times, and signature state.
- [ ] Run `python -m pytest tests/test_incident_case.py tests/test_incident_compiler.py -q`; expect PASS.
- [ ] Commit: `feat: compile failures into reviewed cases`.

### Task 3: Regression and mitigation proof

**Files:**
- Create: `harness/incident_regression.py`
- Create: `tests/test_incident_regression.py`
- Modify: `harness/incident_compiler.py`

- [ ] Write RED tests proving a case emits a data fixture plus expected invariant, not executable source. Cover original failure reproduced, mitigation absent, mitigation claimed without before/after evidence, negative-control regression, checker drift, and independent recheck.
- [ ] Implement:

```python
def build_regression(case: dict, *, out_dir: Path) -> dict: ...
def evaluate_mitigation(case: dict, before: dict, after: dict,
                        controls: list[dict]) -> dict: ...
```

Return UNVERIFIABLE when a safe witness is unavailable. Closure binds before/after receipt hashes, control denominators, and limitations.
- [ ] Run incident plus bundle/receipt regressions; expect PASS.
- [ ] Commit: `feat: prove incident mitigations`.

### Task 4: Lesson bridge without automatic admission

**Files:**
- Create: `harness/incident_lesson.py`
- Create: `tests/test_incident_lesson.py`
- Modify: `harness/lesson_mappers.py`
- Modify: `tests/test_lesson_mappers.py`

- [ ] Write RED tests mapping an admitted incident to a `lesson_candidate`; preserve case, invariant, evidence, expiry, and retirement refs. Assert compiling or closing an incident never calls `LessonStore.add`.
- [ ] Implement a pure `incident_to_lesson_candidate(case) -> dict` mapper and add an explicit, separately invoked admission adapter compatible with the existing lesson transition rules.
- [ ] Run lesson and incident suites; expect PASS.
- [ ] Commit: `feat: bridge reviewed incidents to lessons`.

### Task 5: Routes, CLI, and desktop incident view

**Files:**
- Create: `harness/incident_route.py`
- Create: `harness/incident_cli.py`
- Create: `tests/test_incident_route.py`
- Create: `tests/test_incident_cli.py`
- Create: `desktop/lib/views/incident_view.dart`
- Create: `desktop/test/incident_view_test.dart`
- Modify: `harness/gateway.py`
- Modify: `harness/cli_entry.py`
- Modify: `desktop/lib/main.dart`

- [ ] Write RED transport tests for compile, review, regression export, mitigation evaluation, and packet recheck. Write widget tests showing next safe action first, blast radius and alternatives second, and raw refs/recheck third.
- [ ] Add only thin dispatch to frozen files and offset lines. No endpoint auto-retry, generated-test execution, or policy write is exposed.
- [ ] Run focused Python and Flutter tests; expect PASS.
- [ ] Commit: `feat: expose incident compiler journey`.

### Task 6: July/August deidentified corpus and release proof

**Files:**
- Create: `benchmarks/fixtures/incidents/provider-rejection-v1.json`
- Create: `benchmarks/fixtures/incidents/admission-label-v1.json`
- Create: `benchmarks/fixtures/incidents/zero-quality-copy-v1.json`
- Create: `tests/test_incident_corpus.py`
- Create: `project-docs/records/2026-08-12-incident-compiler.md`

- [ ] Derive fixtures from public-safe facts only: structured provider rejection, static admission block ordering, and executed scorecards with a zero deterministic-quality denominator. Do not copy raw prompts, account details, tokens, or host paths.
- [ ] Prove each fixture reproduces the old invariant failure, the current code satisfies the invariant, a planted regression fails, and the packet rechecks independently.
- [ ] Run full Python/static gates and secret/path scans. Record corpus size, reproduced count, refused count, false-accept mutations, privacy omissions, and `does_not_prove`.
- [ ] Request spec and quality review, remediate findings, rerun, and commit: `test: verify incident compiler corpus`.
