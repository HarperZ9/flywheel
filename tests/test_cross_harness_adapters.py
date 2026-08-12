from datetime import UTC, datetime, timedelta
import hashlib, json
from pathlib import Path

import pytest

from harness.cross_harness_adapters import (
    CodexCliProposer, DirectCodexAdapter, FlywheelRouterAdapter,
    LocalRouterAdapter, ProcessOutcome, _run_process,
)
from harness.cross_harness_artifacts import bind_attempt_receipt, canonical_sha256
from harness.cross_harness_cli import _apply_admission, _recheck_local_gate, main as cross_main
from harness.cross_harness_executor import SHARED_TOOL_POLICY
from harness.cross_harness_types import AttemptRequest
from harness.proposer import StubProposer


def request(tmp_path, role="codex_harness", adapter="codex_cli_json/v1", model="5.3-Codex-Spark"):
    return AttemptRequest(
        "run", "spark", "set", "agt-001-full", "do the task", "a" * 64,
        role, role.split("_")[0], adapter, model, tmp_path, "b" * 64, {},
        SHARED_TOOL_POLICY, "c" * 64, 1, "cold_declared", 3, tmp_path,
    )


def outcome(stdout="", output="answer", *, rc=0, stderr="", elapsed=7):
    return ProcessOutcome(rc, stdout, stderr, output, elapsed, False)


def test_direct_codex_uses_stdin_hardened_read_only_argv_and_captures_jsonl(tmp_path):
    seen = {}
    trace = '\n'.join([
        json.dumps({"type": "item.completed", "item": {"type": "file_read", "path": "x"}}),
        json.dumps({"type": "item.completed", "item": {"type": "command_execution", "command": "dir"}}),
    ])
    def runner(argv, **kw):
        seen.update(argv=argv, **kw)
        return outcome(trace)
    adapter = DirectCodexAdapter(runner=runner, executable_resolver=lambda: "C:/bin/codex.cmd")
    result = adapter.execute(request(tmp_path))
    assert seen["argv"] == [
        "C:/bin/codex.cmd", "exec", "--model", "5.3-Codex-Spark",
        "--sandbox", "read-only", "--cd", str(tmp_path), "--ephemeral",
        "--ignore-user-config", "--skip-git-repo-check", "--json",
        "--output-last-message", str(tmp_path / "last-message.txt"), "-",
    ]
    assert seen["stdin_text"] == "do the task" and seen["cwd"] == tmp_path
    assert result.execution_state == "returned" and len(result.tool_trace) == 3
    assert result.usage == {} and result.resource_observation == {}
    assert result.randomness_control == "unsupported"
    assert result.observed_capabilities == ["read", "shell"]
    assert result.policy_violations == ["exec_not_allowed"]


def test_direct_codex_marks_any_nonblank_malformed_jsonl_and_sanitizes_secrets(tmp_path):
    secret = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature"
    api_key = "sk-" + "proj-" + "abcdefghijklmnopqrstuvwxyz"
    stdout = "not-json\n" + json.dumps({"headers": [{"name": "Authorization", "value": "Bearer hide-me"}], "jwt": secret})
    adapter = DirectCodexAdapter(runner=lambda *a, **k: outcome(stdout, secret + " " + api_key),
                                 executable_resolver=lambda: "codex.cmd")
    result = adapter.execute(request(tmp_path))
    assert result.execution_state == "malformed" and result.failure_class == "malformed_jsonl"
    assert "hide-me" not in repr(result.tool_trace) and secret not in result.output_text and api_key not in result.output_text


def test_direct_codex_audits_mcp_and_shell_write_attempts(tmp_path):
    stdout = '\n'.join((json.dumps({"type": "mcp_tool_call", "name": "lookup"}),
                        json.dumps({"type": "command_execution", "command": "echo bad > x.txt"})))
    adapter = DirectCodexAdapter(runner=lambda *a, **k: outcome(stdout),
                                 executable_resolver=lambda: "codex.cmd")
    result = adapter.execute(request(tmp_path))
    assert result.observed_capabilities == ["shell", "mcp", "write"]
    assert result.policy_violations == ["exec_not_allowed", "mcp_not_allowed", "write_not_allowed"]


