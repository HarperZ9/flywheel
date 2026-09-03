"""Falsifiers for the Claude Code and Cursor adapters.

These two peers are the only harnesses besides codex the executor can actually
drive, so what they record has to be the provider's own report rather than
anything this repository decided on its behalf. The tests below check the four
places that could quietly become a fabrication:

- the command line, which is what makes a run read-only and unconfigured;
- the tool audit, which sees nothing at all unless each peer's tool names are
  normalized into the vocabulary _audit classifies;
- the usage cell, which has to survive its own recompute from the transcript;
- the cost cell, which stays null for a peer that reports no cost.

Every stream in this file is a fixture, so nothing here calls a provider.
"""
import json

import pytest

from harness.adapter_runtime_matrix import _auth_matches
from harness.cross_harness_adapters import ProcessOutcome
from harness.cross_harness_cli import build_adapter_registry
from harness.cross_harness_executor import SHARED_TOOL_POLICY
from harness.cross_harness_peer_adapters import (CLAUDE_ALLOWED_TOOLS, DirectClaudeCodeAdapter,
                                                 DirectCursorAdapter)
from harness.cross_harness_types import AttemptRequest, metric_null_reasons
from harness.cross_harness_usage import inner_source, recheck_inner_usage

FLAT_USAGE = {"input_tokens": 12, "output_tokens": 30}
NESTED_USAGE = {"input_tokens": 12, "output_tokens": 30,
                "output_tokens_details": {"reasoning_tokens": 4}}


def request(tmp_path, role="claude_code", adapter="claude_code_cli_json/v1",
            model="claude-sonnet-5", requested=None):
    return AttemptRequest("run", "spark", "set", "agt-001-full", "do the task", "a" * 64, role,
                          role, adapter, model, requested or model, tmp_path, "b" * 64, {},
                          SHARED_TOOL_POLICY, "c" * 64, 1, "cold_declared", 3, tmp_path)


def stream(*events) -> str:
    return "\n".join(json.dumps(event) for event in events)


def claude_init(**over):
    return {"type": "system", "subtype": "init", "model": "claude-sonnet-5",
            "permissionMode": "restricted", "tools": sorted(CLAUDE_ALLOWED_TOOLS),
            "mcp_servers": [], **over}


def claude_assistant(*blocks, model="claude-sonnet-5"):
    return {"type": "assistant", "message": {"model": model, "content": list(blocks)}}


def claude_result(**over):
    return {"type": "result", "subtype": "success", "is_error": False, "result": "answer",
            "duration_ms": 900, "duration_api_ms": 700, "num_turns": 2,
            "total_cost_usd": 0.0097132, "usage": dict(FLAT_USAGE), **over}


def cursor_init(**over):
    return {"type": "system", "subtype": "init", "model": "Cursor Default",
            "permissionMode": "ask", **over}


def outcome(stdout: str, *, rc=0, stderr="", elapsed=11, timed_out=False, malformed=False):
    return ProcessOutcome(rc, stdout, stderr, elapsed, timed_out, malformed)


def _adapter(cls, version, stdout, path, seen, kw):
    def runner(argv, **kwargs):
        if seen is not None: seen.update(argv=argv, **kwargs)
        return outcome(stdout, **kw)
    return cls(runner=runner, executable_resolver=lambda: path, version_probe=lambda _: version)


def claude(stdout="", *, path="C:/bin/claude.exe", seen=None, **kw):
    return _adapter(DirectClaudeCodeAdapter, "2.1.251", stdout, path, seen, kw)


def cursor(stdout="", *, path="C:/bin/cursor-agent.exe", seen=None, **kw):
    return _adapter(DirectCursorAdapter, "1.0.0", stdout, path, seen, kw)


