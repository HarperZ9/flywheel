import json

from harness import acceptance_criteria as AC
from harness.local_loop import run_agent
from harness.local_session import SessionLedger
from harness.local_tools import ToolExecutor

from test_structured_finalizer import (
    FakeAgent,
    ScriptedTransport,
    _cap,
    _execute,
    _finalizer,
    _finalizer_events,
    _policy,
    _profile,
    _request,
    _reply,
    _usage,
)


def test_criteria_satisfied_candidate_state_is_distinct_from_no_criteria(tmp_path):
    specs = [{"id": "done", "description": "already done", "oracle": "human"}]
    criteria = AC.new_criteria(specs)
    AC.apply_oracle_result(criteria, "done", "human", True, {"fixture": "prepassed"})
    finalize, calls = _finalizer("criteria final")

    result = run_agent(FakeAgent(["candidate"]), "x", ToolExecutor(root=str(tmp_path)),
                       SessionLedger(), max_steps=1, criteria=criteria,
                       finalize_candidate=finalize)

    assert result["final"] == "criteria final"
    assert calls[0]["candidate_state"] == "eligible_criteria_satisfied"


class MalformedJsonTransport(ScriptedTransport):
    def __call__(self, method, url, body, timeout):
        if len(self.bodies) == 1:
            self.timeouts.append(timeout)
            self.raw_bodies.append(body)
            self.bodies.append(json.loads(body))
            raise json.JSONDecodeError("unterminated", "{", 1)
        return super().__call__(method, url, body, timeout)


def test_finalizer_malformed_transport_json_records_denominator_event(tmp_path):
    transport = MalformedJsonTransport(_reply("candidate", usage=_usage(1)))

    result = _execute(tmp_path, _policy(), transport, _cap())

    assert result.execution_state == "returned"
    assert result.output_text == ""
    event = _finalizer_events(result)[0]
    assert event["state"] == "provider_json_invalid"
    assert event["failure_class"] == "provider_json_invalid"
    assert len(transport.bodies) == 2


def test_finalizer_non_object_message_is_missing_content_not_internal_error(tmp_path):
    transport = ScriptedTransport(_reply("candidate", usage=_usage(1)),
                                  (200, {"model": "qwen2.5:7b", "done": True,
                                         "done_reason": "stop", "message": "bad"}))

    result = _execute(tmp_path, _policy(), transport, _cap())

    assert result.execution_state == "returned"
    assert result.output_text == ""
    event = _finalizer_events(result)[0]
    assert event["state"] == "missing_content"
    assert event["failure_class"] == "missing_content"


def test_max_output_tokens_trace_is_numeric(tmp_path):
    transport = ScriptedTransport(_reply("candidate", usage=_usage(1)),
                                  _reply("final", usage=_usage(10)))

    result = _execute(tmp_path, _policy(max_output_tokens="64"), transport, _cap())

    value = _finalizer_events(result)[0]["evidence"]["max_output_tokens"]
    assert type(value) is int
    assert value == 1024


def test_real_local_http_malformed_json_becomes_finalizer_denominator(monkeypatch, tmp_path):
    import harness.cross_harness_adapters as adapters

    class Response:
        def __init__(self, raw):
            self.status = 200
            self.raw = raw

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _limit):
            return self.raw

    class Opener:
        calls = 0

        def open(self, request, timeout):
            self.calls += 1
            if self.calls == 1:
                body = {**_reply("candidate", usage=_usage(1))[1],
                        "model": "qwen2.5:7b"}
                return Response(json.dumps(body).encode())
            return Response(b'{')

    opener = Opener()
    monkeypatch.setattr(adapters.urllib.request, "build_opener",
                        lambda *args, **kwargs: opener)
    backend = adapters.OllamaBackend(model="ollama:qwen2.5:7b",
                                     transport=adapters._local_http)
    adapter = adapters.LocalRouterAdapter("local_14b", _profile(_cap()),
                                          backend_factory=lambda *_: backend)
    request = _request(tmp_path, _policy())

    result = adapter.execute(request)

    assert result.execution_state == "returned"
    assert result.output_text == ""
    event = _finalizer_events(result)[0]
    assert event["state"] == "provider_json_invalid"
    assert event["failure_class"] == "provider_json_invalid"
    assert result.resource_observation["inner_call_count"] == 2