@pytest.mark.parametrize(("process", "state", "failure"), [
    (ProcessOutcome(9, "", "bad", "", 3, False), "internal_error", "process_nonzero"),
    (ProcessOutcome(-1, "", "late", "", 3, True), "timeout", "timeout"),
])
def test_direct_codex_types_nonzero_and_timeout(tmp_path, process, state, failure):
    adapter = DirectCodexAdapter(runner=lambda *a, **k: process,
                                 executable_resolver=lambda: "codex.cmd")
    result = adapter.execute(request(tmp_path))
    assert (result.execution_state, result.failure_class) == (state, failure)


def test_process_runner_terminates_a_timed_out_process_group(tmp_path):
    import sys
    result = _run_process([sys.executable, "-c", "import time; time.sleep(30)"],
                          cwd=tmp_path, stdin_text="", timeout_seconds=.05,
                          output_path=tmp_path / "out.txt")
    assert result.timed_out is True and result.elapsed_ms >= 0


def test_codex_cli_proposer_implements_protocol_and_retains_inner_events(tmp_path):
    seen = {}
    def runner(argv, **kw):
        seen.update(argv=argv, **kw)
        return outcome(json.dumps({"type": "turn.completed"}), "inner answer")
    proposer = CodexCliProposer("5.3-Codex-Spark", workspace=tmp_path,
        artifact_dir=tmp_path, runner=runner, executable_resolver=lambda: "codex.cmd", timeout_seconds=3)
    result = proposer.generate("prompt", seed=4, temperature=.7, max_new_tokens=22, system="system")
    assert result.text == "inner answer" and result.usage is None
    assert result.seed == 4 and result.cache == "unsupported"
    assert seen["stdin_text"] == "system\n\nprompt" and seen["argv"][-1] == "-"
    assert proposer.events == [{"source": "codex_inner", "type": "turn.completed"}]


def test_flywheel_runs_outer_loop_with_read_only_gate_and_distinct_enforcement(tmp_path):
    proposer = StubProposer('TOOL write_file {"path":"x","content":"bad"}', "spark")
    adapter = FlywheelRouterAdapter(proposer=proposer)
    req = request(tmp_path, "flywheel_harness", "flywheel_router/v1")
    result = adapter.execute(req)
    direct = DirectCodexAdapter(executable_resolver=lambda: "codex.cmd")
    assert result.execution_state == "returned" and result.model_observed == "spark"
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
    return {"profile_id": "serve-14b", "profile_sha256": "d" * 64,
            "backend": "serve", "model": "14B", "model_ref": "local:14b",
            "endpoint_url": url, "supports_agentic_workflow": True, "root_exists": True}


def test_local_adapter_uses_exact_injected_backend_without_extracting_tool_protocol(tmp_path):
    backend = FakeBackend()
    adapter = LocalRouterAdapter("local_14b", local_profile(), backend_factory=lambda p, t: backend)
    req = request(tmp_path, "local_14b", "openai_compatible_local/v1", "14B")
    assert adapter.availability(req).available is True and backend.calls == 0
    result = adapter.execute(req)
    assert result.output_text == "local answer" and backend.calls == 1
    assert result.model_observed == "local:14b" and result.tool_trace


@pytest.mark.parametrize("url", ["https://example.com/x", "http://user@127.0.0.1:9", "http://127.0.0.1:9/?token=x"])
def test_local_adapter_rejects_non_loopback_or_credential_bearing_endpoint_before_call(tmp_path, url):
    backend = FakeBackend()
    adapter = LocalRouterAdapter("local_14b", local_profile(url), backend_factory=lambda p, t: backend)
    available = adapter.availability(request(tmp_path, "local_14b", "openai_compatible_local/v1", "14B"))
    assert available.available is False and backend.calls == 0


