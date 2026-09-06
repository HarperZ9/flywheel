"""Driving a real ACP conversation against a hand-written agent."""
import json

import pytest

from harness.acp_client import AuthRequired, AcpClient, VersionUnsupported
from harness.acp_connection import RECEIVED, SENT
from harness.acp_policy import AllowAll, DenyAll, WorkspacePolicy
from harness.acp_turn import END_TURN, REFUSAL
from tests.acp_fake_agent import FakeAgent, _Refuse, connect


def opened(agent, **kwargs):
    client = connect(agent, **kwargs)
    client.initialize()
    client.new_session()
    return client


def test_a_version_2_agent_ends_its_turn_with_an_idle_update():
    with opened(FakeAgent(version=2)) as client:
        assert client.protocol_version == 2
        turn = client.prompt("hello")
    assert turn.stop_reason == END_TURN
    assert turn.text == "done: hello"
    assert turn.thinking == "thinking"
    assert turn.complete is True


def test_a_version_1_agent_ends_its_turn_in_the_prompt_response():
    agent = FakeAgent(version=1)
    with opened(agent) as client:
        assert client.protocol_version == 1
        turn = client.prompt("hello")
    assert turn.stop_reason == END_TURN
    assert turn.text == "done: hello"


def test_a_version_1_agent_that_rejects_the_v2_fields_gets_the_v1_fields():
    agent = FakeAgent(version=1, strict=True)
    with opened(agent) as client:
        assert client.protocol_version == 1
    assert "clientCapabilities" in agent.initialize_params
    assert "capabilities" not in agent.initialize_params
    attempts = [m for m in agent.received if m.get("method") == "initialize"]
    assert len(attempts) == 2


def test_a_turn_that_finishes_before_its_own_response_lands_is_still_collected():
    with opened(FakeAgent(version=2, respond_first=True)) as client:
        turn = client.prompt("hello")
    assert turn.stop_reason == END_TURN
    assert turn.text == "done: hello"


def test_an_agent_speaking_an_unknown_major_version_is_refused_by_name():
    client = connect(FakeAgent(version=99))
    with pytest.raises(VersionUnsupported) as caught:
        client.initialize()
    assert "99" in str(caught.value)
    client.close()


def test_a_refusal_comes_back_as_a_refusal_not_as_an_error():
    agent = FakeAgent(on_prompt=lambda a, s, p: REFUSAL)
    with opened(agent) as client:
        turn = client.prompt("something it will not do")
    assert turn.refused is True
    assert turn.complete is False


def test_the_client_advertises_only_what_its_policy_will_actually_do(tmp_path):
    agent = FakeAgent()
    with opened(agent, policy=DenyAll()):
        pass
    assert agent.initialize_params["capabilities"]["fs"] == {
        "readTextFile": False, "writeTextFile": False}

    agent = FakeAgent()
    with opened(agent, policy=WorkspacePolicy(tmp_path, allow_writes=True)):
        pass
    assert agent.initialize_params["capabilities"]["fs"] == {
        "readTextFile": True, "writeTextFile": True}


def test_the_client_never_advertises_a_terminal_it_does_not_have():
    agent = FakeAgent()
    with opened(agent, policy=AllowAll()):
        pass
    assert agent.initialize_params["capabilities"]["terminal"] is False


def test_a_permission_request_is_answered_by_the_policy(tmp_path):
    asked = {}

    def prompt(agent, session_id, _):
        asked["answer"] = agent.call("session/request_permission", {
            "sessionId": session_id, "title": "Delete everything",
            "options": [{"optionId": "y", "name": "Yes", "kind": "allow_once"},
                        {"optionId": "n", "name": "No", "kind": "reject_once"}]})
        return END_TURN

    policy = DenyAll()
    with opened(FakeAgent(on_prompt=prompt), policy=policy) as client:
        client.prompt("go")
    assert asked["answer"]["result"]["outcome"]["optionId"] == "n"
    assert policy.decisions[-1].allowed is False
    assert policy.decisions[-1].detail == "Delete everything"


def test_a_file_read_the_policy_allows_reaches_the_agent(tmp_path):
    (tmp_path / "note.txt").write_text("from disk\n", encoding="utf-8")
    seen = {}

    def prompt(agent, session_id, _):
        seen["answer"] = agent.call("fs/read_text_file", {
            "sessionId": session_id, "path": str(tmp_path / "note.txt")})
        return END_TURN

    with opened(FakeAgent(on_prompt=prompt),
                policy=WorkspacePolicy(tmp_path)) as client:
        client.prompt("read it")
    assert seen["answer"]["result"] == {"content": "from disk\n"}


