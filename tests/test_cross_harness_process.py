import hashlib, json, pathlib, shutil, subprocess, sys, tempfile
import pytest
from harness.cross_harness_adapters import (CodexCliProposer, DirectCodexAdapter,
    FlywheelRouterAdapter, LocalRouterAdapter, ProcessOutcome)
from harness.cross_harness_artifacts import canonical_sha256
from harness.cross_harness_executor import SHARED_TOOL_POLICY, execute_cross_harness_manifest
from harness.cross_harness_process import run_process
from harness.cross_harness_types import AttemptRequest


def _profile(url):
    row = {"profile_id": "local", "backend": "serve", "model": "14B", "model_ref": "local:14b", "endpoint_url": url,
           "supports_agentic_workflow": True, "root_exists": True}
    return {**row, "profile_sha256": canonical_sha256(row)}


def _request(tmp_path):
    return AttemptRequest("run", "local", "set", "agt-001-task", "prompt", "a" * 64, "local_14b", "local", "openai_compatible_local/v1",
        "flywheel-local-coder-14b", "local:14b", tmp_path, "b" * 64, {}, SHARED_TOOL_POLICY, "c" * 64, 1, "cold_declared", 2, tmp_path)


def _spark_request(tmp_path, role="codex_harness", adapter="codex_cli_json/v1"):
    return AttemptRequest("run", "spark", "set", "agt-001-task", "prompt", "a" * 64, role, role.split("_")[0], adapter,
        "gpt-5.3-codex-spark", "gpt-5.3-codex-spark", tmp_path, "b" * 64, {}, SHARED_TOOL_POLICY, "c" * 64, 1, "cold_declared", 2, tmp_path)


def _execute_spark_rows(tmp_path, process, adapters):
    source = tmp_path / "source"; source.mkdir(); prompt = "prompt"
    task = {"task_id": "agt-001-task", "raw_prompt": prompt, "raw_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "input_sha256s": {}, "required_inputs": [], "expected_artifacts": [], "oracle": {}}
    roles = list(adapters)
    manifest = {"task_set_id": "set", "task_rows": [task], "provider_specs": [{"provider_role": role,
        "harness_id": role.split("_")[0], "adapter_id": "codex_cli_json/v1" if role == "codex_harness" else "flywheel_router/v1",
        "model_id": "gpt-5.3-codex-spark", "model_display_name": "GPT-5.3-Codex-Spark", "requested_model_reference": "gpt-5.3-codex-spark"} for role in roles]}
    runtime = {"runtime_rows": [{"provider_role": role, "focused_run_ready": True, "blocking_gates": []} for role in roles]}
    return execute_cross_harness_manifest(manifest, runtime, adapters, artifact_root=tmp_path / "artifacts", source_root=source,
        run_id="run", phase="spark", selectors=["agt-001"], roles=roles, repetitions=1)["rows"]


@pytest.mark.parametrize(("stdout", "expected"), [
    ("", None),
    (json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": 7}}), None),
    ("\n".join((json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "valid"}}),
                 json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": []}}))), None),
    ("\n".join((json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "first"}}),
                 json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "last"}}))), "last"),
])
def test_direct_codex_final_message_semantics(stdout, expected, tmp_path):
    process = ProcessOutcome(0, stdout, "", 1, False)
    result = DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd").execute(_spark_request(tmp_path))
    assert (result.output_text == expected) if expected else (result.execution_state, result.failure_class) == ("malformed", "malformed_jsonl")