def _receipt_hash(row):
    body = {key: value for key, value in row.items() if key not in {"receipt_hash", "latency_ms"}}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def test_local_phase_rechecks_bound_gate_and_emits_all_eight_sanitized_unavailable_rows(tmp_path):
    source = tmp_path / "source"; source.mkdir()
    tasks = [{"task_id": f"agt-{n:03d}-full", "raw_prompt": f"p{n}",
              "raw_prompt_sha256": f"{n:064x}", "input_sha256s": {}, "required_inputs": [],
              "expected_artifacts": [], "oracle": {}} for n in (1, 3, 9, 10)]
    roles = ["local_14b", "local_32b"]
    manifest = {"schema": "harness.cross-harness-manifest/v1", "task_set_id": "set", "task_rows": tasks, "provider_specs": [
        {"provider_role": role, "harness_id": "local_endpoint",
         "adapter_id": "openai_compatible_local/v1", "target_model": role[-3:].upper()}
        for role in roles]}
    profiles = {"schema": "harness.model-endpoint-profiles/v1", "profiles": []}
    gate_rows, runtime_rows = [], []
    stale = (datetime.now(UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    for role, port in zip(roles, (8765, 8767)):
        model = role[-3:].upper(); profile = {"profile_id": f"serve-{model.lower()}",
            "model": model, "backend": "serve", "provider_role": "flywheel",
            "model_ref": f"local:{model}", "endpoint_url": f"http://127.0.0.1:{port}",
            "root_exists": True, "supports_agentic_workflow": True}
        profiles["profiles"].append(profile); profile_hash = canonical_sha256(profile)
        gate = {"schema": "harness.model-endpoint-gate.row/v1", "selected_profile_id": profile["profile_id"],
            "profile_sha256": profile_hash, "model": model, "backend": "serve",
            "expected_model_ref": profile["model_ref"], "observed_model_ref": profile["model_ref"],
            "health_ok": True, "generation_ok": True, "failure_class": "", "ollama_digest": "",
            "run_id": "gate-1", "observed_at": stale}
        gate["receipt_hash"] = _receipt_hash(gate); gate_rows.append(gate)
        runtime_rows.append({"provider_role": role, "focused_run_ready": True, "blocking_gates": [],
            "endpoint_profile_matches": [{"profile_id": profile["profile_id"], "model": model,
                "backend": "serve", "model_ref": profile["model_ref"], "profile_sha256": profile_hash,
                "root_exists": True, "supports_agentic_workflow": True}], "endpoint_gate_matches": []})
    gate = {"schema": "harness.model-endpoint-gate/v1", "run_id": "gate-1", "rows": gate_rows}
    for name, data in (("manifest.json", manifest), ("profiles.json", profiles), ("gate.json", gate)):
        (tmp_path / name).write_text(json.dumps(data), encoding="utf-8")
    gate_sha = hashlib.sha256((tmp_path / "gate.json").read_bytes()).hexdigest()
    matrix = {"schema": "harness.adapter-runtime-matrix/v1", "endpoint_profiles_path": str(tmp_path / "profiles.json"),
        "endpoint_profiles_sha256": hashlib.sha256((tmp_path / "profiles.json").read_bytes()).hexdigest(),
        "endpoint_gate_path": str(tmp_path / "gate.json"), "endpoint_gate_sha256": gate_sha,
        "expected_gate_run_id": "gate-1", "runtime_rows": runtime_rows}
    (tmp_path / "matrix.json").write_text(json.dumps(matrix), encoding="utf-8")
    args = ["--manifest", str(tmp_path / "manifest.json"), "--runtime-matrix", str(tmp_path / "matrix.json"),
        "--artifact-root", str(tmp_path / "artifacts"), "--tasks", "agt-001,agt-003,agt-009,agt-010",
        "--roles", ",".join(roles), "--repetitions", "1", "--source-commit", "abc",
        "--source-root", str(source), "--phase", "local", "--timeout-seconds", "3", "--cache-state", "cold_declared",
        "--endpoint-gate", str(tmp_path / "gate.json"), "--gate-run-id", "gate-1", "--max-gate-age-seconds", "900",
        "--run-id", "local-run", "--strict-exit"]
    assert cross_main(args) == 1
    run = json.loads((tmp_path / "artifacts" / "local-run" / "run.json").read_text())
    scorecard = json.loads((tmp_path / "artifacts" / "local-run" / "scorecard.json").read_text())
    comparison = json.loads((tmp_path / "artifacts" / "local-run" / "comparison-input.json").read_text())
    assert scorecard == comparison and scorecard["schema"] == "harness.cross-harness-task-scorecard/v1"
    assert "seed" not in scorecard and (tmp_path / "artifacts" / "local-run" / "artifact-index.json").is_file()
    assert len(run["rows"]) == 8 and all(row["execution_state"] == "unavailable" for row in run["rows"])
    for row in run["rows"]:
        evidence = row["availability_evidence"]
        assert evidence["blocking_gates"] == ["endpoint_gate_stale"]
        assert all(evidence[key] for key in ("role", "backend", "requested_model_reference",
            "observed_model_reference", "endpoint_profile_id", "endpoint_profile_sha256",
            "attempted_gate_path", "attempted_gate_sha256", "attempted_gate_run_id", "failure_reason"))
        assert "token" not in json.dumps(evidence).lower()


def test_admission_recheck_blocks_only_the_role_with_a_drifted_attempt_receipt(tmp_path):
    roles, task = ["codex_harness", "flywheel_harness"], "agt-001-full"
    rows = []
    for role in roles:
        attempt = tmp_path / role; attempt.mkdir(); receipt = attempt / "receipt.json"
        row = {"phase": "admission-smoke", "provider_role": role, "task_id": task,
               "repetition": 1, "primary_outcome": "completed", "receipt_path": str(receipt)}
        bind_attempt_receipt(row, {}, receipt); rows.append(row)
    rows[1]["failure_detail"] = "post-seal drift"
    admission = tmp_path / "admission.json"
    admission.write_text(json.dumps({"schema": "harness.cross-harness-run-receipt/v1",
                                     "phase": "admission-smoke", "rows": rows}), encoding="utf-8")
    matrix = {"runtime_rows": [{"provider_role": role, "focused_run_ready": True, "blocking_gates": []}
                               for role in roles]}
    _apply_admission(matrix, admission, {"task_rows": [{"task_id": task}]}, ["agt-001"], roles, 1)
    assert matrix["runtime_rows"][0]["focused_run_ready"] is True
    assert matrix["runtime_rows"][1]["focused_run_ready"] is False
    assert matrix["runtime_rows"][1]["blocking_gates"] == ["admission_role_failed"]


def test_missing_gate_or_admission_artifact_blocks_rows_instead_of_aborting(tmp_path):
    local = {"runtime_rows": [{"provider_role": "local_14b", "focused_run_ready": True,
                               "blocking_gates": [], "endpoint_profile_matches": [{}]}],
             "endpoint_gate_sha256": "a" * 64}
    _recheck_local_gate(local, tmp_path / "missing-gate.json", "gate", ["local_14b"], datetime.now(UTC), 900)
    assert local["runtime_rows"][0]["blocking_gates"] == ["endpoint_gate_missing"]
    spark = {"runtime_rows": [{"provider_role": "codex_harness", "focused_run_ready": True,
                               "blocking_gates": []}]}
    _apply_admission(spark, tmp_path / "missing-admission.json", {"task_rows": []}, [], ["codex_harness"], 1)
    assert spark["runtime_rows"][0]["blocking_gates"] == ["admission_receipt_malformed"]