def test_a_file_read_the_policy_refuses_comes_back_as_an_error(tmp_path):
    seen = {}

    def prompt(agent, session_id, _):
        seen["answer"] = agent.call("fs/read_text_file", {
            "sessionId": session_id, "path": str(tmp_path / "secret.txt")})
        return END_TURN

    with opened(FakeAgent(on_prompt=prompt), policy=DenyAll()) as client:
        client.prompt("read it")
    assert "error" in seen["answer"]
    assert "result" not in seen["answer"]


def test_a_method_this_client_does_not_implement_answers_method_not_found():
    seen = {}

    def prompt(agent, session_id, _):
        seen["answer"] = agent.call("terminal/create", {
            "sessionId": session_id, "command": "rm"})
        return END_TURN

    with opened(FakeAgent(on_prompt=prompt), policy=AllowAll()) as client:
        client.prompt("run something")
    assert seen["answer"]["error"]["code"] == -32601


def test_the_observer_sees_every_frame_in_both_directions():
    frames = []
    with opened(FakeAgent(), observer=lambda way, msg: frames.append(
            (way, msg))) as client:
        client.prompt("hello")
    ways = [way for way, _ in frames]
    assert SENT in ways and RECEIVED in ways
    methods = [msg.get("method") for _, msg in frames if "method" in msg]
    assert "initialize" in methods
    assert "session/prompt" in methods
    assert methods.count("session/update") == 3


def test_the_observer_is_handed_the_frame_and_not_a_summary_of_it():
    frames = []
    with opened(FakeAgent(), observer=lambda way, msg: frames.append(
            (way, msg))) as client:
        client.prompt("hello")
    for way, message in frames:
        assert message["jsonrpc"] == "2.0"
        json.dumps(message)  # every recorded frame is what crossed the wire


def test_an_update_outside_any_awaited_turn_is_kept_rather_than_dropped():
    def prompt(agent, session_id, _):
        agent.update("some-other-session", sessionUpdate="agent_message_chunk",
                     content={"type": "text", "text": "stray"})
        return END_TURN

    with opened(FakeAgent(on_prompt=prompt)) as client:
        client.prompt("go")
        assert len(client.stray_updates) == 1
        assert client.stray_updates[0]["sessionId"] == "some-other-session"


def test_prompting_before_a_session_exists_is_refused_by_name():
    client = connect(FakeAgent())
    client.initialize()
    with pytest.raises(ValueError):
        client.prompt("hello")
    client.close()


def test_an_auth_required_error_names_what_the_operator_has_to_do():
    class NeedsAuth(FakeAgent):
        def _answer(self, method, params, call_id):
            if method == "session/new":
                raise _Refuse(-32000, "sign in first")
            return super()._answer(method, params, call_id)

    client = connect(NeedsAuth())
    client.initialize()
    with pytest.raises(AuthRequired) as caught:
        client.new_session()
    assert "sign in" in str(caught.value)
    client.close()


def test_an_agent_that_answers_new_session_without_an_id_is_refused():
    class NoId(FakeAgent):
        def _answer(self, method, params, call_id):
            if method == "session/new":
                return {}
            return super()._answer(method, params, call_id)

    client = connect(NoId())
    client.initialize()
    with pytest.raises(ValueError):
        client.new_session()
    client.close()


def test_cancel_reaches_the_agent_as_a_notification():
    agent = FakeAgent()
    with opened(agent) as client:
        client.cancel()
        assert agent.cancelled.wait(5.0)
    sent = [m for m in agent.received if m.get("method") == "session/cancel"]
    assert sent and "id" not in sent[0]


def test_a_turn_that_never_ends_times_out_instead_of_hanging():
    def prompt(agent, session_id, _):
        return ""  # idle with no stop reason: the turn never closes

    with opened(FakeAgent(on_prompt=prompt)) as client:
        with pytest.raises(TimeoutError):
            client.prompt("go", timeout=0.5)


def test_closing_wakes_a_caller_waiting_on_the_agent():
    import threading

    started = threading.Event()

    def prompt(agent, session_id, _):
        started.set()
        threading.Event().wait(10)
        return END_TURN

    client = opened(FakeAgent(on_prompt=prompt))
    failures = []

    def ask():
        try:
            client.prompt("go", timeout=10)
        except BaseException as exc:  # noqa: BLE001 - recorded, then asserted
            failures.append(exc)

    caller = threading.Thread(target=ask, daemon=True)
    caller.start()
    assert started.wait(5.0)
    client.close()
    caller.join(5.0)
    assert failures and not caller.is_alive()


def test_spawn_reports_what_a_failed_agent_wrote_to_stderr(tmp_path):
    import sys

    script = tmp_path / "broken.py"
    script.write_text(
        "import sys\nsys.stderr.write('cannot start\\n')\nraise SystemExit(2)\n",
        encoding="utf-8")
    client = AcpClient.spawn([sys.executable, str(script)], cwd=tmp_path)
    with pytest.raises(Exception):
        client.initialize(timeout=10)
    client.close()
    assert "cannot start" in client.stderr
    assert client.process.returncode == 2