def test_claude_argv_is_print_mode_restricted_and_unconfigured(tmp_path):
    seen = {}
    adapter = claude(stream(claude_init(), claude_result()), seen=seen)
    adapter.execute(request(tmp_path))
    assert seen["argv"] == [
        "C:/bin/claude.exe", "-p", "--output-format", "stream-json", "--verbose",
        "--model", "claude-sonnet-5", "--restricted", "--safe-mode", "--strict-mcp-config",
        "--no-session-persistence", "--add-dir", str(tmp_path), "--tools", "Glob,Grep,Read"]
    # The prompt reaches the peer on stdin, so no task text lands in a process
    # table or a shell history that a receipt cannot account for.
    assert seen["stdin_text"] == "do the task" and seen["cwd"] == tmp_path
    assert seen["timeout_seconds"] == 3


def test_claude_reads_the_final_text_and_the_providers_own_numbers(tmp_path):
    result = claude(stream(claude_init(), claude_assistant({"type": "text", "text": "hi"}),
                           claude_result())).execute(request(tmp_path))
    assert (result.execution_state, result.output_text) == ("returned", "answer")
    assert result.resource_observation == {
        "inner_call_count": 1, "cli_version": "2.1.251",
        "resolved_binary_path": "C:/bin/claude.exe", "reasoning_effort": "unspecified",
        "provider_reported_cost_usd": 0.0097132, "duration_ms": 900,
        "provider_api_duration_ms": 700, "provider_turns": 2}
    assert result.usage["per_call"] == [FLAT_USAGE] and result.usage["aggregate"] == FLAT_USAGE
    assert result.model_observation_basis == "structured_provider_event"
    assert result.randomness_control == "unsupported" and result.policy_violations == []


def test_claude_prefers_the_answering_model_over_the_session_model(tmp_path):
    # A fallback between the model the session opened with and the model that
    # actually answered is exactly what a requested reference cannot reveal.
    result = claude(stream(claude_init(model="claude-sonnet-5"),
                           claude_assistant({"type": "text", "text": "hi"}, model="claude-haiku-4-5"),
                           claude_result())).execute(request(tmp_path))
    assert result.model_observed == "claude-haiku-4-5"


def test_claude_records_only_the_numbers_the_provider_actually_sent(tmp_path):
    thin = claude_result(total_cost_usd=None, num_turns="two", duration_api_ms=-1)
    result = claude(stream(claude_init(), thin)).execute(request(tmp_path))
    assert "provider_reported_cost_usd" not in result.resource_observation
    assert "provider_turns" not in result.resource_observation
    assert "provider_api_duration_ms" not in result.resource_observation
    assert result.resource_observation["duration_ms"] == 900


def test_claude_shell_tool_is_audited_even_though_it_is_named_bash(tmp_path):
    # The falsifier for the tool-name normalization. _audit classifies on the
    # words shell/command/exec/run, none of which appear in "Bash", so without
    # the derived observation event a peer shelling out would audit as clean.
    result = claude(stream(claude_init(),
                           claude_assistant({"type": "tool_use", "name": "Bash",
                                             "input": {"cmd": "dir"}}),
                           claude_result())).execute(request(tmp_path))
    assert "shell" in result.observed_capabilities
    assert "exec_not_allowed" in result.policy_violations
    observation = [event for event in result.tool_trace if event.get("type") == "tool_observation"]
    assert observation == [{"source": "claude_code_direct", "type": "tool_observation",
                            "declared_tool": "Bash", "tool": "shell command"}]


def test_claude_read_tool_audits_as_read_and_violates_nothing(tmp_path):
    result = claude(stream(claude_init(),
                           claude_assistant({"type": "tool_use", "name": "Read",
                                             "input": {"file_path": "x"}}),
                           claude_result())).execute(request(tmp_path))
    assert result.observed_capabilities == ["read"] and result.policy_violations == []


@pytest.mark.parametrize("over,expected", [
    ({"tools": ["Read", "Bash"]}, "declared_tool_boundary_exceeded"),
    ({"tools": "Read"}, "boundary_report_malformed"),
    ({"mcp_servers": [{"name": "fs"}]}, "mcp_not_allowed"),
    ({"permissionMode": "bypassPermissions"}, "permission_boundary_unexpected"),
])
def test_claude_cross_checks_the_boundary_against_the_peers_own_report(tmp_path, over, expected):
    # Our own command line is not evidence that it took effect, so a
    # disagreement with the init event is a recorded violation.
    result = claude(stream(claude_init(**over), claude_result())).execute(request(tmp_path))
    assert expected in result.policy_violations


