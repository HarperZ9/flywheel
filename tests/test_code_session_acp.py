"""Falsifiers for `flywheel code --acp`: an editor drives a session over ACP."""
import os
import threading

from harness.acp_wire import AcpFraming
from harness.code_session.acp_agent import serve
from harness.code_session.backends import build_agent
from harness.code_session.session import new_session
from harness.jsonrpc_peer import Peer
from tests.test_code_session import ScriptBackend, _bare_runner


class Editor:
    """The client side: records updates, answers permission requests."""

    def __init__(self, answer="allow"):
        self.updates, self.asked, self.answer = [], [], answer

    def on_request(self, method, params):
        assert method == "session/request_permission"
        self.asked.append(params)
        if self.answer == "cancelled":
            return {"outcome": {"outcome": "cancelled"}}
        return {"outcome": {"outcome": "selected", "optionId": self.answer}}

    def on_notification(self, method, params):
        if method == "session/update":
            self.updates.append(params["update"])


def _connect(tmp_path, replies, mode="ask", answer="allow"):
    a_in_r, a_in_w = os.pipe()          # editor -> agent
    a_out_r, a_out_w = os.pipe()        # agent -> editor
    backend = ScriptBackend(replies)

    def make_session(cwd):
        return new_session(build_agent([backend]), cwd, mode=mode, runner=_bare_runner)
    agent_in, agent_out = os.fdopen(a_in_r, "rb"), os.fdopen(a_out_w, "wb")
    t = threading.Thread(target=serve, args=(make_session, agent_in, agent_out), daemon=True)
    t.start()
    editor = Editor(answer)
    peer = Peer(os.fdopen(a_in_w, "wb"), os.fdopen(a_out_r, "rb"), framing=AcpFraming(),
                handler=editor, name="editor").start()
    return peer, editor, backend


def test_initialize_new_session_and_a_prompt_that_edits_with_permission(tmp_path):
    peer, editor, _ = _connect(tmp_path, [
        "I will write the file.\nTOOL write_file {\"path\": \"hi.txt\", \"content\": \"hello\"}",
        "Wrote hi.txt."])
    init = peer.call("initialize", {"protocolVersion": 1, "clientCapabilities": {}}, timeout=10)
    assert init["protocolVersion"] == 1 and init["authMethods"] == []
    sid = peer.call("session/new", {"cwd": str(tmp_path), "mcpServers": []},
                    timeout=10)["sessionId"]
    out = peer.call("session/prompt", {"sessionId": sid, "prompt": [
        {"type": "text", "text": "write hi.txt"}]}, timeout=30)
    assert out == {"stopReason": "end_turn"}
    assert (tmp_path / "hi.txt").read_text() == "hello"
    kinds = [u["sessionUpdate"] for u in editor.updates]
    assert kinds.count("tool_call") == 1 and kinds.count("tool_call_update") == 1
    call = next(u for u in editor.updates if u["sessionUpdate"] == "tool_call")
    done = next(u for u in editor.updates if u["sessionUpdate"] == "tool_call_update")
    assert call["kind"] == "edit" and done["status"] == "completed"
    assert editor.asked[0]["toolCall"]["toolCallId"] == call["toolCallId"]
    texts = [u["content"]["text"] for u in editor.updates
             if u["sessionUpdate"] == "agent_message_chunk"]
    assert "I will write the file." in texts[0] and "TOOL" not in "".join(texts)
    peer.close()


def test_a_rejected_permission_leaves_the_file_alone(tmp_path):
    peer, editor, _ = _connect(tmp_path, [
        'TOOL write_file {"path": "no.txt", "content": "x"}', "ok, not writing"],
        answer="reject")
    peer.call("initialize", {"protocolVersion": 1}, timeout=10)
    sid = peer.call("session/new", {"cwd": str(tmp_path), "mcpServers": []}, timeout=10)["sessionId"]
    peer.call("session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": "w"}]},
              timeout=30)
    assert not (tmp_path / "no.txt").exists()
    done = next(u for u in editor.updates if u["sessionUpdate"] == "tool_call_update")
    assert done["status"] == "failed"
    peer.close()


def test_cancel_stops_the_turn_with_cancelled(tmp_path):
    peer, editor, backend = _connect(tmp_path, ["unused"], mode="auto", answer="allow")
    peer.call("initialize", {"protocolVersion": 1}, timeout=10)
    sid = peer.call("session/new", {"cwd": str(tmp_path), "mcpServers": []}, timeout=10)["sessionId"]
    peer.notify("session/cancel", {"sessionId": sid})
    import time
    time.sleep(0.3)
    # a cancel that lands before the prompt is cleared by the new prompt; cancel
    # mid-turn by answering the first model call slowly instead
    original = backend.chat

    def slow(messages, **kw):
        peer.notify("session/cancel", {"sessionId": sid})
        time.sleep(0.3)
        return original(messages, **kw)
    backend.replies = ['TOOL list_dir {"path": "."}', "never"]
    backend.chat = slow
    out = peer.call("session/prompt", {"sessionId": sid, "prompt": [
        {"type": "text", "text": "look"}]}, timeout=30)
    assert out == {"stopReason": "cancelled"}
    peer.close()


def test_unknown_session_and_method_are_errors_not_hangs(tmp_path):
    from harness.jsonrpc_peer import PeerError
    peer, _, _ = _connect(tmp_path, [])
    for method, params in (("session/prompt", {"sessionId": "nope", "prompt": []}),
                           ("session/load", {})):
        try:
            peer.call(method, params, timeout=10)
        except PeerError:
            pass
        else:
            raise AssertionError(f"{method} should fail")
    peer.close()
