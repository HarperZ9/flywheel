"""test_mcp_http.py -- the transport for a lane that is already running.

Every other lane is a subprocess flywheel spawns. A board on the open web is
not, so the client reaches it over one POST per JSON-RPC message. What is under
test here is the part a fake stdio transport could never catch: that a 202 with
no body queues nothing, that a JSON-RPC error carried on a 4xx is read rather
than discarded as "HTTP 400", and that a client handed a spec with a url picks
this transport without anything downstream knowing which one it got.

No socket is opened. `urlopen` is replaced with a recorder, so the assertions
are about the bytes this module would put on the wire and what it does with the
bytes that come back.
"""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from harness import mcp_http
from harness.mcp_client import LaunchSpec, MCPClient, MCPError
from harness.mcp_http import HttpTransport, _sse_messages


class _Resp:
    """The context-manager shape `urlopen` returns."""

    def __init__(self, status: int, body: bytes, headers: "dict | None" = None):
        self.status = status
        self.headers = headers or {"content-type": "application/json"}
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _recorder(monkeypatch, *responses):
    """Answer each POST with the next response; record every request sent."""
    sent = []
    queued = list(responses)

    def fake_urlopen(req, timeout=None):
        sent.append({"url": req.full_url, "headers": dict(req.headers),
                     "body": json.loads(req.data.decode("utf-8"))})
        answer = queued.pop(0) if queued else _Resp(202, b"")
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(mcp_http.urllib.request, "urlopen", fake_urlopen)
    return sent


def _rpc(id_: int, result: dict) -> bytes:
    return json.dumps({"jsonrpc": "2.0", "id": id_, "result": result}).encode()


def test_an_unset_endpoint_is_named_rather_than_parsed():
    # A lane declared but never pointed at a deployment. The message has to say
    # that, not fail somewhere downstream as an unparseable url.
    with pytest.raises(MCPError, match="no endpoint configured"):
        HttpTransport("")


@pytest.mark.parametrize("url", ["ws://board/mcp", "file:///mcp", "board.example/mcp"])
def test_a_url_this_transport_cannot_speak_is_refused_by_name(url):
    with pytest.raises(MCPError, match="not an http"):
        HttpTransport(url)


def test_a_json_reply_is_queued_and_received(monkeypatch):
    _recorder(monkeypatch, _Resp(200, _rpc(1, {"tools": []})))
    t = HttpTransport("http://board.test/mcp")
    t.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert t.receive() == {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}


def test_the_request_offers_both_body_shapes_and_pins_the_protocol(monkeypatch):
    sent = _recorder(monkeypatch, _Resp(200, _rpc(1, {})))
    HttpTransport("http://board.test/mcp").send({"jsonrpc": "2.0", "id": 1, "method": "x"})
    head = {k.lower(): v for k, v in sent[0]["headers"].items()}
    assert "application/json" in head["accept"]
    assert "text/event-stream" in head["accept"]
    assert head["mcp-protocol-version"] == "2025-06-18"


def test_a_notification_gets_202_with_no_body_and_queues_nothing(monkeypatch):
    _recorder(monkeypatch, _Resp(202, b""))
    t = HttpTransport("http://board.test/mcp")
    t.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    # The caller that sent a notification never asks, so an empty queue is
    # correct. A caller that asks anyway is told what the server actually did.
    with pytest.raises(MCPError, match="HTTP 202 carried no JSON-RPC reply"):
        t.receive()


def test_a_jsonrpc_error_on_a_4xx_is_read_not_discarded(monkeypatch):
    body = json.dumps({"jsonrpc": "2.0", "id": 1,
                       "error": {"code": -32600, "message": "batched requests are refused"}})
    err = urllib.error.HTTPError("http://board.test/mcp", 400, "Bad Request",
                                 {"content-type": "application/json"},
                                 io.BytesIO(body.encode()))
    _recorder(monkeypatch, err)
    t = HttpTransport("http://board.test/mcp")
    t.send({"jsonrpc": "2.0", "id": 1, "method": "x"})
    # Without this the failure reads "HTTP 400" and the server's own sentence
    # about what it refused is thrown away.
    assert t.receive()["error"]["message"] == "batched requests are refused"


def test_a_connection_that_never_opened_names_the_endpoint(monkeypatch):
    _recorder(monkeypatch, urllib.error.URLError("connection refused"))
    with pytest.raises(MCPError, match="board.test"):
        HttpTransport("http://board.test/mcp").send({"jsonrpc": "2.0", "id": 1, "method": "x"})


def test_a_body_that_is_not_json_reports_what_arrived(monkeypatch):
    _recorder(monkeypatch, _Resp(200, b"<html>504 gateway timeout</html>"))
    with pytest.raises(MCPError, match="not JSON"):
        HttpTransport("http://board.test/mcp").send({"jsonrpc": "2.0", "id": 1, "method": "x"})