@pytest.mark.parametrize("stdout", ["", json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": []}})])
def test_invalid_final_message_beats_nonzero_for_direct_and_inner(stdout, tmp_path):
    process = ProcessOutcome(7, stdout, "provider failed", 1, False)
    direct = DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd").execute(_spark_request(tmp_path))
    proposer = CodexCliProposer("5.3-Codex-Spark", workspace=tmp_path, artifact_dir=tmp_path,
        timeout_seconds=2, runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd")
    inner = FlywheelRouterAdapter(proposer=proposer).execute(_spark_request(tmp_path, "flywheel_harness", "flywheel_router/v1"))
    assert (direct.execution_state, direct.failure_class) == ("malformed", "malformed_jsonl")
    assert (inner.execution_state, inner.failure_class) == ("malformed", "malformed_provider_output")


def test_structured_model_rejection_beats_missing_final_message_for_direct_and_inner(tmp_path):
    provider_error = {"type": "error", "status": 400, "error": {
        "type": "invalid_request_error",
        "message": "The '5.3-Codex-Spark' model is not supported when using Codex with a ChatGPT account.",
        "authorization": "opaque-value-that-must-not-escape",
    }}
    stdout = "\n".join((
        json.dumps({"type": "thread.started", "thread_id": "fixture-thread"}),
        json.dumps({"type": "error", "message": json.dumps(provider_error)}),
        json.dumps({"type": "turn.failed", "error": {"message": json.dumps(provider_error)}}),
    ))
    process = ProcessOutcome(1, stdout, "", 1, False)
    direct = DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd").execute(_spark_request(tmp_path))
    proposer = CodexCliProposer("5.3-Codex-Spark", workspace=tmp_path, artifact_dir=tmp_path,
        timeout_seconds=2, runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd")
    inner = FlywheelRouterAdapter(proposer=proposer).execute(_spark_request(tmp_path, "flywheel_harness", "flywheel_router/v1"))
    for result in (direct, inner):
        assert (result.execution_state, result.failure_class) == ("internal_error", "provider_model_unsupported")
        detail = json.loads(result.failure_detail)
        assert detail == {"provider_error_type": "invalid_request_error", "status": 400}
        assert any(event.get("type") == "turn.failed" for event in result.tool_trace)
    adapters = {"codex_harness": DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd"),
        "flywheel_harness": FlywheelRouterAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd")}
    for row in _execute_spark_rows(tmp_path, process, adapters):
        assert (row["launched"], row["admitted"], row["blocked"], row["failure_class"]) == (True, True, False, "provider_model_unsupported")
        assert (row["execution_state"], row["receipt_state"], row["model_observed"]) == ("internal_error", "verified", "gpt-5.3-codex-spark")
        trace = json.loads(pathlib.Path(row["tool_trace_path"]).read_text())
        assert any(event.get("type") == "turn.failed" for event in trace)
        assert "opaque-value-that-must-not-escape" not in repr(trace)


def test_provider_rejection_detail_excludes_provider_message_and_secrets(tmp_path):
    secret = "sk-proj-abcdefghijklmnopqrstuvwxyz"
    error = {"type": "error", "status": 400, "error": {"type": "invalid_request_error",
        "message": f"The model is not supported for this account; Authorization: Bearer {secret}"}}
    process = ProcessOutcome(1, json.dumps({"type": "turn.failed", "error": {"message": json.dumps(error)}}), "", 1, False)
    result = DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd").execute(_spark_request(tmp_path))
    assert json.loads(result.failure_detail) == {"provider_error_type": "invalid_request_error", "status": 400}
    assert secret not in result.failure_detail and secret not in repr(result.tool_trace)


@pytest.mark.parametrize(("status", "error_type"), [(429, "rate_limit_error"), (503, "server_error")])
def test_other_structured_terminal_provider_failures_use_generic_typed_class(status, error_type, tmp_path):
    event = {"type": "error", "status": status, "error": {"type": error_type, "message": "provider rejected request"}}
    final = {"type": "item.completed", "item": {"type": "agent_message", "text": "must not outrank terminal error"}}
    process = ProcessOutcome(0, "\n".join((json.dumps(event), json.dumps(final))), "", 1, False)
    result = DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd").execute(_spark_request(tmp_path))
    assert (result.execution_state, result.failure_class, result.output_text) == ("internal_error", "provider_rejected", "")
    assert json.loads(result.failure_detail) == {"provider_error_type": error_type, "status": status}


def test_generic_provider_rejection_needs_no_message_and_feature_error_is_not_model_error(tmp_path):
    events = [
        {"type": "error", "status": 503, "error": {"type": "server_error"}},
        {"type": "error", "status": 400, "error": {"type": "invalid_request_error",
            "message": "The model rejected this request because response_format is not supported."}},
    ]
    for event in events:
        process = ProcessOutcome(1, json.dumps(event), "", 1, False)
        result = DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd").execute(_spark_request(tmp_path))
        assert (result.execution_state, result.failure_class) == ("internal_error", "provider_rejected")


def test_nested_structured_turn_failure_is_typed_for_direct_and_inner(tmp_path):
    event = {"type": "turn.failed", "error": {"status": 503, "error": {"type": "server_error"}}}
    final = {"type": "item.completed", "item": {"type": "agent_message", "text": "must not hide terminal failure"}}
    process = ProcessOutcome(0, "\n".join((json.dumps(event), json.dumps(final))), "", 1, False)
    direct = DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd").execute(_spark_request(tmp_path))
    proposer = CodexCliProposer("5.3-Codex-Spark", workspace=tmp_path, artifact_dir=tmp_path,
        timeout_seconds=2, runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd")
    inner = FlywheelRouterAdapter(proposer=proposer).execute(_spark_request(tmp_path, "flywheel_harness", "flywheel_router/v1"))
    assert {(result.execution_state, result.failure_class) for result in (direct, inner)} == {("internal_error", "provider_rejected")}
    adapters = {"codex_harness": DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd"),
        "flywheel_harness": FlywheelRouterAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd")}
    for row in _execute_spark_rows(tmp_path, process, adapters):
        assert (row["execution_state"], row["failure_class"], row["receipt_state"]) == ("internal_error", "provider_rejected", "verified")


def test_malformed_jsonl_outranks_a_valid_provider_rejection(tmp_path):
    error = {"type": "error", "status": 400, "error": {"type": "invalid_request_error",
        "message": "The '5.3-Codex-Spark' model is not supported when using Codex with a ChatGPT account."}}
    process = ProcessOutcome(1, json.dumps(error) + "\nnot-json", "", 1, False)
    result = DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd").execute(_spark_request(tmp_path))
    assert (result.execution_state, result.failure_class) == ("malformed", "malformed_jsonl")


@pytest.mark.parametrize("event", [
    {"type": "error", "message": '{"status":400,"error":{"type":"invalid_request_error","type":"forged","message":"model is not supported"}}'},
    {"type": "error", "message": '{"status":400,"error":{"type":"invalid_request_error","message":"model is not supported"},"value":NaN}'},
    {"type": "error", "message": json.dumps({"status": 400, "error": {"type": "invalid_request_error", "message": "model is not supported"},
        "nested": [[[[[[[[[[[[[[[[["too deep"]]]]]]]]]]]]]]]]]})},
    {"type": "error", "message": json.dumps({"status": 400, "error": {"type": "invalid_request_error",
        "message": "model is not supported " + "x" * 5000}})},
    {"type": "error", "message": r'{"status":400,"error":{"type":"server_error","message":"\ud800"}}'},
], ids=["duplicate", "nonfinite", "depth", "message_limit", "surrogate"])
def test_malformed_nested_terminal_errors_outrank_final_message(event, tmp_path):
    final = {"type": "item.completed", "item": {"type": "agent_message", "text": "answer"}}
    process = ProcessOutcome(0, "\n".join((json.dumps(event), json.dumps(final))), "", 1, False)
    direct = DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd").execute(_spark_request(tmp_path))
    proposer = CodexCliProposer("5.3-Codex-Spark", workspace=tmp_path, artifact_dir=tmp_path,
        timeout_seconds=2, runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd")
    inner = FlywheelRouterAdapter(proposer=proposer).execute(_spark_request(tmp_path, "flywheel_harness", "flywheel_router/v1"))
    assert (direct.execution_state, direct.failure_class) == ("malformed", "malformed_jsonl")
    assert (inner.execution_state, inner.failure_class) == ("malformed", "malformed_provider_output")
    if "\\ud800" in str(event):
        adapters = {"codex_harness": DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd"),
            "flywheel_harness": FlywheelRouterAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd")}
        for row in _execute_spark_rows(tmp_path, process, adapters):
            assert (row["execution_state"], row["receipt_state"], row["model_observed"]) == ("malformed", "verified", "gpt-5.3-codex-spark")
            assert row["failure_class"] in {"malformed_jsonl", "malformed_provider_output"}
            trace = pathlib.Path(row["tool_trace_path"]).read_text()
            assert "\\ud800" not in trace and '"malformed_provider_message":true' in trace


def test_nonterminal_nested_error_metadata_does_not_override_final_message(tmp_path):
    event = {"type": "item.completed", "item": {"type": "error", "message": json.dumps({"status": 400,
        "error": {"type": "invalid_request_error", "message": "model is not supported"}})}}
    final = {"type": "item.completed", "item": {"type": "agent_message", "text": "answer"}}
    process = ProcessOutcome(0, "\n".join((json.dumps(event), json.dumps(final))), "", 1, False)
    result = DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd").execute(_spark_request(tmp_path))
    assert (result.execution_state, result.output_text, result.failure_class) == ("returned", "answer", "")


@pytest.mark.parametrize("payload", [
    b'', b'{"text":"ok","text":"forged"}', b'{"text":NaN}', b'[]', b'{"text":"' + b'x' * 20000 + b'"}',
    b'{"text":' + b'[' * 5000 + b'0' + b']' * 5000 + b'}', b'x' * ((1 << 20) + 1),
], ids=["empty", "duplicate", "nonfinite", "type", "field", "depth", "total"])
def test_local_http_uses_the_provider_json_boundary(payload, monkeypatch, tmp_path):
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, count): return payload[:count]
    class Opener:
        def open(self, *args, **kwargs): return Response()
    monkeypatch.setattr("harness.cross_harness_adapters.urllib.request.build_opener", lambda *a: Opener())
    result = LocalRouterAdapter("local_14b", _profile("http://127.0.0.1:8765")).execute(_request(tmp_path))
    assert result.execution_state == "malformed" and result.failure_class == "malformed_provider_output"


def test_malformed_local_http_attempt_still_seals_receipt(monkeypatch, tmp_path):
    malformed = __import__("harness.cross_harness_adapters", fromlist=["MalformedProviderOutput"]).MalformedProviderOutput
    monkeypatch.setattr("harness.cross_harness_adapters._local_http", lambda *a: (_ for _ in ()).throw(malformed("bad local JSON")))
    source = tmp_path / "source"; source.mkdir(); prompt = "prompt"
    task = {"task_id": "agt-001-task", "raw_prompt": prompt, "raw_prompt_sha256": __import__("hashlib").sha256(prompt.encode()).hexdigest(), "input_sha256s": {}, "required_inputs": [], "expected_artifacts": [], "oracle": {}}
    manifest = {"task_set_id": "set", "task_rows": [task], "provider_specs": [{"provider_role": "local_14b", "harness_id": "local", "adapter_id": "openai_compatible_local/v1", "model_id": "flywheel-local-coder-14b", "model_display_name": "Local 14B", "requested_model_reference": "local:14b"}]}
    runtime = {"runtime_rows": [{"provider_role": "local_14b", "focused_run_ready": True, "blocking_gates": []}]}
    run = execute_cross_harness_manifest(manifest, runtime, {"local_14b": LocalRouterAdapter("local_14b", _profile("http://127.0.0.1:8765"))}, artifact_root=tmp_path / "artifacts", source_root=source, run_id="run", phase="local", selectors=["agt-001"], roles=["local_14b"], repetitions=1)
    assert (run["rows"][0]["execution_state"], run["rows"][0]["receipt_state"]) == ("malformed", "verified")


@pytest.mark.skipif(sys.platform != "win32" or shutil.which("wsl.exe") is None, reason="WSL integration unavailable")
@pytest.mark.parametrize("mode", ["normal", "double-fork", "self-migrate"])
def test_wsl_provider_execution_fails_closed_before_launch(mode):
    root = pathlib.Path(__file__).resolve().parents[1]
    linux_root = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(root)], capture_output=True, text=True, check=True).stdout.strip()
    script = r'''
import pathlib,sys,tempfile
sys.path.insert(0, sys.argv[1]); from harness.cross_harness_process import run_process
with tempfile.TemporaryDirectory() as d:
 p=pathlib.Path(d); marker=p/'launched'; code="import pathlib,sys;pathlib.Path(sys.argv[1]).write_text('bad')"
 try: run_process([sys.executable,'-c',code,str(marker)],cwd=p,stdin_text='',timeout_seconds=2)
 except OSError as exc: assert 'Linux provider containment unavailable' in str(exc)
 else: raise AssertionError('provider launched')
 assert not marker.exists()
'''
    completed = subprocess.run(["wsl.exe", "-e", "python3", "-", linux_root, mode], input=script, text=True, capture_output=True, timeout=15)
    assert completed.returncode == 0, completed.stderr


def test_linux_containment_unavailable_fails_before_launch(tmp_path, monkeypatch):
    import harness.cross_harness_process as process
    monkeypatch.setattr(process.sys, "platform", "linux"); marker = tmp_path / "launched"
    with pytest.raises(OSError, match="Linux provider containment unavailable"):
        process.run_process([sys.executable, "-c", f"open({str(marker)!r},'w').write('bad')"], cwd=tmp_path, stdin_text="", timeout_seconds=1)
    assert not marker.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows provider boundary")
def test_real_provider_receives_no_output_path_or_stage_directory(tmp_path):
    event = {"type": "item.completed", "item": {"type": "agent_message", "text": "answer"}}
    code = f"import json,pathlib,sys;assert len(sys.argv)==1;assert not list(pathlib.Path.cwd().glob('.cross-harness-stage-*'));print(json.dumps({event!r}))"
    result = run_process([sys.executable, "-c", code], cwd=tmp_path, stdin_text="", timeout_seconds=2)
    assert result.returncode == 0 and json.loads(result.stdout)["item"]["text"] == "answer"
    assert not list(tmp_path.glob(".cross-harness-stage-*"))
