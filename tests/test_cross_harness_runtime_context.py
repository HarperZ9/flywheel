from __future__ import annotations

import json, os, shutil
from pathlib import Path

import pytest

from harness.cross_harness_adapters import _enforcement
from harness.cross_harness_artifacts import materialize_response_envelope, remove_readonly_tree
from harness.cross_harness_executor import execute_cross_harness_manifest
from harness.cross_harness_manifest import build_manifest, load_json
from harness.cross_harness_oracles import _CHECKERS as REGISTERED_CHECKERS
from harness.cross_harness_runtime_context import build_runtime_context
from harness.cross_harness_types import AdapterResult, AvailabilityResult


ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory permissions are required")
def test_remove_readonly_tree_handles_read_only_parent_directories(tmp_path):
    root = tmp_path / "readonly"
    nested = root / "fixtures" / "cross-harness"
    nested.mkdir(parents=True)
    (nested / "fixture.json").write_text("{}", encoding="utf-8")
    for directory in (root, root / "fixtures", nested):
        directory.chmod(0o555)
    (nested / "fixture.json").chmod(0o444)
    remove_readonly_tree(root)
    assert not root.exists()


class ContextReadingAdapter:
    role = "codex_harness"
    adapter_id = "codex_cli_json/v1"

    def __init__(self) -> None:
        self.context: dict = {}

    def enforcement(self, _request):
        return _enforcement({"boundary": "test_read_only"})

    def availability(self, _request):
        return AvailabilityResult(True, "", "available", {"provider_called": False})

    def execute(self, request):
        context_path = request.workspace_root / "benchmark" / "context.json"
        self.context = json.loads(context_path.read_text(encoding="utf-8"))
        fixture = json.loads(
            (request.workspace_root / "benchmarks" / "fixtures" / "cross-harness" / "index-events-v1.json").read_text(
                encoding="utf-8"
            )
        )
        classes, citations = [], []
        for event in fixture["events"]:
            if event.get("type") == "mcp_call" and event.get("outcome") == "failure":
                classes.append("live_mcp_failure")
            elif event.get("type") == "artifact_read" and event.get("source") == "stale":
                classes.append("stale_artifact_use")
            elif event.get("type") == "json_parse" and event.get("outcome") == "failure":
                classes.append("invalid_json")
            elif event.get("type") == "match" and event.get("mode") == "degraded":
                classes.append("degraded_match")
            else:
                continue
            citations.append(event["event_id"])
        values = self.context["harness_values"]
        report = {
            "task_id": values["task_id"],
            "input_sha256s": values["input_sha256s"],
            "receipt_input_sha256s": values["receipt_input_sha256s"],
            "failure_classes": sorted(classes),
            "cited_event_ids": sorted(citations),
        }
        output = json.dumps(
            {
                "artifacts": {
                    "index_fallback_integrity_report.json": report,
                    "index_fallback_integrity_report.md": f"# {request.task_id}\n\nFixture-derived result.",
                }
            },
            separators=(",", ":"),
        )
        return AdapterResult(
            "returned", output, [], 7, request.requested_model_reference, "unsupported",
            "", "", {}, {}, [], [], "structured_provider_event",
        )


@pytest.fixture(scope="session")
def staged_source(tmp_path_factory):
    """A source tree holding exactly the files this manifest names.

    The executor snapshots its whole source root, SHA-256ing every file, twice
    per run (before and after). Pointed at the repo root that is honest but
    unbounded: it hashes whatever the checkout happens to contain, so the cost
    is a property of the machine rather than of the test. On a clean CI
    checkout that is small; on a working tree carrying artifacts/, build/,
    dist/ and worktrees it reached ~36.5k files / ~2.9 GB and blew the
    per-test timeout. A test whose verdict depends on how much unrelated
    output is lying around is not measuring what it claims to.

    The manifest needs 18 repo-relative inputs, ~289 KB. Staging those keeps
    the snapshot exact -- the copies are byte-identical, so every
    input_sha256 still matches -- while making the cost a property of the
    task set. Inputs carrying a scheme (external://, operator://,
    workspace://) are not repo-relative and the manifest resolves them
    itself."""
    task_set = load_json(ROOT / "benchmarks" / "agentic-task-set-v1.json")
    wanted = {
        "benchmarks/agentic-task-set-v1.json",
        "benchmarks/cross-harness-adapter-contract-v2.json",
    }
    for task in task_set["tasks"]:
        wanted.update(task.get("required_inputs", []))
        fixture = (task.get("oracle") or {}).get("fixture")
        if fixture:
            wanted.add(fixture)
    root = tmp_path_factory.mktemp("cross-harness-source")
    for rel in sorted(wanted):
        if "://" in rel:
            continue
        src = ROOT / rel
        if not src.is_file():
            continue
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return root


