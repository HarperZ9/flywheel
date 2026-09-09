import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from harness.cross_harness_artifacts import canonical_sha256, snapshot_source_tree
from harness.cross_harness_cli import build_adapter_registry
from harness.cross_harness_executor import SHARED_TOOL_POLICY
from harness.cross_harness_types import AttemptRequest
from harness.adapter_runtime_matrix import build_matrix
import harness.cross_harness_adapters as adapters
from scripts.run_model_endpoint_profiles import build_report
from tests.adapter_runtime_fixtures import gate_fixture


NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
SCHEMA = {"type": "object", "required": ["artifacts"],
          "properties": {"artifacts": {"type": "object"}}}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _release_artifact(root: Path) -> None:
    release = root / "release" / "flywheel-local-coder-14b"
    release.mkdir(parents=True)
    (release / "telos-coder-14b-cpt2020-q4_k_m.gguf").write_bytes(b"gguf")


def _report(tmp_path: Path) -> dict:
    _release_artifact(tmp_path)
    return build_report(models=["14B"], base_root=tmp_path, serve_url="",
                        ollama_url="http://127.0.0.1:11434",
                        ollama_num_ctx=32768,
                        ollama_models={"14b": "flywheel-local-coder-14b"})


def _release_profile(report: dict) -> dict:
    return next(row for row in report["profiles"]
                if row["profile_id"] == "ollama-release-14b")


def _policy() -> dict:
    policy = dict(SHARED_TOOL_POLICY)
    policy.update({"max_steps": 1, "max_output_tokens": 64,
                   "structured_final_output": {
                       "enabled": True, "format_mode": "schema",
                       "schema": SCHEMA, "system": "Return only JSON.",
                       "max_output_tokens": 64, "context_max_bytes": 20000,
                       "retain_private_finalizer_payloads": True}})
    return policy


def _request(tmp_path: Path, profile: dict) -> AttemptRequest:
    policy = _policy()
    return AttemptRequest(
        "run", "local", "set", "task", "produce final", "a" * 64,
        "local_14b", "local_endpoint", "openai_compatible_local/v1",
        "flywheel-local-coder-14b", profile["model_ref"], tmp_path,
        snapshot_source_tree(tmp_path)["sha256"], {}, policy,
        canonical_sha256(policy), 1, "cold_declared", 120, tmp_path,
    )

def _contract(profile: dict) -> dict:
    return {"provider_roles": [{
        "provider_role": "local_14b",
        "harness_id": "local_endpoint",
        "model_id": "flywheel-local-coder-14b",
        "model_display_name": "flywheel-local-coder-14b",
        "requested_model_reference": profile["model_ref"],
        "adapter_state": "needs_endpoint_profile_and_gate",
        "allowed_modes": ["manifest_only", "focused_run_after_approval"],
        "required_receipts": [],
        "endpoint_selector": {
            "profile_id": profile["profile_id"],
            "backend": profile["backend"],
            "model_reference": profile["model_ref"],
            "release_asset_sha256": profile["release_asset_sha256"],
        },
    }]}

def _matrix(tmp_path: Path, report: dict, profile: dict) -> dict:
    profile_path = tmp_path / "profiles.json"
    profile_path.write_text(json.dumps(report), encoding="utf-8")
    gate = gate_fixture(profile, observed_at=NOW.isoformat().replace("+00:00", "Z"))
    return build_matrix(
        _contract(profile), contract_path="contract.json",
        contract_sha256="contract-hash", endpoint_profiles=report,
        endpoint_profiles_path=str(profile_path),
        endpoint_profiles_sha256=_sha(profile_path), endpoint_gate=gate,
        endpoint_gate_path="gate.json", endpoint_gate_sha256="gate-hash",
        expected_gate_run_id="gate-run", now=NOW,
    )


def test_ollama_profiles_declare_configured_schema_transport_without_probe(tmp_path):
    report = _report(tmp_path)

    serve = next(row for row in report["profiles"] if row["profile_id"] == "serve-14b")
    release = _release_profile(report)
    generic = next(row for row in report["profiles"] if row["profile_id"] == "ollama-14b")

    assert "structured_final_output" not in serve
    for profile in (generic, release):
        assert profile["structured_final_output"] == {
            "state": "supported",
            "transport": "ollama_chat_format_json_schema",
            "request_field": "format",
            "schema_limits": "basic_json_schema_only",
            "evidence": "configured_ollama_api_chat_format_json_schema",
        }
        assert profile["generate_url"].endswith("/api/chat")
        assert profile["live_probed"] is False


def test_runtime_matrix_preserves_selected_schema_capability(tmp_path):
    report = _report(tmp_path)
    profile = _release_profile(report)

    row = next(item for item in _matrix(tmp_path, report, profile)["runtime_rows"]
               if item["provider_role"] == "local_14b")

    assert row["focused_run_ready"] is True
    assert row["endpoint_profile_matches"][0]["structured_final_output"] == profile["structured_final_output"]


def test_profile_to_matrix_to_adapter_builds_native_schema_request(tmp_path, monkeypatch):
    report = _report(tmp_path)
    profile = _release_profile(report)
    matrix = _matrix(tmp_path, report, profile)
    requests = []

    def fake_local_http(method, url, body, timeout):
        decoded = json.loads(body.decode("utf-8"))
        requests.append({"method": method, "url": url, "body": decoded,
                         "timeout": timeout})
        return 200, {"model": decoded["model"], "done": True,
                     "done_reason": "stop",
                     "message": {"content": "candidate" if len(requests) == 1 else "final"}}

    monkeypatch.setattr(adapters, "_local_http", fake_local_http)

    adapter = build_adapter_registry(matrix, ["local_14b"])["local_14b"]
    result = adapter.execute(_request(tmp_path, profile))

    assert result.execution_state == "returned"
    assert result.output_text == "final"
    assert [request["url"] for request in requests] == [
        "http://127.0.0.1:11434/api/chat",
        "http://127.0.0.1:11434/api/chat",
    ]
    assert "format" not in requests[0]["body"]
    assert requests[1]["body"]["format"] == SCHEMA
    assert requests[1]["body"]["model"] == requests[0]["body"]["model"]
    assert requests[1]["body"]["stream"] == requests[0]["body"]["stream"]
    assert requests[1]["body"]["options"] == requests[0]["body"]["options"]
    event = next(item for item in result.tool_trace
                 if item.get("type") == "structured_finalization")
    assert event["state"] == "returned"
    assert event["evidence"]["request_field"] == "format"


def test_empty_schema_capability_refuses_before_transport(tmp_path, monkeypatch):
    report = _report(tmp_path)
    profile = _release_profile(report)
    profile.pop("structured_final_output", None)
    matrix = _matrix(tmp_path, report, profile)
    calls = []

    def fake_local_http(method, url, body, timeout):
        calls.append(json.loads(body.decode("utf-8")))
        return 200, {"model": calls[-1]["model"], "done": True,
                     "done_reason": "stop",
                     "message": {"content": "candidate"}}

    monkeypatch.setattr(adapters, "_local_http", fake_local_http)

    adapter = build_adapter_registry(matrix, ["local_14b"])["local_14b"]
    result = adapter.execute(_request(tmp_path, profile))

    assert result.output_text == ""
    assert len(calls) == 1
    event = next(item for item in result.tool_trace
                 if item.get("type") == "structured_finalization")
    assert event["state"] == "unsupported"
    assert event["evidence"] == {}
