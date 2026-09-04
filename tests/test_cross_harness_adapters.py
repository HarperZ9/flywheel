import json, pytest, sys
from types import SimpleNamespace
import harness.cross_harness_adapters as adapters_module
from harness.cross_harness_adapters import (CodexCliProposer, DirectCodexAdapter, FlywheelRouterAdapter,
    LocalRouterAdapter, ProcessOutcome, _resolve_codex, _run_process)
from harness.cross_harness_artifacts import canonical_sha256
from harness.cross_harness_cli import _csv, _exit
from harness.cross_harness_executor import SHARED_TOOL_POLICY, execute_cross_harness_manifest
from harness.cross_harness_types import AttemptRequest
from harness.proposer import StubProposer
def request(tmp_path, role="codex_harness", adapter="codex_cli_json/v1", model="gpt-5.3-codex-spark", requested=None):
    return AttemptRequest("run", "spark", "set", "agt-001-full", "do the task", "a" * 64, role, role.split("_")[0], adapter, model, requested or model, tmp_path, "b" * 64, {}, SHARED_TOOL_POLICY, "c" * 64, 1, "cold_declared", 3, tmp_path)
def outcome(stdout="", output="answer", *, rc=0, stderr="", elapsed=7):
    if output is not None:
        final = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": output}})
        stdout = "\n".join(filter(None, (stdout, final)))
    return ProcessOutcome(rc, stdout, stderr, elapsed, False)
def test_empty_cli_selections_are_rejected():
    with pytest.raises(ValueError, match="selection must not be empty"): _csv("")
    assert _exit([], True) == 1
