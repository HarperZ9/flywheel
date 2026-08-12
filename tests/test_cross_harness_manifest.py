import hashlib
import json
from pathlib import Path, PurePosixPath

import pytest

from harness.cross_harness_manifest import _input_hashes, build_manifest, load_json, render_markdown
from harness.cross_harness_cli import main as execute_main
from scripts.run_cross_harness_manifest import DEFAULT_CONTRACT, main as manifest_main

ROOT = Path(__file__).resolve().parent.parent

def _task_set():
    return {
        "schema": "harness.agentic-task-set/v1",
        "task_set_id": "sample_tasks",
        "tasks": [
            {
                "id": "agt-001-index-fallback-integrity",
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
        "schema": "harness.cross-harness-adapter-contract/v2",
        "contract_id": "sample_cross_harness",
        "global_invariants": ["same prompt hash"],
        "planned_scorecard_schema": "harness.cross-harness-task-scorecard/v1",
        "planned_run_receipt_schema": "harness.cross-harness-run-receipt/v1",
        "provider_roles": [
            {
                "provider_role": "codex_harness",
                "harness_id": "codex",
                "model_id": "gpt-5.3-codex-spark",
                "model_display_name": "GPT-5.3-Codex-Spark",
                "requested_model_reference": "gpt-5.3-codex-spark",
                "adapter_state": "contract_only",
                "allowed_modes": ["manifest_only"],
                "required_receipts": ["raw_prompt", "raw_output"],
            },
            {
                "provider_role": "flywheel_harness",
                "harness_id": "flywheel",
                "model_id": "gpt-5.3-codex-spark",
                "model_display_name": "GPT-5.3-Codex-Spark",
                "requested_model_reference": "gpt-5.3-codex-spark",
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

def test_v2_contract_binds_canonical_spark_and_exact_local_release_selectors():
    contract = load_json(ROOT / "benchmarks/cross-harness-adapter-contract-v2.json")

    assert contract["schema"] == "harness.cross-harness-adapter-contract/v2"
    roles = {row["provider_role"]: row for row in contract["provider_roles"]}
    for role in ("codex_harness", "flywheel_harness"):
        assert roles[role]["model_id"] == "gpt-5.3-codex-spark"
        assert roles[role]["model_display_name"] == "GPT-5.3-Codex-Spark"
        assert roles[role]["requested_model_reference"] == "gpt-5.3-codex-spark"
        assert "target_model" not in roles[role]
    assert roles["local_14b"]["endpoint_selector"] == {
        "profile_id": "ollama-release-14b", "backend": "ollama",
        "model_reference": "ollama:flywheel-local-coder-14b",
        "release_asset_sha256": "613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be",
    }
    assert roles["local_32b"]["endpoint_selector"] == {
        "profile_id": "ollama-release-32b", "backend": "ollama",
        "model_reference": "ollama:flywheel-local-coder-32b",
        "release_asset_sha256": "65e6133fbe4d12579a776047a71bebb98ab86f9e3d343ed821b51dac0ce312f4",
    }

def test_manifest_rejects_v1_contract_instead_of_coercing_overloaded_model_identity():
    v1 = load_json(ROOT / "benchmarks/cross-harness-adapter-contract-v1.json")

    with pytest.raises(ValueError, match="unsupported cross-harness contract schema"):
        build_manifest(_task_set(), v1, provider_roles=["codex_harness"])


def test_execution_cli_rejects_manifest_from_v1_contract_before_loading_runtime(tmp_path):
    manifest, matrix = tmp_path / "manifest.json", tmp_path / "matrix.json"
    manifest.write_text(json.dumps({"schema": "harness.cross-harness-manifest/v1", "contract_schema": "harness.cross-harness-adapter-contract/v1"}), encoding="utf-8")
    matrix.write_text(json.dumps({"schema": "harness.adapter-runtime-matrix/v1"}), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest contract schema mismatch"):
        execute_main(["--manifest", str(manifest), "--runtime-matrix", str(matrix), "--artifact-root", str(tmp_path / "artifacts"), "--roles", "codex_harness", "--source-commit", "test", "--source-root", str(tmp_path), "--phase", "test", "--run-id", "test", "--tasks", "agt-001", "--cache", "cold_declared", "--repetitions", "1", "--timeout", "1"])

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
        source_root=str(tmp_path),
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


@pytest.mark.parametrize("kind", ["missing", "directory", "absolute", "traversal", "normalized_traversal", "symlink"])
def test_manifest_rejects_unhashable_repo_input(tmp_path, monkeypatch, kind):
    root, outside = tmp_path / "repo", tmp_path / "outside.json"
    (root / "benchmarks").mkdir(parents=True)
    outside.write_text("{}", encoding="utf-8")
    refs = {"missing": "missing.json", "directory": "inputs", "absolute": str(outside),
            "traversal": "../outside.json", "normalized_traversal": "nested/../fixture.json", "symlink": "linked.json"}
    (root / "inputs").mkdir()
    (root / "fixture.json").write_text("{}", encoding="utf-8")
    if kind == "symlink":
        try: (root / "linked.json").symlink_to(outside)
        except OSError:
            original = Path.resolve
            monkeypatch.setattr(Path, "resolve", lambda path, *a, **kw: outside if path.name == "linked.json" else original(path, *a, **kw))
    task_set = _task_set()
    task_set["tasks"][0]["required_inputs"] = [refs[kind]]
    with pytest.raises(ValueError, match="required input"):
        build_manifest(task_set, _contract(), task_set_path=str(root / "benchmarks" / "tasks.json"), source_root=str(root))


@pytest.mark.parametrize("raw", ['{"key":1,"key":2}', "[]", "null", "7"])
def test_manifest_loader_rejects_duplicate_keys_and_non_objects(tmp_path, raw):
    path = tmp_path / "input.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError): load_json(path)


@pytest.mark.parametrize(("ref", "rejected"), [("workspace://facts/a.json", False), ("external://receipt/a.json", False),
                                                 ("operator://input/a.json", False), ("bogus://a", True), ("file://a", True), ("workspace://", True),
                                                 ("external://   ", True), ("operator://../a", True), ("workspace:///abs", True), ("external://C:/a", True), ("external://C:", True), ("external://C:relative", True), ("operator://a/../b", True)])
def test_nonpilot_typed_inputs_use_exact_scheme_allowlist(tmp_path, ref, rejected):
    task_set = _task_set(); task_set["tasks"][0].update(id="custom-task", required_inputs=[ref], oracle={"checker_id": "custom/v1"})
    call = lambda: build_manifest(task_set, _contract(), task_set_path=str(tmp_path / "benchmarks" / "tasks.json"))
    if rejected:
        with pytest.raises(ValueError, match="required input"): call()
    else: assert call()["task_rows"][0]["input_sha256s"] == {}


@pytest.mark.parametrize("ref", ["external://C:/a", r"external://C:\a", "external://C:", "external://C:relative"])
def test_typed_drive_payload_rejection_is_platform_neutral(tmp_path, monkeypatch, ref):
    monkeypatch.setitem(_input_hashes.__globals__, "Path", PurePosixPath)
    with pytest.raises(ValueError, match="required input"): _input_hashes(tmp_path, [ref], False)


@pytest.mark.parametrize(("task_id", "checker"), [("agt-001-index-fallback-integrity", "index_fallback_integrity/v1"), ("agt-003-codex-flywheel-shared-task", "shared_task_artifact/v1"),
                                                       ("agt-009-receipts-vs-guardrails-friction", "paired_friction/v1"), ("agt-010-documentation-schematic-maintenance", "documentation_maintenance/v1")])
@pytest.mark.parametrize("ref", ["workspace://a", "external://a", "operator://a"])
def test_canonical_pilots_reject_typed_inputs(tmp_path, task_id, checker, ref):
    task_set = _task_set(); task_set["tasks"][0].update(id=task_id, required_inputs=[ref], oracle={"checker_id": checker})
    with pytest.raises(ValueError, match="required input"):
        build_manifest(task_set, _contract(), task_set_path=str(tmp_path / "benchmarks" / "tasks.json"))
@pytest.mark.parametrize(("task_id", "checker"), [("renamed", "index_fallback_integrity/v1"),
                                                     ("agt-001-index-fallback-integrity", "shared_task_artifact/v1")])
def test_registered_checker_and_canonical_task_id_must_pair(tmp_path, task_id, checker):
    task_set = _task_set(); task_set["tasks"][0].update(id=task_id, oracle={"checker_id": checker})
    with pytest.raises(ValueError, match="checker"):
        build_manifest(task_set, _contract(), task_set_path=str(tmp_path / "benchmarks" / "tasks.json"))
def test_frozen_pilot_contract_is_public_clean_and_replayable():
    task_path = ROOT / "benchmarks" / "agentic-task-set-v1.json"
    contract_path = ROOT / "benchmarks" / "cross-harness-adapter-contract-v2.json"
    task_set = json.loads(task_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    manifest = build_manifest(task_set, contract, task_set_path=str(task_path), source_root=str(ROOT))
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
def _copied_contract(tmp_path):
    task, contract = tmp_path / "copied-tasks.json", tmp_path / "copied-contract.json"
    task.write_bytes((ROOT / "benchmarks/agentic-task-set-v1.json").read_bytes())
    contract.write_bytes((ROOT / "benchmarks/cross-harness-adapter-contract-v2.json").read_bytes())
    return task, contract
def test_external_contract_uses_explicit_source_root_without_serializing_it(tmp_path):
    task_path, contract_path = _copied_contract(tmp_path)
    manifest = build_manifest(load_json(task_path), load_json(contract_path), task_set_path=str(task_path),
                              contract_path=str(contract_path), source_root=str(ROOT))
    row = next(row for row in manifest["task_rows"] if row["task_id"].startswith("agt-001")); ref = row["required_inputs"][0]
    assert row["input_sha256s"] == {ref: hashlib.sha256((ROOT / ref).read_bytes()).hexdigest()}
    assert "source_root" not in manifest and str(ROOT.resolve()) not in str(manifest)
    assert (ROOT / ref).read_text(encoding="utf-8") not in json.dumps(manifest)
def test_external_canonical_contract_requires_explicit_source_root(tmp_path):
    task_path, contract_path = _copied_contract(tmp_path)
    with pytest.raises(ValueError, match="source root"):
        build_manifest(load_json(task_path), load_json(contract_path), task_set_path=str(task_path))
@pytest.mark.parametrize("kind", ["missing", "file"])
def test_source_root_must_be_an_existing_directory(tmp_path, kind):
    root = tmp_path / "source"
    if kind == "file": root.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ValueError, match="source root"):
        build_manifest(_task_set(), _contract(), source_root=str(root))
def test_input_hash_binds_source_bytes_not_contract_location(tmp_path):
    source, copied = tmp_path / "source", tmp_path / "external/tasks.json"; source.mkdir(); copied.parent.mkdir()
    fixture = source / "fixture.json"; fixture.write_bytes(b"first")
    task = _task_set(); task["tasks"][0]["required_inputs"] = ["fixture.json"]
    first = build_manifest(task, _contract(), task_set_path=str(copied), source_root=str(source))["task_rows"][0]
    fixture.write_bytes(b"second")
    second = build_manifest(task, _contract(), task_set_path=str(copied), source_root=str(source))["task_rows"][0]
    assert first["input_sha256s"] != second["input_sha256s"]
    assert (first["task_set_id"], first["task_id"], first["raw_prompt_sha256"]) == (second["task_set_id"], second["task_id"], second["raw_prompt_sha256"])
    assert "first" not in json.dumps(first) and "second" not in json.dumps(second)
def test_manifest_cli_requires_source_root_and_supports_external_contract(tmp_path, capsys):
    task_path, contract_path = _copied_contract(tmp_path); out, markdown = tmp_path / "manifest.json", tmp_path / "manifest.md"
    base = ["--task-set", str(task_path), "--contract", str(contract_path), "--provider-roles", "codex_harness", "--out", str(out), "--markdown-out", str(markdown)]
    with pytest.raises(ValueError, match="source root"): manifest_main(base)
    assert not out.exists()
    assert manifest_main([*base, "--source-root", str(ROOT)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["schema"] == "harness.cross-harness-manifest/v1"
    capsys.readouterr()
def test_manifest_cli_safely_defaults_source_root_for_checkout_contract(tmp_path, capsys):
    out = tmp_path / "manifest.json"
    assert DEFAULT_CONTRACT.endswith("cross-harness-adapter-contract-v2.json")
    assert manifest_main(["--task-set", str(ROOT / "benchmarks/agentic-task-set-v1.json"), "--contract",
                          str(ROOT / "benchmarks/cross-harness-adapter-contract-v2.json"), "--provider-roles", "codex_harness", "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["schema"] == "harness.cross-harness-manifest/v1"
    deck = json.loads((ROOT / "benchmarks/dry-run-preflight-command-deck-v1.json").read_text(encoding="utf-8"))
    command = next(row["command"] for row in deck["commands"] if row["id"] == "deck-012-cross-harness-manifest")
    assert "--source-root C:/dev/local-model" in command and "cross-harness-adapter-contract-v2.json" in command
    capsys.readouterr()
