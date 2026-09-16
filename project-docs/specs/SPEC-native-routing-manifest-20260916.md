# Native Routing Manifest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task in this same isolated worktree. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a planned-only native-routing task-family manifest validator and safe model-visible projection renderer, with demo fixtures and leakage tests, without running models or benchmarks.

**Architecture:** Implement one focused stdlib-only module that validates a synthetic demo task-family set, builds a planned manifest, and renders model-visible prompt/features/cache-key material plus a private hidden-authority manifest. The renderer must fail closed if hidden authority strings, semantic family tags, split roles, or private labels reach model-visible artifacts. A small CLI mirrors the existing agentic manifest command pattern and writes planned JSON/Markdown only.

**Tech Stack:** Python stdlib only, pytest for focused tests, existing Flywheel harness conventions.

**Spec:** Private v2 design was accepted for design only. This public plan intentionally does not copy private paths or private authority payloads.

## Global Constraints

- No model calls, endpoint launches, training, downloads, global installs, benchmark execution, release, or full-suite run in this slice.
- Keep source public-clean: no private local paths, credentials, raw private authorities, or hidden expected values in public outputs.
- Strictly separate hard policy labels from unmeasured workflow utility; workflow choice may be described only as planned observed utility, never an optimal gold label.
- Current fixture scope is text/account-state/action-log only. It must not claim multimodal, UI, OCR, image, video, LRM, or general model performance.
- New Python files must stay below the 300-line gate. Do not grow frozen large files.
- Fixture cases are demos for schema and leakage behavior, not a complete 180-case benchmark.

---

### Task 1: Failing validator and renderer tests

**Files:**
- Create: `tests/test_native_routing_manifest.py`

**Interfaces:**
- Consumes: future `harness.native_routing_manifest.build_manifest`, `render_case_projection`, and `render_markdown`.
- Produces: behavioral tests that prove the module rejects semantic leaks and separates hard policy from workflow utility.

- [x] **Step 1: Write tests that should fail before implementation**

Test cases to include:

```python
def test_build_manifest_renders_planned_rows_without_execution():
    manifest = build_manifest(_demo_doc(), source_path="demo.json", source_sha256="abc")
    assert manifest["schema"] == "harness.native-routing-task-family-manifest/v1"
    assert manifest["status"] == "planned_not_executed"
    assert manifest["summary"]["model_execution"] is False
    assert manifest["summary"]["benchmark_execution"] is False
    assert manifest["summary"]["total_cases"] == 2
    assert manifest["summary"]["workflow_utility_measured"] is False


def test_projection_omits_private_family_labels_and_cache_keys():
    projection = render_case_projection(_demo_doc(), _demo_doc()["cases"][0], _demo_doc()["candidate_arms"][0])
    visible = projection["model_visible_prompt"] + json.dumps(projection["model_visible_features"], sort_keys=True) + json.dumps(projection["cache_key_material"], sort_keys=True)
    assert "permission gate" not in visible
    assert "AUTH-SENTINEL" not in visible
    assert "development" not in visible
    assert projection["hidden_authority_manifest"]["hidden_leakage_sentinels"] == ["AUTH-SENTINEL"]


def test_projection_fails_closed_when_hidden_sentinel_reaches_visible_text():
    doc = _demo_doc()
    doc["cases"][0]["scenario_state"]["redacted_user_text"] = "AUTH-SENTINEL leaked"
    with pytest.raises(ValueError, match="leakage"):
        render_case_projection(doc, doc["cases"][0], doc["candidate_arms"][0])


def test_validator_rejects_workflow_utility_claimed_as_gold():
    doc = _demo_doc()
    doc["cases"][1]["workflow_utility_contract"]["no_optimal_gold"] = False
    with pytest.raises(ValueError, match="no optimal gold"):
        build_manifest(doc)
```

- [x] **Step 2: Run red test**

Run: `python -m pytest tests/test_native_routing_manifest.py -q`

Expected: FAIL because `harness.native_routing_manifest` does not exist.

---

### Task 2: Implement validator and renderer module

