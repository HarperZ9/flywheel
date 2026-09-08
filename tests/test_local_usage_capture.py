import hashlib
import json
from pathlib import Path

import pytest

from harness.cross_harness_adapters import (
    FlywheelRouterAdapter,
    LocalRouterAdapter,
    ProcessOutcome,
)
from harness.cross_harness_artifacts import canonical_sha256
from harness.cross_harness_executor import SHARED_TOOL_POLICY, execute_cross_harness_manifest
from harness.cross_harness_types import AttemptRequest
from harness.cross_harness_usage import (
    inner_source,
    recheck_inner_usage,
    usage_records_from_trace,
)
from harness.endpoint_registry import BackendProposer
from harness.local_agent import BackendError, OllamaBackend


USAGE_A = {
    "prompt_eval_count": 10,
    "prompt_eval_cached_count": 2,
    "eval_count": 3,
    "prompt_eval_duration": 1000,
    "eval_duration": 2000,
    "load_duration": 3000,
    "total_duration": 6000,
}
USAGE_B = {
    "prompt_eval_count": 20,
    "prompt_eval_cached_count": 4,
    "eval_count": 5,
    "prompt_eval_duration": 4000,
    "eval_duration": 5000,
    "load_duration": 6000,
    "total_duration": 15000,
}


def _profile():
    profile = {
        "profile_id": "local-14b",
        "backend": "ollama",
        "model": "14B",
        "model_ref": "local:14b",
        "endpoint_url": "http://127.0.0.1:11434",
        "supports_agentic_workflow": True,
        "root_exists": True,
    }
    return {**profile, "profile_sha256": canonical_sha256(profile)}


def _request(root: Path) -> AttemptRequest:
    return AttemptRequest(
        "run", "local", "set", "agt-001-task", "prompt", "a" * 64,
        "local_14b", "local_endpoint", "openai_compatible_local/v1",
        "flywheel-local-coder-14b", "local:14b", root, "b" * 64, {},
        SHARED_TOOL_POLICY, "c" * 64, 1, "cold_declared", 3, root,
    )


class _FixedBackend:
    name = "fixed"

    def __init__(self, output):
        self.output = output

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        return self.output


class _ScriptedBackend:
    name = "scripted"

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


def _ollama_chat(raw):
    backend = OllamaBackend(
        model="ollama:qwen2.5:7b",
        transport=lambda *_: (200, raw),
    )
    return backend.chat([], system="", max_tokens=8, temperature=0, seed=7)


def _router(tmp_path, *outputs):
    (tmp_path / "x").write_text("evidence", encoding="utf-8")
    backend = _ScriptedBackend(*outputs)
    adapter = LocalRouterAdapter("local_14b", _profile(), backend_factory=lambda *_: backend)
    return adapter.execute(_request(tmp_path)), backend


def _tool(usage):
    return {
        "text": 'TOOL read_file {"path":"x"}',
        "model_ref": "local:14b",
        "seed": 7,
        "usage": usage,
    }


def _final(text, usage=None):
    out = {"text": text, "model_ref": "local:14b", "seed": 7}
    if usage is not None:
        out["usage"] = usage
    return out


def _aggregate():
    return {key: USAGE_A[key] + USAGE_B[key] for key in sorted(USAGE_A)}


def test_ollama_backend_and_backend_proposer_keep_native_usage_verbatim():
    raw = {
        "model": "qwen2.5:7b",
        "message": {"content": "ok"},
        **USAGE_A,
        "session_token": 8675309,
    }
    generated = _ollama_chat(raw)
    assert generated["usage"] == USAGE_A

    proposed = BackendProposer(_FixedBackend(generated), extract=False).generate(
        "prompt", seed=7, temperature=0, max_new_tokens=8,
    )
    assert proposed.usage == USAGE_A


def test_missing_ollama_usage_stays_unknown_without_synthesized_fields():
    generated = _ollama_chat({"model": "qwen2.5:7b", "message": {"content": "ok"}})
    assert "usage" not in generated

    proposed = BackendProposer(_FixedBackend(generated), extract=False).generate(
        "prompt", seed=7, temperature=0, max_new_tokens=8,
    )
    assert proposed.usage is None


@pytest.mark.parametrize(("field", "bad"), [
    ("prompt_eval_count", True),
    ("eval_count", -1),
    ("prompt_eval_duration", 1.5),
    ("total_duration", "99"),
])
def test_invalid_ollama_usage_keeps_fixed_refusal_without_coercion(field, bad):
    raw = {"model": "qwen2.5:7b", "message": {"content": "ok"}, **USAGE_A, field: bad}
    generated = _ollama_chat(raw)

    assert generated["usage"]["native_usage_refused"].startswith("OLLAMA_USAGE_INVALID")
    assert generated["usage"].get(field) != bad
    assert "total_tokens" not in generated["usage"]


def test_local_router_records_indexed_usage_events_for_each_inner_call(tmp_path):
    result, backend = _router(tmp_path, _tool(USAGE_A), _final("done", USAGE_B))

    local_events = [
        event for event in result.tool_trace
        if event.get("source") == "local_endpoint_inner"
        and event.get("type") == "usage.observed"
    ]
    assert result.execution_state == "returned"
    assert backend.calls == 2
    assert [event["inner_call"] for event in local_events] == [1, 2]
    assert [event["usage"] for event in local_events] == [USAGE_A, USAGE_B]
    assert result.usage == {"inner_calls": 2, "per_call": [USAGE_A, USAGE_B],
                            "aggregate": _aggregate()}
    assert inner_source(result.tool_trace) == "local_endpoint_inner"
    assert usage_records_from_trace(result.tool_trace, "local_endpoint_inner") == [USAGE_A, USAGE_B]
    assert recheck_inner_usage(result.tool_trace, result.usage) == {
        "verified": True, "recomputed": result.usage}


