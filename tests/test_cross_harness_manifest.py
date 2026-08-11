import hashlib
import json
from pathlib import Path

import pytest

from harness.cross_harness_manifest import build_manifest, load_json, render_markdown

ROOT = Path(__file__).resolve().parent.parent


def _task_set():
    return {
        "schema": "harness.agentic-task-set/v1",
        "task_set_id": "sample_tasks",
        "tasks": [
            {
                "id": "agt-001",
                "lane": "agentic_tool_workflows",
                "difficulty": "focused",
                "prompt": "Run the same task across harnesses.",
                "required_inputs": [],
                "expected_artifacts": ["report.json", "report.md"],
                "scoring_focus": ["quality", "reproducibility"],
                "must_not": ["run providers during manifest generation"],
                "oracle": {
                    "checker_id": "index_fallback_integrity/v1",
                    "fixture": "benchmarks/fixtures/cross-harness/index-events-v1.json",
                },
            }
        ],
    }


def _contract():
    return {
        "schema": "harness.cross-harness-adapter-contract/v1",
        "contract_id": "sample_cross_harness",
        "global_invariants": ["same prompt hash"],
        "planned_scorecard_schema": "harness.cross-harness-task-scorecard/v1",
        "planned_run_receipt_schema": "harness.cross-harness-run-receipt/v1",
        "provider_roles": [
            {
                "provider_role": "codex_harness",
                "harness_id": "codex",
                "target_model": "5.3-Codex-Spark",
                "adapter_state": "contract_only",
                "allowed_modes": ["manifest_only"],
                "required_receipts": ["raw_prompt", "raw_output"],
            },
            {
                "provider_role": "flywheel_harness",
                "harness_id": "flywheel",
                "target_model": "5.3-Codex-Spark",
                "adapter_state": "contract_only",
                "allowed_modes": ["manifest_only"],
                "required_receipts": ["raw_prompt", "raw_output"],
            },
        ],
        "scorecard_row_contract": {
            "required_metrics": ["task_completion", "quality", "reproducibility"]
        },
        "comparability_checks": ["same raw_prompt_sha256"],
    }


def test_cross_harness_manifest_expands_same_prompt_across_provider_roles():
    manifest = build_manifest(_task_set(), _contract(), provider_roles=["codex_harness", "flywheel_harness"])

    assert manifest["schema"] == "harness.cross-harness-manifest/v1"
    assert manifest["status"] == "planned_not_executed"
    assert manifest["benchmark_id"] == "cross_harness_reproducibility_matrix"
    assert manifest["summary"]["provider_execution"] is False
    assert manifest["summary"]["endpoint_probe"] is False
    assert manifest["summary"]["benchmark_execution"] is False
    assert manifest["task_count"] == 1
    assert len(manifest["dry_scorecard_rows"]) == 2
    assert {row["provider_role"] for row in manifest["dry_scorecard_rows"]} == {
        "codex_harness",
        "flywheel_harness",
    }
    assert len({row["raw_prompt_sha256"] for row in manifest["dry_scorecard_rows"]}) == 1
    assert all(row["failure_class"] == "not_executed" for row in manifest["dry_scorecard_rows"])


def test_cross_harness_manifest_rejects_unknown_provider_role():
    with pytest.raises(ValueError, match="unknown cross-harness provider roles"):
        build_manifest(_task_set(), _contract(), provider_roles=["missing_provider"])


def test_cross_harness_manifest_markdown_declares_non_execution():
    markdown = render_markdown(build_manifest(_task_set(), _contract(), provider_roles=["codex_harness"]))

    assert "# Cross-harness manifest" in markdown
    assert "Provider execution: `false`" in markdown
    assert "codex_harness" in markdown


def test_manifest_preserves_replayable_prompt_oracle_and_input_hash(tmp_path):
    source = tmp_path / "fixture.json"
    source.write_text('{"fact": 1}\n', encoding="utf-8")
    task_set = _task_set()
    task_set["tasks"][0]["required_inputs"] = ["fixture.json"]

    row = build_manifest(
        task_set,
        _contract(),
        provider_roles=["codex_harness"],
        task_set_path=str(tmp_path / "benchmarks" / "task-set.json"),
    )["task_rows"][0]

    assert hashlib.sha256(row["raw_prompt"].encode()).hexdigest() == row["raw_prompt_sha256"]
    assert row["oracle"]["checker_id"] == "index_fallback_integrity/v1"
    assert row["input_sha256s"] == {
        "fixture.json": hashlib.sha256(source.read_bytes()).hexdigest()
    }
    assert row["response_envelope"] == {
        "type": "json_object",
        "artifacts": {"report.json": "json_object", "report.md": "markdown_string"},
        "additional_properties": False,
    }


