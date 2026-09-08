import base64
import hashlib
import json

from harness import acceptance_criteria as AC
from harness.cross_harness_adapters import LocalRouterAdapter
from harness.cross_harness_artifacts import canonical_sha256
from harness.cross_harness_executor import SHARED_TOOL_POLICY
from harness.cross_harness_types import AttemptRequest
from harness.local_agent import OllamaBackend
from harness.local_loop import run_agent
from harness.local_session import SessionLedger
from harness.local_tools import ToolExecutor, ToolGate
from harness.cross_harness_usage import usage_records_from_trace
from harness.structured_finalizer import local_structured_finalizer_factory


class FakeAgent:
    def __init__(self, replies):
        self.system = "base system"
        self.replies = list(replies)
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        text = self.replies.pop(0) if self.replies else "done"
        return {"content": [{"text": text}], "backend": "stub"}


def _finalizer(return_text="finalized"):
    calls = []

    def finalize(ctx):
        calls.append(dict(ctx))
        return {"state": "returned", "selected_text": return_text,
                "evidence": {"request_sha256": "r" * 64}}

    return finalize, calls


def test_finalizer_waits_for_rescued_tool_path_then_records_candidate_state(tmp_path):
    (tmp_path / "x").write_text("evidence", encoding="utf-8")
    agent = FakeAgent(['TOOL: read_file {"path":"x"}', "candidate"])
    finalize, calls = _finalizer("finalized")
    ledger = SessionLedger()

    result = run_agent(agent, "inspect", ToolExecutor(root=str(tmp_path)), ledger,
                       max_steps=3, finalize_candidate=finalize)

    assert result["final"] == "finalized"
    assert len(calls) == 1
    assert calls[0]["candidate_text"] == "candidate"
    assert calls[0]["candidate_state"] == "eligible_no_test_no_criteria"
    assert "TOOL RESULTS" in agent.sent[1]
    entries = [e for e in ledger.entries if e.kind == "structured_finalization"]
    assert json.loads(entries[0].content)["state"] == "returned"


def test_finalizer_excludes_failing_criteria_denied_exec_and_max_steps(tmp_path):
    specs = [{"id": "docs", "description": "docs exist", "oracle": "human"}]
    criteria = AC.new_criteria(specs)
    finalize, calls = _finalizer()
    run_agent(FakeAgent(["candidate", "candidate"]), "x", ToolExecutor(root=str(tmp_path)),
              SessionLedger(), max_steps=2, criteria=criteria,
              finalize_candidate=finalize)
    assert calls == []

    denied = run_agent(FakeAgent(["candidate"]), "x", ToolExecutor(root=str(tmp_path)),
                       SessionLedger(), max_steps=1, test_cmd="pytest -q",
                       finalize_candidate=finalize)
    assert "test gate" in denied["note"]
    assert calls == []

    looping = FakeAgent(['TOOL list_dir {"path":"."}'])
    exhausted = run_agent(looping, "x", ToolExecutor(root=str(tmp_path)),
                          SessionLedger(), max_steps=1,
                          finalize_candidate=finalize)
    assert exhausted["final"] == "[max_steps reached without a final answer]"
    assert calls == []


def _schema():
    return {"type": "object", "required": ["artifacts"],
            "properties": {"artifacts": {"type": "object"}}}


def _cap(state="supported"):
    return {"state": state, "transport": "ollama_chat_format_json_schema",
            "schema_limits": "basic_json_schema_only",
            "evidence": "profile_declared"}


def _profile(capability=None):
    profile = {"profile_id": "local-14b", "backend": "ollama", "model": "14B",
               "model_ref": "ollama:qwen2.5:7b",
               "endpoint_url": "http://127.0.0.1:11434",
               "supports_agentic_workflow": True, "root_exists": True}
    if capability is not None:
        profile["structured_final_output"] = capability
    return {**profile, "profile_sha256": canonical_sha256(profile)}


def _policy(**overrides):
    cfg = {"enabled": True, "schema": _schema(), "system": "finalize only",
           "max_output_tokens": 64, "context_max_bytes": 20000}
    cfg.update(overrides)
    policy = dict(SHARED_TOOL_POLICY)
    policy.update({"max_steps": 1, "max_output_tokens": 64,
                   "structured_final_output": cfg})
    return policy


def _request(root, policy):
    return AttemptRequest(
        "run", "local", "set", "agt-001-task", "prompt", "a" * 64,
        "local_14b", "local_endpoint", "openai_compatible_local/v1",
        "flywheel-local-coder-14b", "ollama:qwen2.5:7b", root,
        "b" * 64, {}, policy, canonical_sha256(policy), 1,
        "cold_declared", 3, root,
    )


def _usage(n):
    return {"prompt_eval_count": n, "prompt_eval_cached_count": 0,
            "eval_count": n + 1, "prompt_eval_duration": n + 2,
            "eval_duration": n + 3, "load_duration": n + 4,
            "total_duration": n + 5}


def _reply(text, *, model="qwen2.5:7b", done=True, reason="stop", usage=None):
    out = {"model": model, "done": done, "done_reason": reason,
           "message": {"content": text}}
    if usage:
        out.update(usage)
    return 200, out


class ScriptedTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.bodies = []
        self.raw_bodies = []
        self.timeouts = []

    def __call__(self, method, url, body, timeout):
        self.timeouts.append(timeout)
        if body is not None:
            self.raw_bodies.append(body)
            self.bodies.append(json.loads(body))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _execute(tmp_path, policy, transport, capability=None):
    backend = OllamaBackend(model="ollama:qwen2.5:7b", transport=transport)
    adapter = LocalRouterAdapter("local_14b", _profile(capability),
                                 backend_factory=lambda *_: backend)
    return adapter.execute(_request(tmp_path, policy))