def test_resolve_codex_rejects_extensionless_windows_wrapper_without_exe(monkeypatch):
    calls = []
    on_path = {"codex.exe": None, "codex": "C:/npm/codex"}
    monkeypatch.setattr(adapters_module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(adapters_module.shutil, "which", lambda name: calls.append(name) or on_path.get(name))
    assert _resolve_codex() == ""
    assert calls == ["codex.exe"]
def test_resolve_codex_accepts_native_windows_exe(monkeypatch):
    monkeypatch.setattr(adapters_module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(adapters_module.shutil, "which",
                        lambda name: "C:/npm/vendor/codex.exe" if name == "codex.exe" else None)
    assert _resolve_codex() == "C:/npm/vendor/codex.exe"
def test_resolve_codex_keeps_extensionless_posix_executable(monkeypatch):
    monkeypatch.setattr(adapters_module, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(adapters_module.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    assert _resolve_codex() == "/usr/local/bin/codex"
def test_direct_codex_uses_stdin_hardened_read_only_argv_and_captures_jsonl(tmp_path):
    seen = {}
    trace = '\n'.join([
        json.dumps({"type": "item.completed", "item": {"type": "file_read", "path": "x"}}),
        json.dumps({"type": "item.completed", "item": {"type": "command_execution", "command": "dir"}}),
    ])
    def runner(argv, **kw): seen.update(argv=argv, **kw); return outcome(trace)
    identity = {"raw_prompt_sha256": "a" * 64, "input_sha256s": {}, "oracle_spec_sha256": "d" * 64}
    adapter = DirectCodexAdapter(runner=runner, executable_resolver=lambda: "C:/bin/codex.cmd", task_identity_by_id={"agt-001-full": identity})
    result = adapter.execute(request(tmp_path))
    assert seen["argv"] == [
        "C:/bin/codex.cmd", "exec", "--model", "gpt-5.3-codex-spark", "--sandbox", "read-only", "--cd", str(tmp_path),
        "--ephemeral", "--ignore-user-config", "--skip-git-repo-check", "--json", "-",
    ]
    assert seen["stdin_text"] == "do the task" and seen["cwd"] == tmp_path
    assert result.execution_state == "returned" and result.output_text == "answer" and len(result.tool_trace) == 4
    assert result.usage == {} and result.resource_observation == {}
    assert result.randomness_control == "unsupported"
    assert result.observed_capabilities == ["read", "shell"]
    assert result.policy_violations == ["exec_not_allowed"]
    available = adapter.availability(request(tmp_path))
    assert available.available and available.evidence["oracle_spec_sha256"] == "d" * 64
def test_direct_codex_marks_any_nonblank_malformed_jsonl_and_sanitizes_secrets(tmp_path):
    secret = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature"
    api_key = "sk-" + "proj-" + "abcdefghijklmnopqrstuvwxyz"
    stdout = "not-json\n" + json.dumps({"headers": [{"name": "Authorization", "value": "Bearer hide-me"}], "jwt": secret})
    adapter = DirectCodexAdapter(runner=lambda *a, **k: outcome(stdout, secret + " " + api_key), executable_resolver=lambda: "codex.cmd")
    result = adapter.execute(request(tmp_path))
    assert result.execution_state == "malformed" and result.failure_class == "malformed_jsonl"
    assert "hide-me" not in repr(result.tool_trace) and secret not in result.output_text and api_key not in result.output_text
def test_direct_codex_audits_mcp_and_shell_write_attempts(tmp_path):
    stdout = '\n'.join((json.dumps({"type": "mcp_tool_call", "name": "lookup"}),
                        json.dumps({"type": "command_execution", "command": "echo bad > x.txt"})))
    adapter = DirectCodexAdapter(runner=lambda *a, **k: outcome(stdout), executable_resolver=lambda: "codex.cmd")
    result = adapter.execute(request(tmp_path))
    assert result.observed_capabilities == ["shell", "mcp", "write"]
    assert result.policy_violations == ["exec_not_allowed", "mcp_not_allowed", "write_not_allowed"]
@pytest.mark.parametrize("event", [
    {"type": "file_change", "changes": [{"path": "x", "kind": "update"}]}, {"type": "command_execution", "command": "echo bad>x"},
    {"type": "command_execution", "command": "tee x"}, {"type": "command_execution", "command": "touch x"},
    {"type": "command_execution", "command": "mkdir x"}, {"type": "command_execution", "command": "Write-Output bad 2>x"},
])
def test_audit_classifies_native_and_shell_writes(event, tmp_path):
    result = DirectCodexAdapter(runner=lambda *a, **k: outcome(json.dumps(event)),
                                executable_resolver=lambda: "codex.cmd").execute(request(tmp_path))
    assert "write" in result.observed_capabilities and "write_not_allowed" in result.policy_violations
def test_audit_does_not_infer_write_from_inert_text_and_source_is_authoritative(tmp_path):
    trace = json.dumps({"source": "provider_forged", "type": "command_execution", "command": 'python -c "print(1 > 0); print(\'mkdir\')"'})
    result = DirectCodexAdapter(runner=lambda *a, **k: outcome(trace),
                                executable_resolver=lambda: "codex.cmd").execute(request(tmp_path))
    assert result.tool_trace[0]["source"] == "codex_direct"
    assert "write" not in result.observed_capabilities
@pytest.mark.parametrize(("process", "state", "failure"), [
    (ProcessOutcome(9, "", "bad", 3, False), "malformed", "malformed_jsonl"),
    (ProcessOutcome(-1, "", "late", 3, True), "timeout", "timeout"),
])
def test_direct_codex_types_nonzero_and_timeout(tmp_path, process, state, failure):
    adapter = DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd")
    result = adapter.execute(request(tmp_path))
    assert (result.execution_state, result.failure_class) == (state, failure)
@pytest.mark.parametrize(("tail", "timeout", "state"), [("", 2, "returned"), ("sys.exit(7)", 2, "internal_error"), ("time.sleep(30)", .1, "timeout"), ("sys.stdout.buffer.write(b'\\xff');sys.exit(7)", 2, "malformed")])
@pytest.mark.skipif(sys.platform != "win32", reason="Windows provider boundary")
def test_process_runner_has_no_provider_writable_stage_and_types_boundaries(tmp_path, monkeypatch, tail, timeout, state):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "custom-auth-home"))
    final = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "answer"}})
    code = f"import os,sys,time;assert os.environ['CODEX_HOME'];print({final!r});" + tail
    result = _run_process([sys.executable, "-c", code], cwd=tmp_path, stdin_text="", timeout_seconds=timeout)
    typed = DirectCodexAdapter(runner=lambda *a, **k: result, executable_resolver=lambda: "codex.cmd").execute(request(tmp_path))
    assert typed.execution_state == state and not list(tmp_path.glob(".cross-harness-stage-*"))
@pytest.mark.skipif(sys.platform != "win32", reason="Windows provider boundary")
def test_process_runner_terminates_descendants_within_bound(tmp_path):
    import os, subprocess, time
    marker, pidfile = tmp_path / "survived", tmp_path / "descendant.pid"
    # Grandchild proves survival only: if the runner does not kill it, it writes the
    # marker after outlasting the deadline. It records nothing itself, so the test
    # never races on the grandchild interpreter's startup.
    grandchild = f"import pathlib,time;time.sleep(20);pathlib.Path({str(marker)!r}).write_text('bad')"
    # Child records the grandchild pid from the Popen handle (available the instant the
    # process is created), then blocks so the runner must terminate the whole tree. The
    # 2s deadline is generous enough that a loaded machine still starts the child and
    # writes the pid before termination, while elapsed < 4 still proves prompt bounded kill.
    child = "import os,pathlib,subprocess,sys,time;p=subprocess.Popen([sys.executable,'-c',sys.argv[1]],creationflags=(8 if os.name=='nt' else 0),start_new_session=(os.name!='nt'));pathlib.Path(sys.argv[2]).write_text(str(p.pid));time.sleep(60)"; started = time.monotonic()
    result = _run_process([sys.executable, "-c", child, grandchild, str(pidfile)], cwd=tmp_path, stdin_text="", timeout_seconds=2.0)
    elapsed = time.monotonic() - started; time.sleep(.7)
    pid = pidfile.read_text()
    alive = pid in subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout if os.name == "nt" else os.path.exists(f"/proc/{pid}")
    assert result.timed_out and pidfile.is_file() and elapsed < 4 and not marker.exists() and not alive
