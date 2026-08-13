import hashlib
import json
import pytest

from harness.cross_harness_adapters import DirectCodexAdapter, FlywheelRouterAdapter, LocalRouterAdapter, ProcessOutcome
from harness.cross_harness_artifacts import canonical_sha256
from harness.cross_harness_executor import SHARED_TOOL_POLICY, execute_cross_harness_manifest
from harness.local_agent import MalformedBackendOutput, OllamaBackend, ServeBackend
from harness.cross_harness_types import AdapterResult, AvailabilityResult, EnforcementResult


class UnattestedAdapter:
    role = "local_14b"
    adapter_id = "local_14b/v1"

    def enforcement(self, request):
        description = {"boundary": "fixture"}
        return EnforcementResult(description, canonical_sha256(description), "fixture", "non_equivalent")

    def availability(self, request):
        return AvailabilityResult(True, "", "ready", {})

    def execute(self, request):
        return AdapterResult("returned", '{"artifacts":{}}', [], 1, "untrusted-model", "unsupported", "", "", {}, {}, [], [],
                             model_observation_basis="unknown")


def test_returned_unattested_model_is_empty_and_records_request_limitation(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    prompt = "prompt"
    manifest = {"task_set_id": "set", "task_rows": [{"task_id": "task", "raw_prompt": prompt,
        "raw_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "input_sha256s": {}, "required_inputs": [],
        "expected_artifacts": [], "oracle": {}}], "provider_specs": [{"provider_role": "local_14b",
        "harness_id": "local", "adapter_id": "local_14b/v1", "model_id": "stable-model",
        "model_display_name": "Stable model", "requested_model_reference": "request-model"}]}
    runtime = {"runtime_rows": [{"provider_role": "local_14b", "focused_run_ready": True, "blocking_gates": []}]}

    row = execute_cross_harness_manifest(manifest, runtime, {"local_14b": UnattestedAdapter()}, artifact_root=tmp_path / "artifacts",
        source_root=source, run_id="run", phase="local", selectors=["task"], roles=["local_14b"], repetitions=1)["rows"][0]

    assert row["requested_model_reference"] == "request-model"
    assert (row["model_observed"], row["model_observation_basis"]) == ("", "unknown")
    assert "provider_request_accepted_not_model_attested" in row["limitations"]


def _request(tmp_path, role="codex_harness", adapter="codex_cli_json/v1"):
    from harness.cross_harness_types import AttemptRequest
    return AttemptRequest("run", "spark", "set", "task", "prompt", "a" * 64, role, "harness", adapter,
                          "stable", "requested", tmp_path, "b" * 64, {}, {}, "c" * 64, 1, "cold", 3, tmp_path)


def test_direct_and_flywheel_only_accept_explicit_bounded_model_attestation(tmp_path):
    events = [
        {"type": "item.completed", "item": {"type": "agent_message", "text": "I am spoofed"}},
        {"type": "turn.completed", "model": "attested-model"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}},
    ]
    process = ProcessOutcome(0, "\n".join(json.dumps(item) for item in events), "", 1, False)
    direct = DirectCodexAdapter(runner=lambda *_, **__: process, executable_resolver=lambda: "codex.cmd").execute(_request(tmp_path))
    flywheel = FlywheelRouterAdapter(runner=lambda *_, **__: process, executable_resolver=lambda: "codex.cmd").execute(
        _request(tmp_path, "flywheel_harness", "flywheel_router/v1"))

    assert (direct.model_observed, direct.model_observation_basis) == ("attested-model", "structured_provider_event")
    assert (flywheel.model_observed, flywheel.model_observation_basis) == ("attested-model", "structured_provider_event")


def test_direct_and_flywheel_do_not_treat_final_prose_or_request_as_observation(tmp_path):
    event = {"type": "item.completed", "item": {"type": "agent_message", "text": "requested is the model"}}
    process = ProcessOutcome(0, json.dumps(event), "", 1, False)
    direct = DirectCodexAdapter(runner=lambda *_, **__: process, executable_resolver=lambda: "codex.cmd").execute(_request(tmp_path))
    flywheel = FlywheelRouterAdapter(runner=lambda *_, **__: process, executable_resolver=lambda: "codex.cmd").execute(
        _request(tmp_path, "flywheel_harness", "flywheel_router/v1"))

    assert (direct.model_observed, direct.model_observation_basis) == ("", "unknown")
    assert (flywheel.model_observed, flywheel.model_observation_basis) == ("", "unknown")