def _finalizer_events(result):
    return [e for e in result.tool_trace if e.get("type") == "structured_finalization"]


def test_local_router_sends_schema_only_on_finalizer_and_counts_usage(tmp_path):
    transport = ScriptedTransport(_reply("already valid", usage=_usage(1)),
                                  _reply("semantic regression", usage=_usage(10)))

    result = _execute(tmp_path, _policy(), transport, _cap())

    assert result.output_text == "semantic regression"
    assert len(transport.bodies) == 2
    assert "format" not in transport.bodies[0]
    assert transport.bodies[1]["format"] == _schema()
    assert "already valid" in json.dumps(transport.bodies[1]["messages"])
    assert result.resource_observation["inner_call_count"] == 2
    assert result.resource_observation["structured_final_output"]["total_provider_invocations_max"] == 2
    assert usage_records_from_trace(result.tool_trace, "local_endpoint_inner") == [_usage(1), _usage(10)]
    event = _finalizer_events(result)[0]
    assert event["state"] == "returned"
    assert event["evidence"]["request_body_sha256"] == hashlib.sha256(
        transport.raw_bodies[1]).hexdigest()
    assert event["evidence"]["raw_output_sha256"]
    assert event["evidence"]["remaining_invocations_before_call"] == 1
    assert event["evidence"]["native_usage"] == _usage(10)
    assert "request_body_b64" not in event["evidence"]


def test_unconstrained_and_schema_finalizer_differ_only_by_format_field(tmp_path):
    schema_transport = ScriptedTransport(_reply("candidate", usage=_usage(1)),
                                         _reply("schema final", usage=_usage(10)))
    _execute(tmp_path, _policy(), schema_transport, _cap())

    free_policy = _policy(format_mode="unconstrained", schema=None)
    free_transport = ScriptedTransport(_reply("candidate", usage=_usage(1)),
                                       _reply("free final", usage=_usage(10)))
    free_result = _execute(tmp_path, free_policy, free_transport, _cap("unsupported"))

    schema_body = dict(schema_transport.bodies[1])
    assert schema_body.pop("format") == _schema()
    assert "format" not in free_transport.bodies[1]
    assert schema_body == free_transport.bodies[1]
    assert free_result.output_text == "free final"
    assert _finalizer_events(free_result)[0]["evidence"]["format_mode"] == "unconstrained"


def test_private_payload_retention_is_explicit_and_exact(tmp_path):
    transport = ScriptedTransport(_reply("candidate", usage=_usage(1)),
                                  _reply("private final", usage=_usage(10)))
    result = _execute(tmp_path, _policy(retain_private_finalizer_payloads=True),
                      transport, _cap())
    evidence = _finalizer_events(result)[0]["evidence"]

    assert base64.b64decode(evidence["request_body_b64"]) == transport.raw_bodies[1]
    assert base64.b64decode(evidence["candidate_text_b64"]).decode() == "candidate"
    assert base64.b64decode(evidence["raw_output_b64"]).decode() == "private final"


def test_context_overflow_and_budget_exhaustion_do_not_fallback_to_candidate(tmp_path):
    too_small = ScriptedTransport(_reply("candidate", usage=_usage(1)))
    context_result = _execute(tmp_path, _policy(context_max_bytes=10), too_small, _cap())
    assert context_result.output_text == ""
    assert len(too_small.bodies) == 1
    assert _finalizer_events(context_result)[0]["state"] == "context_not_admitted"

    class NoBudget:
        calls = 1
        max_calls = 1
        inner = object()

        def remaining_seconds(self):
            return 1.0

        def remaining_calls(self):
            return 0

    factory, resource, total = local_structured_finalizer_factory(
        _profile(_cap()), _request(tmp_path, _policy()))
    finalize, returned_resource = factory(NoBudget())
    out = finalize({"candidate_text": "candidate", "candidate_state": "eligible",
                    "candidate_sha256": "c" * 64, "step": 1, "history": [],
                    "pre_finalizer_checkpoint": "checkpoint"})
    assert out["state"] == "budget_exhausted"
    assert resource == returned_resource
    assert total == 2


def test_wrong_model_and_length_stop_are_evidence_not_selected_output(tmp_path):
    wrong_model = ScriptedTransport(_reply("candidate", usage=_usage(1)),
                                    _reply("do not score", model="other:7b"))
    result = _execute(tmp_path, _policy(), wrong_model, _cap())
    event = _finalizer_events(result)[0]
    assert result.output_text == ""
    assert event["state"] == "model_mismatch"
    assert event["evidence"]["raw_output_sha256"]

    length_stop = ScriptedTransport(_reply("candidate", usage=_usage(1)),
                                    _reply("truncated", reason="length"))
    result = _execute(tmp_path, _policy(), length_stop, _cap())
    assert result.output_text == ""
    assert _finalizer_events(result)[0]["state"] == "generation_length_stop"


def test_unsupported_profile_and_unavailable_adapter_do_not_spend_schema_call(tmp_path):
    unsupported = ScriptedTransport(_reply("candidate", usage=_usage(1)))
    result = _execute(tmp_path, _policy(), unsupported, _cap("unsupported"))
    assert result.output_text == ""
    assert len(unsupported.bodies) == 1
    assert _finalizer_events(result)[0]["state"] == "unsupported"

    backend = OllamaBackend(model="ollama:qwen2.5:7b", transport=unsupported)
    adapter = LocalRouterAdapter("other_role", _profile(_cap()),
                                 backend_factory=lambda *_: backend)
    unavailable = adapter.execute(_request(tmp_path, _policy()))
    assert unavailable.execution_state == "unavailable"
    assert len(unsupported.bodies) == 1