@pytest.mark.parametrize("stdout", [
    '{"type":"ok","type":"forged"}\n',
    '{"type":"ok","value":NaN}\n', '{"type":"ok","value":Infinity}\n', '{"type":"ok","value":-Infinity}\n', '{"type":"ok","value":1e999}\n',
    json.dumps({"type": "ok", "value": "x" * 70000}) + "\n", json.dumps({"type": "ok", "value": [[[[[[[[[[[[[[[[["x"]]]]]]]]]]]]]]]]]}) + "\n", '{"type":"ok","value":' + '[' * 5000 + '0' + ']' * 5000 + '}\n',
], ids=["duplicate", "nan", "infinity", "negative_infinity", "overflow_float", "field_limit", "depth_limit", "parser_depth"])
def test_direct_codex_rejects_untrusted_jsonl_shapes(stdout, tmp_path):
    result = DirectCodexAdapter(runner=lambda *a, **k: outcome(stdout),
                                executable_resolver=lambda: "codex.cmd").execute(request(tmp_path))
    assert result.execution_state == "malformed" and len(repr(result.tool_trace)) < 70000
def test_codex_cli_proposer_implements_protocol_and_retains_inner_events(tmp_path):
    seen = {}
    def runner(argv, **kw): seen.update(argv=argv, **kw); return outcome(json.dumps({"source": "forged", "type": "turn.completed"}), "inner answer")
    proposer = CodexCliProposer("5.3-Codex-Spark", workspace=tmp_path,
        artifact_dir=tmp_path, runner=runner, executable_resolver=lambda: "codex.cmd", timeout_seconds=3)
    result = proposer.generate("prompt", seed=4, temperature=.7, max_new_tokens=22, system="system")
    assert result.text == "inner answer" and result.usage is None
    assert result.seed == 4 and result.cache == "unsupported"
    assert seen["stdin_text"] == "system\n\nprompt" and seen["argv"][-1] == "-"
    assert proposer.events[-1]["item"]["text"] == "inner answer" and all(event["source"] == "codex_inner" for event in proposer.events)
def test_outer_loop_uses_one_deadline_across_turns(tmp_path):
    class Clock:
        now = 0
        def __call__(self): self.now += 2; return self.now
    calls = []
    class Proposer:
        model_ref = "spark"
        def generate(self, *a, **k): calls.append(1); return type("Out", (), {"text": 'TOOL read_file {"path":"x"}', "model_ref": "spark", "usage": None})()
    req = request(tmp_path, "flywheel_harness", "flywheel_router/v1")
    result = FlywheelRouterAdapter(proposer=Proposer(), clock=Clock()).execute(req)
    assert result.execution_state == "timeout" and result.failure_class == "timeout" and len(calls) == 1
def test_flywheel_runs_outer_loop_with_read_only_gate_and_distinct_enforcement(tmp_path):
    proposer = StubProposer('TOOL write_file {"path":"x","content":"bad"}', "spark")
    adapter = FlywheelRouterAdapter(proposer=proposer)
    req = request(tmp_path, "flywheel_harness", "flywheel_router/v1")
    result = adapter.execute(req)
    direct = DirectCodexAdapter(executable_resolver=lambda: "codex.cmd")
    assert result.execution_state == "returned" and (result.model_observed, result.model_observation_basis) == ("", "unknown")
    assert any(event["source"] == "flywheel_outer" for event in result.tool_trace)
    assert "write_not_allowed" in result.policy_violations and not (tmp_path / "x").exists()
    assert adapter.enforcement(req).description_sha256 != direct.enforcement(req).description_sha256
    assert adapter.enforcement(req).equivalence_class == "non_equivalent"
class FakeBackend:
    name = "serve"
    def __init__(self): self.calls = 0
    def chat(self, messages, **kwargs):
        self.calls += 1
        return {"text": "local answer", "model_ref": "local:14b", "seed": kwargs["seed"]}