def test_local_observation_comes_from_structured_response_not_requested_reference(tmp_path):
    profile = {"profile_id": "local", "backend": "serve", "model": "14B", "model_ref": "requested",
               "endpoint_url": "http://127.0.0.1:8765", "supports_agentic_workflow": True, "root_exists": True}
    profile["profile_sha256"] = canonical_sha256(profile)
    backend = type("Backend", (), {"chat": lambda *_args, **_kwargs: {"text": "ok", "model_ref": "response-model", "seed": 0}})()
    result = LocalRouterAdapter("local_14b", profile, backend_factory=lambda *_: backend).execute(
        _request(tmp_path, "local_14b", "openai_compatible_local/v1"))

    assert (result.model_observed, result.model_observation_basis, result.failure_class) == ("response-model", "structured_provider_response", "observed_model_drift")


@pytest.mark.parametrize(("requested", "native"), [
    ("ollama:qwen:14b", "qwen:14b"), ("qwen:14b", "qwen:14b"),
    ("ollama:ollama:qwen:14b", "ollama:qwen:14b"), ("other:qwen", "other:qwen"),
])
def test_ollama_backend_removes_exactly_one_receipt_prefix_and_validates_response(requested, native):
    seen = {}
    def transport(_method, _url, body, _timeout):
        seen.update(json.loads(body)); return 200, {"model": native, "message": {"content": "ok"}}
    response = OllamaBackend(model=requested, transport=transport).chat([], system="", max_tokens=1, temperature=0, seed=0)
    assert seen["model"] == native
    assert response["model_ref"] == f"ollama:{native}"


@pytest.mark.parametrize("observed", [None, "", "served"])
def test_ollama_backend_types_missing_or_mismatched_response_model_as_malformed(observed):
    response = {"message": {"content": "ok"}}
    if observed is not None: response["model"] = observed
    backend = OllamaBackend(model="ollama:requested", transport=lambda *_: (200, response))
    with pytest.raises(MalformedBackendOutput):
        backend.chat([], system="", max_tokens=1, temperature=0, seed=0)


def test_local_adapter_preserves_ollama_response_model_violation_as_typed_malformed(tmp_path):
    profile = {"profile_id": "local", "backend": "ollama", "model": "14B", "model_ref": "requested",
               "endpoint_url": "http://127.0.0.1:11434", "supports_agentic_workflow": True, "root_exists": True}
    profile["profile_sha256"] = canonical_sha256(profile)
    backend = OllamaBackend(model="requested", transport=lambda *_: (200, {"message": {"content": "ok"}}))
    result = LocalRouterAdapter("local_14b", profile, backend_factory=lambda *_: backend).execute(
        _request(tmp_path, "local_14b", "openai_compatible_local/v1"))
    assert (result.execution_state, result.failure_class) == ("malformed", "malformed_provider_output")


def test_serve_without_response_identity_stays_unknown_and_limits_executor(tmp_path):
    profile = {"profile_id": "local", "backend": "serve", "model": "14B", "model_ref": "requested",
               "endpoint_url": "http://127.0.0.1:8765", "supports_agentic_workflow": True, "root_exists": True}
    profile["profile_sha256"] = canonical_sha256(profile)
    backend = ServeBackend(transport=lambda *_: (200, {"text": '{"artifacts":{}}'}))
    adapter = LocalRouterAdapter("local_14b", profile, backend_factory=lambda *_: backend)
    result = adapter.execute(_request(tmp_path, "local_14b", "openai_compatible_local/v1"))
    source = tmp_path / "source"; source.mkdir()
    manifest = {"task_set_id": "set", "task_rows": [{"task_id": "task", "raw_prompt": "prompt", "raw_prompt_sha256": hashlib.sha256(b"prompt").hexdigest(), "input_sha256s": {}, "required_inputs": [], "expected_artifacts": [], "oracle": {}}], "provider_specs": [{"provider_role": "local_14b", "harness_id": "local", "adapter_id": "openai_compatible_local/v1", "model_id": "stable", "model_display_name": "Stable", "requested_model_reference": "requested"}]}
    runtime = {"runtime_rows": [{"provider_role": "local_14b", "focused_run_ready": True, "blocking_gates": []}]}
    row = execute_cross_harness_manifest(manifest, runtime, {"local_14b": adapter}, artifact_root=tmp_path / "artifacts", source_root=source, run_id="run", phase="local", selectors=["task"], roles=["local_14b"], repetitions=1)["rows"][0]

    assert (result.model_observed, result.model_observation_basis) == ("", "unknown")
    assert "provider_request_accepted_not_model_attested" in row["limitations"]