def test_claude_missing_init_is_an_absent_boundary_report(tmp_path):
    result = claude(stream(claude_result())).execute(request(tmp_path))
    assert result.policy_violations == ["boundary_report_absent"]


@pytest.mark.parametrize("events,state,failure", [
    ((claude_init(),), "malformed", "malformed_jsonl"),
    ((claude_init(), claude_result(result="")), "malformed", "malformed_jsonl"),
    ((claude_init(), claude_result(is_error=True, subtype="error_during_execution")),
     "internal_error", "provider_reported_error"),
    ((claude_init(), claude_result(subtype="error_max_turns")),
     "internal_error", "provider_reported_error"),
])
def test_claude_terminal_failures_are_typed_and_carry_no_answer(tmp_path, events, state, failure):
    result = claude(stream(*events)).execute(request(tmp_path))
    assert (result.execution_state, result.failure_class) == (state, failure)
    assert result.output_text == ""


def test_claude_timeout_shadows_every_other_verdict(tmp_path):
    result = claude("not json at all", rc=1, timed_out=True).execute(request(tmp_path))
    assert (result.execution_state, result.failure_class) == ("timeout", "timeout")


def test_claude_nonzero_exit_is_typed_when_the_provider_reported_nothing(tmp_path):
    result = claude(stream(claude_init(), claude_result()), rc=2,
                    stderr="boom").execute(request(tmp_path))
    assert (result.execution_state, result.failure_class) == ("internal_error", "process_nonzero")


def test_claude_usage_survives_its_own_recompute_from_the_transcript(tmp_path):
    # The falsifier for deriving the inner source from the trace. The recompute
    # used to look only for codex_inner turn.completed events, so this adapter's
    # usage cell would have been refused for a mismatch it did not have.
    result = claude(stream(claude_init(), claude_result())).execute(request(tmp_path))
    assert inner_source(result.tool_trace) == "claude_code_inner"
    assert recheck_inner_usage(result.tool_trace, result.usage)["verified"] is True


def test_claude_nested_usage_refuses_its_aggregate_by_name(tmp_path):
    result = claude(stream(claude_init(),
                           claude_result(usage=dict(NESTED_USAGE)))).execute(request(tmp_path))
    assert result.usage["per_call"] == [NESTED_USAGE] and result.usage["aggregate"] is None
    assert result.usage["aggregate_refused"].startswith("USAGE_NON_SUMMABLE")
    assert recheck_inner_usage(result.tool_trace, result.usage)["verified"] is True


def test_a_reported_cost_clears_the_cost_null_and_an_absent_one_keeps_it(tmp_path):
    priced = claude(stream(claude_init(), claude_result())).execute(request(tmp_path))
    unpriced = claude(stream(claude_init(), claude_result(total_cost_usd=None))).execute(request(tmp_path))
    metrics = {"latency_ms": 4, "usage": priced.usage, "resource_observation": priced.resource_observation}
    assert "cost" not in metric_null_reasons(metrics)
    metrics["resource_observation"] = unpriced.resource_observation
    assert metric_null_reasons(metrics)["cost"] == "provider_cost_unavailable"


def test_claude_availability_refuses_a_missing_binary_and_a_shim(tmp_path):
    missing = claude(path="").availability(request(tmp_path))
    assert (missing.available, missing.failure_class) == (False, "claude_code_cli_missing")
    shim = claude(path=str(tmp_path / "claude.cmd")).availability(request(tmp_path))
    assert (shim.available, shim.failure_class) == (False, "shim_or_missing_binary")