def test_an_event_stream_body_is_parsed_into_its_messages(monkeypatch):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"a": 1}})
    stream = "event: message\ndata: " + payload + "\n\ndata:\ndata: not json at all\n"
    _recorder(monkeypatch, _Resp(200, stream.encode(), {"content-type": "text/event-stream"}))
    t = HttpTransport("http://board.test/mcp")
    t.send({"jsonrpc": "2.0", "id": 1, "method": "x"})
    assert t.receive()["result"] == {"a": 1}
    # The blank and unparseable data lines are dropped, not queued as messages.
    with pytest.raises(MCPError):
        t.receive()


def test_sse_parsing_keeps_message_order():
    body = 'data: {"id": 1}\ndata: {"id": 2}\n'
    assert [m["id"] for m in _sse_messages(body)] == [1, 2]


def test_a_session_handed_out_on_one_reply_comes_back_on_the_next(monkeypatch):
    sent = _recorder(monkeypatch,
                     _Resp(200, _rpc(1, {}), {"content-type": "application/json",
                                              "mcp-session-id": "s-42"}),
                     _Resp(200, _rpc(2, {})))
    t = HttpTransport("http://board.test/mcp")
    t.send({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    t.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    first = {k.lower() for k in sent[0]["headers"]}
    second = {k.lower(): v for k, v in sent[1]["headers"].items()}
    assert "mcp-session-id" not in first
    assert second["mcp-session-id"] == "s-42"


def test_there_is_no_child_process_on_this_side_of_the_wire():
    t = HttpTransport("http://board.test/mcp")
    assert t.stderr_tail() == ""
    assert t.close() is None


def test_a_launch_spec_carrying_a_url_reaches_the_board_over_http(monkeypatch):
    # The dispatch that lets `_probe_lane` stay one code path for both kinds.
    init = {"protocolVersion": "2025-06-18", "serverInfo": {"name": "bulletin"},
            "capabilities": {"tools": {}}}
    sent = _recorder(monkeypatch,
                     _Resp(200, _rpc(1, init)),
                     _Resp(202, b""),
                     _Resp(200, _rpc(2, {"tools": [{"name": "bulletin_status"}]})))
    with MCPClient(LaunchSpec((), url="http://board.test/mcp")) as c:
        assert [t["name"] for t in c.list_tools()] == ["bulletin_status"]
        assert c.server_info["name"] == "bulletin"
    assert {s["url"] for s in sent} == {"http://board.test/mcp"}


def test_a_spec_with_an_argv_still_spawns_a_child(monkeypatch):
    # The negative half: a stdio lane must not be routed onto the wire.
    def never(*a, **k):
        raise AssertionError("a stdio lane was sent over http")

    monkeypatch.setattr(mcp_http.urllib.request, "urlopen", never)
    with pytest.raises((MCPError, OSError)):
        MCPClient(LaunchSpec(("this-command-does-not-exist-9271",))).__enter__()


def _header(sent_request: dict, name: str) -> str:
    """urllib title-cases what it is handed, so read the header case-insensitively."""
    for key, value in sent_request["headers"].items():
        if key.lower() == name:
            return value
    return ""


def test_the_transport_identifies_itself_rather_than_the_library(monkeypatch):
    # urllib signs its own name when nobody sets one, and an edge reads that as an
    # unidentified script. Measured 2026-09-05 against the deployed board: the
    # library default came back 403 with Cloudflare error 1010 before the request
    # reached the worker, while a header naming a real client came back 200. A
    # lane that cannot be reached is not a lane, so the header is not cosmetic.
    sent = _recorder(monkeypatch, _Resp(200, _rpc(1, {"tools": []})))
    t = HttpTransport("http://board.test/mcp")
    t.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    agent = _header(sent[0], "user-agent")
    assert "python-urllib" not in agent.lower(), "the library default is refused at the edge"
    assert "flywheel" in agent, "the header has to name the client a server operator would log"
    assert "https://github.com/HarperZ9/flywheel" in agent, "and where to complain about it"


def test_the_identification_carries_this_distribution_not_a_stranger(monkeypatch):
    # The distribution is flywheel-verify. An unrelated package named "flywheel"
    # is installed in this environment, so asking for the short name reports
    # someone else's version number in our own outbound header.
    from importlib.metadata import PackageNotFoundError, version

    try:
        expected = version("flywheel-verify")
    except PackageNotFoundError:
        expected = "0"
    assert mcp_http._user_agent().startswith(f"flywheel-lanes/{expected} ")


def test_a_caller_can_replace_the_identification(monkeypatch):
    # A workstation reaching a board that wants its own agent string.
    sent = _recorder(monkeypatch, _Resp(200, _rpc(1, {"tools": []})))
    t = HttpTransport("http://board.test/mcp", headers={"user-agent": "custom/9"})
    t.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert _header(sent[0], "user-agent") == "custom/9"