**Files:**
- Create: `harness/native_routing_manifest.py`

**Interfaces:**
- Produces:
  - `load_json(path: Path) -> dict[str, Any]`
  - `file_sha256(path: Path) -> str`
  - `build_manifest(doc: dict[str, Any], *, source_path: str = "", source_sha256: str = "", artifact_dir: str = "artifacts/native-routing") -> dict[str, Any]`
  - `render_case_projection(doc: dict[str, Any], case: dict[str, Any], arm: dict[str, Any]) -> dict[str, Any]`
  - `render_markdown(manifest: dict[str, Any]) -> str`

- [x] **Step 1: Implement minimal validation**

Validate schema, non-empty cases, non-empty arms, opaque ids, text-state modality, hard-policy contracts, unmeasured workflow utility, no-optimal-gold semantics, execution denominator fields, and hidden sentinel lists.

- [x] **Step 2: Implement model-visible projection**

Render only redacted scenario text, opaque case id, opaque option ids, opaque policy excerpt ids, and pinned arm id/class. Build cache-key material from schema, case id, arm id, and content hashes only. Keep split role, private labels, family ids, hidden authorities, expected values, and semantic tags out of model-visible prompt/features/cache material.

- [x] **Step 3: Implement leakage guard**

Collect forbidden terms from split role, private human label, semantic family tags, hidden authority refs, hidden expected fields, and hidden leakage sentinels. Fail if any forbidden term appears in prompt, features, or cache-key material. Do not scan the private hidden-authority manifest.

- [x] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_native_routing_manifest.py -q`

Expected: PASS.

---

### Task 3: Add demo fixture and CLI

**Files:**
- Create: `benchmarks/fixtures/native-routing-task-family-demo-v1.json`
- Create: `scripts/run_native_routing_manifest.py`
- Modify: `tests/test_native_routing_manifest.py`

**Interfaces:**
- CLI consumes a task-family fixture and produces planned manifest JSON/Markdown plus optional projection files.

- [x] **Step 1: Add public-clean demo fixture**

Use two synthetic demo cases only. Include one hard-policy support case and one workflow-utility planned case. Mark `dataset_status` as `demo_fixture_not_180_case_benchmark`.

- [x] **Step 2: Add CLI**

Arguments: `--task-set`, `--out`, `--markdown-out`, `--projection-dir`, `--artifact-dir`. Defaults may point to repo-relative fixture and temporary outputs, not private paths.

- [x] **Step 3: Add CLI tests**

Assert the CLI writes planned JSON/Markdown, optional projection files, and no model execution flags.

- [x] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_native_routing_manifest.py -q`

Expected: PASS.

---

### Task 4: Static gates and freeze for review

**Files:**
- No new source files beyond Tasks 1-3.

**Verification:**
- `python -m py_compile harness/native_routing_manifest.py scripts/run_native_routing_manifest.py`
- `python -m pytest tests/test_native_routing_manifest.py -q`
- `python scripts/check_file_gate.py`
- `python scripts/check_verifier_stdlib.py`
- `python scripts/check_public_instructions.py`
- `python scripts/check_claim_language.py`
- `git diff --check`

**Completion rule:** Report exact command outputs, changed file hashes, limitations, and remaining gated work. Do not run the full suite until resource coordination.

## Implementation Result

Implemented in this branch for review:

- `harness/native_routing_manifest.py` validates planned-only native-routing demo manifests, separates hard-policy constraints from unmeasured workflow utility, and renders safe model-visible projections.
- `scripts/run_native_routing_manifest.py` writes planned JSON/Markdown and optional projection files without model execution.
- `benchmarks/fixtures/native-routing-task-family-demo-v1.json` is a two-case synthetic demo fixture only, not a completed 180-case benchmark.
- `tests/test_native_routing_manifest.py` covers planned rows, leakage into prompts/features/cache keys, no-optimal-gold validation, markdown limits, and CLI output.

Left gated for later work: full real case authoring, arm pinning, arm execution, utility measurement, coverage ingestion, and any benchmark comparison.

## Status: IMPLEMENTED FOR REVIEW