def test_cursor_argv_puts_the_prompt_in_argv_and_sends_no_model_by_default(tmp_path):
    seen = {}
    adapter = cursor(stream(cursor_init(), {"type": "result", "subtype": "success",
                                            "result": "answer"}), seen=seen)
    adapter.execute(request(tmp_path, role="cursor", adapter="cursor_agent_cli_json/v1",
                            model="cursor_account_default", requested="default"))
    assert seen["argv"] == ["C:/bin/cursor-agent.exe", "agent", "-p", "--output-format",
                            "stream-json", "--workspace", str(tmp_path), "--sandbox", "enabled",
                            "--mode", "ask", "do the task"]
    # No --model at all rather than a name nothing verified against a local CLI.
    assert "--model" not in seen["argv"] and seen["stdin_text"] == ""


def test_cursor_sends_a_model_reference_when_one_is_named(tmp_path):
    seen = {}
    cursor(stream(cursor_init(), {"type": "result", "subtype": "success", "result": "a"}),
           seen=seen).execute(request(tmp_path, role="cursor", requested="sonnet-4.5"))
    assert seen["argv"][5:7] == ["--model", "sonnet-4.5"]


def test_cursor_tool_names_live_in_a_dict_key_and_are_still_audited(tmp_path):
    # _audit walks dict values and never reads a key, so Cursor's tool name is
    # invisible to it until the adapter lifts it onto a derived event.
    result = cursor(stream(cursor_init(),
                           {"type": "tool_call", "subtype": "completed",
                            "tool_call": {"writeToolCall": {"path": "x"}}},
                           {"type": "result", "subtype": "success", "result": "answer",
                            "duration_ms": 400})).execute(request(tmp_path, role="cursor"))
    assert "write" in result.observed_capabilities
    assert "write_not_allowed" in result.policy_violations


def test_cursor_reports_no_usage_and_no_cost_and_says_so(tmp_path):
    result = cursor(stream(cursor_init(),
                           {"type": "result", "subtype": "success", "result": "answer",
                            "duration_ms": 400, "duration_api_ms": 380})
                    ).execute(request(tmp_path, role="cursor"))
    assert (result.execution_state, result.output_text) == ("returned", "answer")
    assert result.model_observed == "Cursor Default" and result.usage == {}
    assert result.resource_observation == {
        "inner_call_count": 1, "cli_version": "1.0.0",
        "resolved_binary_path": "C:/bin/cursor-agent.exe", "reasoning_effort": "unspecified",
        "duration_ms": 400, "provider_api_duration_ms": 380}
    reasons = metric_null_reasons({"latency_ms": 4, "usage": result.usage,
                                   "resource_observation": result.resource_observation})
    assert reasons["cost"] == "provider_cost_unavailable"
    assert reasons["usage"] == "provider_usage_unavailable"


def test_cursor_availability_refuses_a_missing_cli(tmp_path):
    missing = cursor(path="").availability(request(tmp_path, role="cursor"))
    assert (missing.available, missing.failure_class) == (False, "cursor_cli_missing")


def test_the_executor_registry_builds_both_peers(tmp_path):
    registry = build_adapter_registry({}, ["claude_code", "cursor"])
    assert [(role, adapter.adapter_id) for role, adapter in sorted(registry.items())] == [
        ("claude_code", "claude_code_cli_json/v1"), ("cursor", "cursor_agent_cli_json/v1")]


def test_the_runtime_matrix_knows_which_account_lane_each_peer_needs():
    lanes = {"lanes": [{"id": "claude_subscription", "provider": "claude", "mode": "plan",
                        "kind": "subscription_cli", "configured": True},
                       {"id": "cursor_subscription", "provider": "cursor", "mode": "plan",
                        "kind": "subscription_cli", "configured": False}]}
    assert [row["lane_id"] for row in _auth_matches("claude_code", lanes)] == ["claude_subscription"]
    cursor_lanes = _auth_matches("cursor", lanes)
    assert [row["lane_id"] for row in cursor_lanes] == ["cursor_subscription"]
    # Presence of the CLI is the whole basis. Nothing here reads a token store.
    assert {row["evidence_basis"] for row in cursor_lanes} == {"cli_presence_only"}
    assert cursor_lanes[0]["configured"] is False
