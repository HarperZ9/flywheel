import copy
import json
from pathlib import Path

import pytest

from harness.adapter_runtime_matrix import DEFAULT_CONTRACT, build_matrix
from harness.cross_harness_adapters import DirectCodexAdapter, LocalRouterAdapter, ProcessOutcome
from harness.cross_harness_artifacts import canonical_sha256
from harness.cross_harness_executor import expand_attempt_rows
from harness.cross_harness_manifest import build_manifest, load_json
from harness.cross_harness_types import AttemptRequest


ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "benchmarks/cross-harness-adapter-contract-v2.json"


def task_set():
    return {"schema": "harness.agentic-task-set/v1", "task_set_id": "set", "tasks": [{
        "id": "contract-v2", "lane": "agentic", "difficulty": "focused",
        "prompt": "contract test", "required_inputs": [], "expected_artifacts": [],
        "scoring_focus": [], "must_not": [], "oracle": {},
    }]}


def contract():
    return load_json(V2)


def test_current_runtime_default_uses_v2_contract():
    assert Path(DEFAULT_CONTRACT).name == V2.name


@pytest.mark.parametrize(("mutate", "message"), [
    (lambda value: value["provider_roles"][0].pop("model_id"), "model_id"),
    (lambda value: value["provider_roles"][0].pop("model_display_name"), "model_display_name"),
    (lambda value: value["provider_roles"][0].pop("requested_model_reference"), "requested_model_reference"),
    (lambda value: value["provider_roles"][0].update(target_model="legacy"), "target_model"),
    (lambda value: value["provider_roles"][4]["endpoint_selector"].pop("profile_id"), "profile_id"),
    (lambda value: value["provider_roles"][4]["endpoint_selector"].pop("backend"), "backend"),
    (lambda value: value["provider_roles"][4]["endpoint_selector"].pop("model_reference"), "model_reference"),
    (lambda value: value["provider_roles"][4]["endpoint_selector"].pop("release_asset_sha256"), "release_asset_sha256"),
])
def test_v2_contract_rejects_malformed_identity_and_local_selector(mutate, message):
    value = copy.deepcopy(contract())
    mutate(value)

    with pytest.raises(ValueError, match=message):
        build_manifest(task_set(), value, provider_roles=["codex_harness"])


def test_v2_runtime_and_execution_project_exact_local_identity():
    value = contract()
    profile = {
        "profile_id": "ollama-release-14b", "backend": "ollama",
        "model_ref": "ollama:flywheel-local-coder-14b", "root_exists": True,
        "supports_agentic_workflow": True,
    }
    matrix = build_matrix(value, contract_path="contract.json", contract_sha256="hash",
                          endpoint_profiles={"profiles": [profile]})
    runtime = next(row for row in matrix["runtime_rows"] if row["provider_role"] == "local_14b")
    manifest = build_manifest(task_set(), value, provider_roles=["local_14b"])
    plan = expand_attempt_rows(manifest, {"runtime_rows": [runtime]}, artifact_root=ROOT / "tmp",
                               run_id="run", phase="local", selectors=["contract-v2"],
                               roles=["local_14b"], repetitions=1)[0]

    assert runtime["model_id"] == "flywheel-local-coder-14b"
    assert runtime["requested_model_reference"] == "ollama:flywheel-local-coder-14b"
    assert runtime["endpoint_profile_matches"][0]["profile_id"] == "ollama-release-14b"
    assert plan["model_id"] == "flywheel-local-coder-14b"
    assert plan["requested_model_reference"] == "ollama:flywheel-local-coder-14b"


@pytest.mark.parametrize(("role", "model_id", "model_ref", "profile_id", "profile_model"), [
    ("local_14b", "flywheel-local-coder-14b", "ollama:flywheel-local-coder-14b", "ollama-release-14b", "14B"),
    ("local_32b", "flywheel-local-coder-32b", "ollama:flywheel-local-coder-32b", "ollama-release-32b", "32B"),
])
def test_ready_local_v2_request_binds_profile_reference_not_stable_identity(tmp_path, role, model_id, model_ref, profile_id, profile_model):
    raw_profile = {"profile_id": profile_id, "backend": "ollama", "model": profile_model,
                   "model_ref": model_ref, "endpoint_url": "http://127.0.0.1:11434",
                   "supports_agentic_workflow": True, "root_exists": True}
    request = AttemptRequest("run", "local", "set", "task", "prompt", "a" * 64, role,
                             "local_endpoint", "openai_compatible_local/v1", model_id, model_ref,
                             tmp_path, "b" * 64, {}, {}, "c" * 64, 1, "cold_declared", 3, tmp_path)

    availability = LocalRouterAdapter(role, {**raw_profile, "profile_sha256": canonical_sha256(raw_profile)}).availability(request)

    assert model_id != profile_model
    assert availability.available is True


def test_requested_reference_drives_transport_while_stable_identity_stays_observed(tmp_path):
    seen = {}
    request = AttemptRequest("run", "spark", "set", "task", "prompt", "a" * 64, "codex_harness",
                             "codex", "codex_cli_json/v1", "stable-id", "request-ref", tmp_path,
                             "b" * 64, {}, {}, "c" * 64, 1, "cold_declared", 3, tmp_path)
    process = ProcessOutcome(0, json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}), "", 1, False)
    def runner(argv, **_):
        seen["argv"] = argv
        return process

    result = DirectCodexAdapter(runner=runner, executable_resolver=lambda: "codex.cmd").execute(request)

    assert seen["argv"][3] == "request-ref"
    assert result.model_observed == "stable-id"
