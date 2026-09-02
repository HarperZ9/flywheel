import json
from harness.cross_harness_adapters import CodexCliProposer, FlywheelRouterAdapter, ProcessOutcome
from harness.cross_harness_executor import SHARED_TOOL_POLICY
from harness.cross_harness_types import AttemptRequest, sanitize_evidence
from harness.cross_harness_usage import attempt_usage, recheck_inner_usage, usage_from_events, usage_records_from_trace
USAGE_A = {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 30, "reasoning_output_tokens": 5, "total_tokens": 135}
USAGE_B = {"input_tokens": 200, "cached_input_tokens": 0, "output_tokens": 50, "reasoning_output_tokens": 10, "total_tokens": 260}
def request(tmp_path, role="flywheel_harness", adapter="flywheel_router/v1", model="gpt-5.3-codex-spark"):
    return AttemptRequest("run", "spark", "set", "agt-001-full", "do the task", "a" * 64, role, role.split("_")[0], adapter, model, model, tmp_path, "b" * 64, {}, SHARED_TOOL_POLICY, "c" * 64, 1, "cold_declared", 3, tmp_path)
def outcome(stdout="", output="answer"):
    if output is not None:
        final = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": output}})
        stdout = "\n".join(filter(None, (stdout, final)))
    return ProcessOutcome(0, stdout, "", 7, False)
def turn(usage, model="served-spark"):
    return json.dumps({"type": "turn.completed", "model": model, "usage": usage})
def governed(tmp_path):
    outs = [outcome(turn(USAGE_A), 'TOOL read_file {"path":"x"}'), outcome(turn(USAGE_B), "final answer")]
    adapter = FlywheelRouterAdapter(runner=lambda *a, **k: outs.pop(0), executable_resolver=lambda: "codex.cmd", proposer_invocations_max=None)
    result = adapter.execute(request(tmp_path))
    assert result.execution_state == "returned" and not outs
    return result
def test_codex_cli_proposer_captures_usage_verbatim(tmp_path):
    proposer = CodexCliProposer("spark", workspace=tmp_path, artifact_dir=tmp_path, timeout_seconds=3,
        runner=lambda *a, **k: outcome(turn(USAGE_A), "inner answer"), executable_resolver=lambda: "codex.cmd")
    result = proposer.generate("prompt", seed=1, temperature=.7, max_new_tokens=9)
    assert result.usage == USAGE_A and result.usage["total_tokens"] == 135
    assert result.served_model == "served-spark"
    assert proposer.events and all(event["inner_call"] == 1 for event in proposer.events)
def test_usage_from_events_is_last_wins_and_none_when_absent():
    assert usage_from_events([{"type": "turn.completed", "model": "m"}]) is None
    events = [{"type": "turn.completed", "usage": USAGE_A}, {"type": "turn.completed", "usage": USAGE_B}]
    assert usage_from_events(events) == USAGE_B
def test_governed_arm_receipt_carries_recomputable_usage(tmp_path):
    result = governed(tmp_path)
    assert result.usage == {"inner_calls": 2, "per_call": [USAGE_A, USAGE_B], "aggregate": {
        "cached_input_tokens": 20, "input_tokens": 300, "output_tokens": 80,
        "reasoning_output_tokens": 15, "total_tokens": 395}}
    assert recheck_inner_usage(result.tool_trace, result.usage) == {"verified": True, "recomputed": result.usage}
    assert result.resource_observation == {"inner_call_count": 2,
        "cli_version": "", "resolved_binary_path": "codex.cmd", "reasoning_effort": "unspecified"}
def test_perturbed_transcript_or_claim_trips_refusal(tmp_path):
    result = governed(tmp_path)
    trace = [dict(event) for event in result.tool_trace]
    victim = next(event for event in trace if event.get("source") == "codex_inner" and event.get("type") == "turn.completed")
    victim["usage"] = {**victim["usage"], "output_tokens": victim["usage"]["output_tokens"] + 1}
    tripped = recheck_inner_usage(trace, result.usage)
    assert tripped["verified"] is False and tripped["usage_cell_refused"].startswith("USAGE_RECOMPUTE_MISMATCH")
    assert tripped["claimed"] == result.usage and tripped["recomputed"] != result.usage
    inflated = {**result.usage, "aggregate": {**result.usage["aggregate"], "total_tokens": 396}}
    tripped = recheck_inner_usage(result.tool_trace, inflated)
    assert tripped["verified"] is False and tripped["usage_cell_refused"].startswith("USAGE_RECOMPUTE_MISMATCH")
def test_attempt_usage_sums_only_full_matching_integer_records():
    assert attempt_usage([]) == {} and attempt_usage([None, None]) == {}
    summed = attempt_usage([USAGE_A, USAGE_B])
    assert summed["aggregate"] == {"cached_input_tokens": 20, "input_tokens": 300, "output_tokens": 80,
                                   "reasoning_output_tokens": 15, "total_tokens": 395}
    partial = attempt_usage([USAGE_A, None])
    assert partial["aggregate"] is None and partial["aggregate_refused"].startswith("USAGE_ABSENT")
    assert partial["per_call"] == [USAGE_A, None] and partial["inner_calls"] == 2
    skew = attempt_usage([USAGE_A, {"input_tokens": 1}])
    assert skew["aggregate"] is None and skew["aggregate_refused"].startswith("USAGE_KEY_MISMATCH")
    for bad in ({"input_tokens": True}, {"input_tokens": -1}, {"input_tokens": 1.5}, {"input_tokens": "7"}):
        out = attempt_usage([bad])
        assert out["aggregate"] is None and out["aggregate_refused"].startswith("USAGE_NON_SUMMABLE")
    assert attempt_usage(["oops"])["aggregate_refused"].startswith("USAGE_MALFORMED")
def test_recheck_never_raises_on_malformed_inputs():
    assert recheck_inner_usage("nope", {})["usage_cell_refused"].startswith("USAGE_TRANSCRIPT_MALFORMED")
    assert recheck_inner_usage([], None)["usage_cell_refused"].startswith("USAGE_CLAIM_MALFORMED")
    assert recheck_inner_usage([], {}) == {"verified": True, "recomputed": {}}
def test_trace_recovery_orders_calls_and_marks_usageless_calls():
    trace = [{"source": "codex_inner", "inner_call": 2, "type": "turn.completed", "usage": USAGE_B},
             {"source": "codex_inner", "inner_call": 1, "type": "item.completed"},
             {"source": "flywheel_outer", "inner_call": 9, "type": "turn.completed", "usage": USAGE_A}]
    assert usage_records_from_trace(trace) == [None, USAGE_B]
def test_redaction_passes_token_counts_and_keeps_string_secrets(tmp_path):
    stdout = json.dumps({"type": "turn.completed", "model": "m", "usage": USAGE_A, "api_token": "sk-live-abcdefghijkl"})
    proposer = CodexCliProposer("spark", workspace=tmp_path, artifact_dir=tmp_path, timeout_seconds=3,
        runner=lambda *a, **k: outcome(stdout, "inner answer"), executable_resolver=lambda: "codex.cmd")
    result = proposer.generate("prompt", seed=1, temperature=.7, max_new_tokens=9)
    assert result.usage == USAGE_A
    event = next(e for e in proposer.events if e.get("type") == "turn.completed")
    assert event["api_token"] == "[REDACTED]" and event["usage"] == USAGE_A
    assert sanitize_evidence({"usage": dict(USAGE_A), "session_token": "abc"}) == {"usage": USAGE_A, "session_token": "[REDACTED]"}