def _manifest(source_root):
    return build_manifest(
        load_json(ROOT / "benchmarks" / "agentic-task-set-v1.json"),
        load_json(ROOT / "benchmarks" / "cross-harness-adapter-contract-v2.json"),
        source_root=str(source_root),
        provider_roles=["codex_harness"],
    )


def _runtime():
    return {
        "runtime_rows": [
            {
                "provider_role": "codex_harness",
                "focused_run_ready": True,
                "blocking_gates": [],
                "endpoint_profile_matches": [],
                "endpoint_gate_matches": [],
            }
        ]
    }


def test_manifest_prompt_requires_role_neutral_runtime_context_and_compact_json(staged_source):
    prompt = next(row for row in _manifest(staged_source)["task_rows"]
                  if row["task_id"].startswith("agt-001"))["raw_prompt"]
    assert "benchmark/context.json" in prompt
    assert "Do not run commands" in prompt
    assert "one compact JSON object on one line" in prompt
    assert "values for .json artifact names must be json objects" in prompt.lower()
    assert "Do not JSON-encode an artifact object into a string" in prompt
    assert "codex_harness" not in prompt and "flywheel_harness" not in prompt


def test_executor_stages_receipt_bound_role_neutral_runtime_context(tmp_path, staged_source):
    adapter = ContextReadingAdapter()
    run = execute_cross_harness_manifest(
        _manifest(staged_source), _runtime(), {"codex_harness": adapter},
        artifact_root=tmp_path / "artifacts",
        source_root=staged_source, run_id="runtime-context", phase="admission-smoke",
        selectors=["agt-001"], roles=["codex_harness"], repetitions=1,
        source_commit="test-commit",
    )
    row = run["rows"][0]
    assert (row["primary_outcome"], row["oracle_state"], row["receipt_state"]) == ("completed", "pass", "verified")
    values = adapter.context["harness_values"]
    assert adapter.context["schema"] == "harness.cross-harness-runtime-context/v1"
    assert values["raw_prompt_sha256"] == row["raw_prompt_sha256"]
    assert values["tool_policy_sha256"] == row["tool_policy_sha256"]
    assert values["input_sha256s"] == row["input_sha256s"]
    receipt = json.loads(Path(row["receipt_path"]).read_text(encoding="utf-8"))
    assert "benchmark-context.json" in {item["name"] for item in receipt["receipt_subject"]["artifacts"]}


def test_runtime_context_name_is_reserved_from_provider_artifacts(tmp_path):
    with pytest.raises(ValueError, match="standard attempt filename"):
        materialize_response_envelope(
            '{"artifacts":{"benchmark-context.json":{}}}', ["benchmark-context.json"], tmp_path,
        )


def test_every_registered_checker_publishes_the_type_of_each_field_it_requires():
    """A checker states the fields it needs. It also enforces their types, and
    until now it kept those to itself.

    `index_fallback_integrity/v1` wants `failure_classes` as a sorted array of
    strings. A provider that answered with an array of objects, one per event,
    raised `failure_classes_type_invalid`, scored `malformed`, and produced no
    graded metrics at all, on work whose content was right. Nothing in the task
    prompt or in benchmark/context.json had said which shape to use. That scores
    shape-guessing rather than the capability, so the contract now travels with
    the field names, and a new checker cannot ship without one.
    """
    task_set = load_json(ROOT / "benchmarks" / "agentic-task-set-v1.json")
    published = task_set["oracle_contract"]["checkers"]
    assert set(published) == set(REGISTERED_CHECKERS), set(published) ^ set(REGISTERED_CHECKERS)
    for checker_id, block in published.items():
        contract = block.get("json_field_contract")
        assert isinstance(contract, dict), checker_id
        assert list(contract) == list(block["required_json_fields"]), checker_id
        assert all(isinstance(text, str) and text.strip() for text in contract.values()), checker_id


def test_the_staged_context_carries_the_type_of_every_field_it_requires(staged_source):
    """What the gate above proves about the task set has to reach the provider.

    The provider never reads the task set. It reads benchmark/context.json, so
    the types have to be in that document, beside the names they describe.
    """
    manifest = _manifest(staged_source)
    rows = {row["task_id"]: row for row in manifest["task_rows"]}
    scored = [row for row in rows.values() if (row.get("oracle") or {}).get("checker_id")]
    assert scored
    for row in scored:
        context = build_runtime_context(row, {"task_id": row["task_id"], "raw_prompt_sha256": row["raw_prompt_sha256"],
                                              "tool_policy_sha256": "b" * 64}, {})
        assert list(context["required_json_field_types"]) == context["required_json_fields"], row["task_id"]
    unscored = [row for row in rows.values() if not (row.get("oracle") or {}).get("checker_id")]
    context = build_runtime_context(unscored[0], {"task_id": unscored[0]["task_id"],
                                                  "raw_prompt_sha256": "a" * 64, "tool_policy_sha256": "b" * 64}, {})
    assert context["required_json_field_types"] == {}
