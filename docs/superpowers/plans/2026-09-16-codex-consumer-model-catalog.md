# Codex Consumer Model Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `codex-cli` model picker use the official Codex app-server model catalog without silently falling back to an unsupported default model.

**Architecture:** Add a narrow helper that converts `codex_consumer_account.discover_models()` rows into the existing `/api/models` shape while keeping catalog ids separate from executable model routes. Wire only `harness.model_roster.list_models("codex-cli")` to that helper. Update `ModelSelectorButton` so endpoints can declare `endpoint_default_selectable: false`; for `codex-cli`, the provider default is a suggestion row that still emits an explicit model route.

**Tech Stack:** Python stdlib, pytest, Flutter widget tests, existing Codex app-server client.

**Spec:** Root instruction on 2026-09-16 for the consumer Codex model discovery slice; adjacent native session adapter files remain frozen.

## Global Constraints

- Do not edit native provider-session adapter/client/transport/backend/gateway runtime files.
- Do not change `harness/endpoints.py`, `harness/providers.py`, registry defaults, credentials, provider generation, or live provider calls.
- Preserve exact separation between catalog id and executable model route.
- Hidden, duplicate, failed, missing-default, and ambiguous-default catalogs fail closed without a fake endpoint-default row.
- `endpoint_default_selectable` is `false` for `codex-cli`; `actual_provider_default` is a suggestion only, not inference-readiness proof.
- If an empty route still reaches execution, report the seam instead of silently choosing a different hardcoded model.

---

### Task 1: Backend catalog adapter

**Files:**
- Create: `harness/codex_consumer_models.py`
- Create: `tests/test_model_roster_codex_consumer.py`
- Modify: `harness/model_roster.py`

**Interfaces:**
- Consumes: `discover_models(client, include_hidden=False, page_limit=100, max_pages=10) -> dict`
- Produces: `codex_consumer_roster(endpoint: str, configured_default: str, *, timeout: float = 3.0, client_factory: Callable | None = None) -> dict`

- [ ] Write pytest coverage for route-vs-catalog separation, hidden/duplicate omission, ambiguous defaults, sanitized failure, close lifecycle, and no fake fallback.
- [ ] Verify the tests fail because `harness.codex_consumer_models` and the `codex-cli` model roster integration do not exist.
- [ ] Implement the helper with deterministic normalization and `client.close()` in `finally` when the client was created.
- [ ] Wire `model_roster._native_or_unknown("codex-cli")` through the helper.
- [ ] Run the focused backend tests.

### Task 2: Picker explicit-selection behavior

**Files:**
- Modify: `desktop/lib/widgets/model_selector.dart`
- Modify: `desktop/test/model_selector_test.dart`
- Modify: `desktop/test/model_selector_manual_test.dart`

**Interfaces:**
- Consumes: `/api/models` docs with optional `endpoint_default_selectable: false`
- Produces: a picker callback that emits a non-empty model route for `codex-cli` catalog rows and hides the endpoint-default reset when the endpoint disallows it.

- [ ] Write widget tests showing a `codex-cli` default catalog row emits its explicit route and that catalog failure does not synthesize `endpoint default`.
- [ ] Verify the widget tests fail against the current picker.
- [ ] Update row selection, empty-roster fallback, and the footer action to honor `endpoint_default_selectable`.
- [ ] Run the focused picker tests.

### Task 3: Verification and handoff

**Files:**
- Verify only the files listed above.

- [ ] Run Python syntax/file gates relevant to the changed Python files.
- [ ] Run focused pytest and focused Flutter widget tests.
- [ ] Record exact SHA-256 hashes and physical line counts for every edited file.
- [ ] Report the remaining execution seam: an empty Codex model selection can still fall through to `harness.endpoints.PROVIDERS["codex"]["model"]`; the proposed follow-up is a typed selection-required response at the operation/admission boundary.