@pytest.mark.parametrize(("second", "reason"), [
    (_final("done"), "USAGE_ABSENT"),
    (_final("done", {"prompt_eval_count": 2}), "USAGE_KEY_MISMATCH"),
    (_final("done", {"prompt_eval_count": 2, "native_usage_refused": "OLLAMA_USAGE_INVALID"}),
     "USAGE_NON_SUMMABLE"),
    (BackendError("second call failed"), "USAGE_ABSENT"),
])
def test_local_router_refuses_incomplete_or_invalid_usage_aggregates(tmp_path, second, reason):
    result, backend = _router(tmp_path, _tool(USAGE_A), second)

    assert backend.calls == 2
    assert result.usage["inner_calls"] == 2
    assert result.usage["per_call"][0] == USAGE_A
    assert result.usage["aggregate"] is None
    assert result.usage["aggregate_refused"].startswith(reason)
    records = usage_records_from_trace(result.tool_trace, "local_endpoint_inner")
    assert records[0] == USAGE_A and len(records) == 2 and (reason != "USAGE_ABSENT" or records[1] is None)
    assert recheck_inner_usage(result.tool_trace, result.usage)["verified"] is True


def test_local_router_usage_trace_tamper_or_aggregate_only_claim_is_refused(tmp_path):
    result, _ = _router(tmp_path, _tool(USAGE_A), _final("done", USAGE_B))
    trace = [dict(event) for event in result.tool_trace]
    victim = next(event for event in trace if event.get("source") == "local_endpoint_inner")
    victim["usage"] = {**victim["usage"], "eval_count": victim["usage"]["eval_count"] + 1}

    assert recheck_inner_usage(trace, result.usage)["usage_cell_refused"].startswith(
        "USAGE_RECOMPUTE_MISMATCH")
    aggregate_only = {"inner_calls": 2, "aggregate": _aggregate()}
    assert recheck_inner_usage(result.tool_trace, aggregate_only)["usage_cell_refused"].startswith(
        "USAGE_RECOMPUTE_MISMATCH")


def _manifest(source: Path):
    prompt = "prompt\n"
    input_hash = hashlib.sha256((source / "x").read_bytes()).hexdigest()
    return {
        "task_set_id": "set",
        "task_rows": [{
            "task_id": "agt-001-task",
            "raw_prompt": prompt,
            "raw_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "input_sha256s": {"x": input_hash},
            "required_inputs": ["x"],
            "expected_artifacts": ["result.json"],
            "oracle": {"expected_artifacts": ["result.json"]},
        }],
        "provider_specs": [{
            "provider_role": "local_14b",
            "harness_id": "local_endpoint",
            "adapter_id": "openai_compatible_local/v1",
            "model_id": "flywheel-local-coder-14b",
            "model_display_name": "Local 14B",
            "requested_model_reference": "local:14b",
        }],
    }


def _runtime():
    return {"runtime_rows": [{"provider_role": "local_14b", "focused_run_ready": True,
                              "blocking_gates": [], "endpoint_profile_matches": [],
                              "endpoint_gate_matches": []}]}


def test_malformed_artifact_envelope_retains_verified_local_usage(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "x").write_text("evidence", encoding="utf-8")
    backend = _ScriptedBackend(_tool(USAGE_A), _final('{"not_artifacts":true}', USAGE_B))
    adapter = LocalRouterAdapter("local_14b", _profile(), backend_factory=lambda *_: backend)

    run = execute_cross_harness_manifest(
        _manifest(source), _runtime(), {"local_14b": adapter},
        artifact_root=tmp_path / "artifacts", source_root=source, run_id="run",
        phase="local", selectors=["agt-001"], roles=["local_14b"], repetitions=1,
    )

    row = run["rows"][0]
    assert row["execution_state"] == "malformed"
    assert row["oracle_state"] == "not_run"
    assert row["metrics"]["usage"]["aggregate"] == _aggregate()
    assert row["usage_verification"] == {"verified": True,
                                         "recomputed": row["metrics"]["usage"]}
    assert Path(row["raw_output_path"]).read_text(encoding="utf-8") == '{"not_artifacts":true}'


def test_codex_inner_usage_source_stays_codex_inner(tmp_path):
    def event(usage):
        return json.dumps({"type": "turn.completed", "model": "spark", "usage": usage})
    outputs = [
        ProcessOutcome(0, "\n".join((event(USAGE_A), json.dumps(
            {"type": "item.completed", "item": {"type": "agent_message",
                                                "text": 'TOOL read_file {"path":"x"}'}}))), "", 1, False),
        ProcessOutcome(0, "\n".join((event(USAGE_B), json.dumps(
            {"type": "item.completed", "item": {"type": "agent_message",
                                                "text": "done"}}))), "", 1, False),
    ]
    (tmp_path / "x").write_text("evidence", encoding="utf-8")
    adapter = FlywheelRouterAdapter(
        runner=lambda *a, **k: outputs.pop(0),
        executable_resolver=lambda: "codex.cmd",
        proposer_invocations_max=None,
    )

    result = adapter.execute(AttemptRequest(
        "run", "spark", "set", "agt-001-task", "prompt", "a" * 64,
        "flywheel_harness", "flywheel", "flywheel_router/v1", "spark", "spark",
        tmp_path, "b" * 64, {}, SHARED_TOOL_POLICY, "c" * 64, 1,
        "cold_declared", 3, tmp_path,
    ))

    assert inner_source(result.tool_trace) == "codex_inner"
    assert "local_endpoint_inner" not in {event.get("source") for event in result.tool_trace}
    assert usage_records_from_trace(result.tool_trace) == [USAGE_A, USAGE_B]