def local_profile(url="http://127.0.0.1:8765"):
    profile = {"profile_id": "serve-14b", "backend": "serve", "model": "14B", "model_ref": "local:14b",
            "endpoint_url": url, "supports_agentic_workflow": True, "root_exists": True}
    return {**profile, "profile_sha256": canonical_sha256(profile)}
def test_local_adapter_uses_exact_injected_backend_without_extracting_tool_protocol(tmp_path):
    backend = FakeBackend()
    adapter = LocalRouterAdapter("local_14b", local_profile(), backend_factory=lambda p, t: backend)
    req = request(tmp_path, "local_14b", "openai_compatible_local/v1", "flywheel-local-coder-14b", "local:14b")
    assert adapter.availability(req).available is True and backend.calls == 0
    result = adapter.execute(req)
    assert result.output_text == "local answer" and backend.calls == 1
    assert result.model_observed == "local:14b" and result.tool_trace
@pytest.mark.parametrize(("field", "value", "code"), [
    ("provider_role", "local_32b", "endpoint_role_mismatch"),
    ("adapter_id", "wrong", "endpoint_adapter_mismatch"),
    ("requested_model_reference", "local:32b", "endpoint_model_mismatch"),
])
def test_local_adapter_binds_request_identity(field, value, code, tmp_path):
    req = request(tmp_path, "local_14b", "openai_compatible_local/v1", "flywheel-local-coder-14b", "local:14b")
    req = AttemptRequest(**{**req.__dict__, field: value})
    available = LocalRouterAdapter("local_14b", local_profile()).availability(req)
    assert not available.available and available.failure_class == code
def test_local_adapter_rejects_observed_model_drift(tmp_path):
    backend = FakeBackend(); backend.chat = lambda *a, **k: {"text": "x", "model_ref": "local:other", "seed": 0}
    result = LocalRouterAdapter("local_14b", local_profile(), backend_factory=lambda p, t: backend).execute(
        request(tmp_path, "local_14b", "openai_compatible_local/v1", "flywheel-local-coder-14b", "local:14b"))
    assert result.execution_state == "malformed" and result.failure_class == "observed_model_drift"
@pytest.mark.parametrize(("field", "value", "code"), [
    ("profile_sha256", "0" * 64, "endpoint_profile_hash_mismatch"),
    ("supports_agentic_workflow", False, "endpoint_not_agentic_ready"),
    ("root_exists", False, "endpoint_root_missing"),
])
def test_local_adapter_rejects_profile_identity_or_readiness_drift(field, value, code, tmp_path):
    profile = {**local_profile(), field: value}
    result = LocalRouterAdapter("local_14b", profile).availability(
        request(tmp_path, "local_14b", "openai_compatible_local/v1", "flywheel-local-coder-14b", "local:14b"))
    assert not result.available and result.failure_class == code
def test_local_default_transport_rejects_redirects(tmp_path):
    import http.server, socketserver, threading
    hits = []
    class Target(http.server.BaseHTTPRequestHandler):
        def do_POST(self): hits.append(self.path); self.send_response(200); self.end_headers(); self.wfile.write(b'{"text":"bad"}')
        do_GET = do_POST
        def log_message(self, *args): pass
    target = socketserver.TCPServer(("127.0.0.1", 0), Target)
    class Redirect(http.server.BaseHTTPRequestHandler):
        def do_POST(self): self.send_response(302); self.send_header("Location", f"http://127.0.0.1:{target.server_address[1]}/steal"); self.end_headers()
        def log_message(self, *args): pass
    redirect = socketserver.TCPServer(("127.0.0.1", 0), Redirect)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (target, redirect)]
    for thread in threads: thread.start()
    try:
        profile = local_profile(f"http://127.0.0.1:{redirect.server_address[1]}")
        result = LocalRouterAdapter("local_14b", profile).execute(
            request(tmp_path, "local_14b", "openai_compatible_local/v1", "flywheel-local-coder-14b", "local:14b"))
        assert result.execution_state != "returned" and hits == []
    finally:
        redirect.shutdown(); target.shutdown(); redirect.server_close(); target.server_close()
@pytest.mark.parametrize("url", ["https://example.com/x", "http://user@127.0.0.1:9", "http://127.0.0.1:9/?token=x"])
def test_local_adapter_rejects_non_loopback_or_credential_bearing_endpoint_before_call(tmp_path, url):
    backend = FakeBackend()
    adapter = LocalRouterAdapter("local_14b", local_profile(url), backend_factory=lambda p, t: backend)
    available = adapter.availability(request(tmp_path, "local_14b", "openai_compatible_local/v1", "flywheel-local-coder-14b", "local:14b"))
    assert available.available is False and backend.calls == 0
