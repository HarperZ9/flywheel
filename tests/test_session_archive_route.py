"""SP-05, I12: the session import route takes a client and a session id and
nothing else. The gateway resolves the transcript under its own client root,
refuses a file reached through a link, refuses UNC, device, stream and
reserved-name targets before any open, and imports one session per minute."""
import json
import secrets
import time
import urllib.error
import urllib.request

import pytest

from capture_channel_fixture import running_gateway
from import_fixtures import OWNER, SESSION, claude_tree, link_dir
from trace_enc_fakes import StreamTestProvider, using


def _signed(port, token, body: dict):
    from harness.capture_hooks import protocol
    with urllib.request.urlopen(
            f"http://127.0.0.1:{port}{protocol.HELLO_PATH}?v=1&cn={'ab' * 16}", timeout=5) as r:
        hello = json.loads(r.read())
    _, k_c = protocol.derive_keys(token)
    raw = json.dumps(body).encode()
    path = protocol.SESSION_PATH
    header = protocol.auth_header(k_c, "POST", path, raw, int(time.time()),
                                  secrets.token_hex(16), hello["sn"], "127.0.0.1", port)
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=raw, method="POST",
                                     headers={"Authorization": header,
                                              "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    from harness import trace_import_session
    home = tmp_path / "home"
    home.mkdir()
    (home / "owner.ref").write_text(OWNER)
    root, outside, linked = claude_tree(tmp_path)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(root))
    monkeypatch.setattr(trace_import_session, "_LAST", {})
    with using(StreamTestProvider()), running_gateway(home, monkeypatch) as server:
        from harness.capture_hooks.client import read_token
        _archive_on(home)
        yield home, root, outside, linked, server.server_address[1], read_token(home)


def _archive_on(home):
    from harness.trace_capture_settings import adopt, digest, write_file
    from harness.trace_presence import confirm
    from harness.trace_witness import MemorySink
    settings = write_file(home, {"archive_transcripts": "on"})
    adopt(home, OWNER, confirm(home / "state", OWNER, "capture_settings", digest(settings),
                               "archive on"), sink=MemorySink())


def _wait_for_items(home, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = len(_items(home))
        if found:
            return found
        time.sleep(0.05)
    return 0


def _items(home):
    from harness.trace_import_core import ImportStore
    return ImportStore(home, OWNER).item_refs()


def test_a_session_is_imported_by_id(gateway):
    home, _, _, _, port, token = gateway
    status, body = _signed(port, token, {"client": "claude-code", "session_id": SESSION,
                                         "reason": "exit"})
    assert status == 202 and body["queued"] is True
    assert _wait_for_items(home) == 1


@pytest.mark.parametrize("extra", [{"path": "C:/x.jsonl"}, {"transcript_path": "/tmp/x"},
                                   {"owner_ref": "owner_" + "b" * 32}])
def test_a_body_with_a_path_or_owner_field_is_422(gateway, extra):
    _, _, _, _, port, token = gateway
    status, _ = _signed(port, token, {"client": "claude-code", "session_id": SESSION, **extra})
    assert status == 422


@pytest.mark.parametrize("bad", ["../" + SESSION, SESSION + "/x", "C:" + SESSION,
                                 "a\\b", "not-a-uuid", SESSION.upper() + ":stream"])
def test_a_malformed_session_id_is_422(gateway, bad):
    _, _, _, _, port, token = gateway
    assert _signed(port, token, {"client": "claude-code", "session_id": bad})[0] == 422


def test_a_session_reached_through_a_link_is_refused(gateway, tmp_path):
    home, root, outside, _, port, token = gateway
    other = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d"
    (outside / f"{other}.jsonl").write_bytes(b'{"type": "user"}\n')
    if not link_dir(root / "projects" / "linked-project", outside):
        pytest.skip("cannot create a directory link here")
    status, _ = _signed(port, token, {"client": "claude-code", "session_id": other})
    assert status in (404, 422) and _items(home) == []


@pytest.mark.parametrize("target", ["\\\\server\\share\\x.jsonl", "\\\\?\\C:\\x.jsonl",
                                    "\\\\.\\PhysicalDrive0", "C:\\dir\\x.jsonl:stream",
                                    "C:\\dir\\CON", "C:\\dir\\nul.jsonl"])
def test_unsafe_targets_are_refused_before_any_open(target, monkeypatch):
    from harness import trace_import_session
    opened = []
    monkeypatch.setattr("builtins.open", lambda *a, **k: opened.append(a) or None)
    with pytest.raises(trace_import_session.SessionRefused):
        trace_import_session.check_target(target)
    assert opened == []


def test_a_second_request_within_a_minute_is_refused(gateway):
    _, _, _, _, port, token = gateway
    first = _signed(port, token, {"client": "claude-code", "session_id": SESSION})
    second = _signed(port, token, {"client": "claude-code", "session_id": SESSION})
    assert first[0] == 202 and second[0] == 429