@pytest.mark.parametrize("kind", ["missing", "directory", "absolute", "traversal", "symlink"])
def test_manifest_rejects_unhashable_repo_input(tmp_path, monkeypatch, kind):
    root, outside = tmp_path / "repo", tmp_path / "outside.json"
    (root / "benchmarks").mkdir(parents=True)
    outside.write_text("{}", encoding="utf-8")
    refs = {"missing": "missing.json", "directory": "inputs", "absolute": str(outside),
            "traversal": "../outside.json", "symlink": "linked.json"}
    (root / "inputs").mkdir()
    if kind == "symlink":
        try: (root / "linked.json").symlink_to(outside)
        except OSError:
            original = Path.resolve
            monkeypatch.setattr(Path, "resolve", lambda path, *a, **kw: outside if path.name == "linked.json" else original(path, *a, **kw))
    task_set = _task_set()
    task_set["tasks"][0]["required_inputs"] = [refs[kind]]
    with pytest.raises(ValueError, match="required input"):
        build_manifest(task_set, _contract(), task_set_path=str(root / "benchmarks" / "tasks.json"))


@pytest.mark.parametrize("raw", ['{"key":1,"key":2}', "[]", "null", "7"])
def test_manifest_loader_rejects_duplicate_keys_and_non_objects(tmp_path, raw):
    path = tmp_path / "input.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError): load_json(path)


@pytest.mark.parametrize(("ref", "rejected"), [("workspace://facts/a.json", False), ("external://receipt/a.json", False),
                                                 ("operator://input/a.json", False), ("bogus://a", True), ("file://a", True), ("workspace://", True),
                                                 ("external://   ", True), ("operator://../a", True), ("workspace:///abs", True), ("external://C:/a", True), ("operator://a/../b", True)])
def test_nonpilot_typed_inputs_use_exact_scheme_allowlist(tmp_path, ref, rejected):
    task_set = _task_set(); task_set["tasks"][0]["required_inputs"] = [ref]
    call = lambda: build_manifest(task_set, _contract(), task_set_path=str(tmp_path / "benchmarks" / "tasks.json"))
    if rejected:
        with pytest.raises(ValueError, match="required input"): call()
    else: assert call()["task_rows"][0]["input_sha256s"] == {}


@pytest.mark.parametrize("task_id", ["agt-001-index-fallback-integrity", "agt-003-codex-flywheel-shared-task",
                                      "agt-009-receipts-vs-guardrails-friction", "agt-010-documentation-schematic-maintenance"])
@pytest.mark.parametrize("ref", ["workspace://a", "external://a", "operator://a"])
def test_canonical_pilots_reject_typed_inputs(tmp_path, task_id, ref):
    task_set = _task_set(); task_set["tasks"][0].update(id=task_id, required_inputs=[ref])
    with pytest.raises(ValueError, match="required input"):
        build_manifest(task_set, _contract(), task_set_path=str(tmp_path / "benchmarks" / "tasks.json"))


def test_frozen_pilot_contract_is_public_clean_and_replayable():
    task_path = ROOT / "benchmarks" / "agentic-task-set-v1.json"
    contract_path = ROOT / "benchmarks" / "cross-harness-adapter-contract-v1.json"
    task_set = json.loads(task_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    manifest = build_manifest(task_set, contract, task_set_path=str(task_path))
    rows = {row["task_id"]: row for row in manifest["task_rows"]}
    expected = {
        "agt-001-index-fallback-integrity": ("index_fallback_integrity_report.json", "index_fallback_integrity_report.md"),
        "agt-003-codex-flywheel-shared-task": ("codex_flywheel_shared_task_scorecard.json", "codex_flywheel_shared_task_scorecard.md"),
        "agt-009-receipts-vs-guardrails-friction": ("receipts_vs_guardrails_friction.json", "receipts_vs_guardrails_friction.md"),
        "agt-010-documentation-schematic-maintenance": ("documentation_schematic_maintenance_receipt.json", "documentation_schematic_maintenance_receipt.md"),
    }
    for task_id, basenames in expected.items():
        row = rows[task_id]
        assert tuple(row["expected_artifacts"]) == basenames
        assert row["input_sha256s"] and set(row["input_sha256s"]) == set(row["required_inputs"])
        assert row["oracle"]["checker_id"].endswith("/v1")
        assert "Response envelope (JSON only):" in row["raw_prompt"]
    serialized = json.dumps([task_set, contract])
    assert not any(value in serialized for value in ("C:/", "E:/", "C:\\\\", "AppData", "cross_harness_runs"))
    assert all(role["adapter_id"] for role in contract["provider_roles"])
    assert all(role.get("endpoint_selector") for role in contract["provider_roles"] if role["provider_role"].startswith("local_"))
    oracle_contract = task_set["oracle_contract"]
    for task_id in expected:
        oracle = rows[task_id]["oracle"]
        fixture = json.loads((ROOT / oracle["fixture"]).read_text(encoding="utf-8"))
        assert fixture["task_id"] == task_id
        assert fixture["failure_code_vocabulary"]["common"] == oracle_contract["common_failure_codes"]
        assert fixture["failure_code_vocabulary"]["task"] == oracle_contract["checkers"][oracle["checker_id"]]["failure_codes"]
        assert oracle["required_json_fields"]
