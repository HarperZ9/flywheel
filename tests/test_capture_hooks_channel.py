"""I3 and I18: the capture channel records turns, fails loudly, and gives no
token and no body to a listener that has not proved it is the gateway.

The gateway runs in this process on port 0 with a temporary home; the hooks
run as subprocesses exactly as a client would start them.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request

import pytest

from capture_channel_fixture import (UUID, RecordingListener, prompt_event, run_hook,
                                     running_gateway, spool_files, stop_event)


@pytest.fixture
def home(tmp_path):
    path = tmp_path / "home"
    path.mkdir()
    return path


@pytest.fixture
def work(tmp_path):
    path = tmp_path / "work"
    path.mkdir()
    return path


def _receipts(home):
    from harness.store import query_entities
    return query_entities(kind="turn-receipt", home=home)


def _reason(proc) -> str:
    return proc.stderr.decode()


def test_a_stop_event_is_recorded_with_a_receipt(home, work, monkeypatch):
    with running_gateway(home, monkeypatch):
        proc = run_hook(home, "stop", stop_event(), cwd=work)
    assert proc.returncode == 0, _reason(proc)
    assert proc.stdout == b"" and proc.stderr == b""
    receipts = _receipts(home)
    assert len(receipts) == 1
    answer = hashlib.sha256(b"the final answer").hexdigest()
    from harness.store import get_entity
    assert get_entity(receipts[0]["eid"], home=home)["data"]["answer_sha256"] == answer
    assert spool_files(home) == []


def test_a_prompt_event_passes_the_channel_and_stays_silent(home, work, monkeypatch):
    with running_gateway(home, monkeypatch):
        proc = run_hook(home, "prompt", prompt_event(), cwd=work)
    assert proc.returncode == 0, _reason(proc)
    assert proc.stdout.strip() in (b"", b"{}")


def test_no_token_fails_loudly_and_spools_one_record(home, work):
    proc = run_hook(home, "stop", stop_event(), cwd=work)
    assert proc.returncode == 1
    assert proc.stdout == b""
    lines = proc.stderr.decode().strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("flywheel capture:")
    assert "TOKEN_MISSING" in lines[0]
    records = spool_files(home)
    assert len(records) == 1
    record = json.loads(records[0].read_text())
    assert record["reason_code"] == "TOKEN_MISSING"
    assert record["session_id"] == UUID
    assert "cwd" not in record and "transcript_path" not in record


def test_no_endpoint_file_means_no_connection(home, work):
    (home / "gateway.token").write_text("synthetic-token-value")
    proc = run_hook(home, "stop", stop_event(), cwd=work)
    assert proc.returncode == 1
    assert "GATEWAY_NOT_RUNNING" in _reason(proc)


def test_a_stale_endpoint_file_names_a_dead_process_and_connects_nowhere(home, work):
    from harness.gateway_endpoint_file import write_endpoint
    (home / "gateway.token").write_text("synthetic-token-value")
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    listener = RecordingListener(lambda data: b"{}")
    try:
        write_endpoint(home, "127.0.0.1", listener.port, dead.pid)
        proc = run_hook(home, "stop", stop_event(), cwd=work)
    finally:
        listener.close()
    assert "GATEWAY_NOT_RUNNING" in _reason(proc)
    assert listener.received == []


def _fake_hello(data: bytes) -> bytes:
    return json.dumps({"schema": "flywheel.capture-hello/v1", "sn": "00" * 16,
                       "proof": "11" * 32, "effective": {}}).encode()


def test_a_listener_without_the_proof_gets_no_token_and_no_body(home, work):
    from harness.gateway_endpoint_file import write_endpoint
    token = "synthetic-token-" + "q" * 20
    (home / "gateway.token").write_text(token)
    listener = RecordingListener(_fake_hello)
    try:
        write_endpoint(home, "127.0.0.1", listener.port, os.getpid())
        proc = run_hook(home, "stop", stop_event(answer="CANARY-BODY-7Q2"), cwd=work)
    finally:
        listener.close()
    assert proc.returncode == 1 and "SERVER_PROOF_FAILED" in _reason(proc)
    assert len(listener.received) == 1
    request = listener.received[0]
    assert request.startswith(b"GET /api/traces/capture/hello?")
    head, _, body = request.partition(b"\r\n\r\n")
    assert b"authorization" not in head.lower()
    assert body == b"" and b"CANARY-BODY-7Q2" not in request
    assert token.encode() not in request


def test_a_proof_relayed_from_the_real_gateway_on_another_port_is_refused(
        home, work, monkeypatch):
    from harness.gateway_endpoint_file import write_endpoint
    with running_gateway(home, monkeypatch) as server:
        real = server.server_address[1]

        def relay(data: bytes) -> bytes:
            path = data.split(b" ", 2)[1].decode()
            with urllib.request.urlopen(f"http://127.0.0.1:{real}{path}", timeout=5) as r:
                return r.read()
        listener = RecordingListener(relay)
        try:
            write_endpoint(home, "127.0.0.1", listener.port, os.getpid())
            proc = run_hook(home, "stop", stop_event(), cwd=work)
        finally:
            listener.close()
    assert "SERVER_PROOF_FAILED" in _reason(proc)
    assert len(listener.received) == 1
    assert _receipts(home) == []


def _signed_request(home, port, token, body: bytes):
    from harness.capture_hooks import protocol
    with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/traces/capture/hello?v=1&cn={'ab' * 16}",
            timeout=5) as r:
        hello = json.loads(r.read())
    _, k_c = protocol.derive_keys(token)
    path = "/api/traces/capture/scaffold"
    header = protocol.auth_header(k_c, "POST", path, body, int(time.time()),
                                  "cd" * 16, hello["sn"], "127.0.0.1", port)
    return urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, headers={
        "Authorization": header, "Content-Type": "application/json"}, method="POST")


def test_a_replayed_signed_request_is_refused(home, work, monkeypatch):
    with running_gateway(home, monkeypatch) as server:
        port = server.server_address[1]
        token = (home / "gateway.token").read_text().strip()
        request = _signed_request(home, port, token, b'{"answer": "once"}')
        with urllib.request.urlopen(request, timeout=5) as first:
            assert first.status == 200
        with pytest.raises(urllib.error.HTTPError) as replay:
            urllib.request.urlopen(request, timeout=5)
    assert replay.value.code == 401
    assert len(_receipts(home)) == 1


def test_a_signature_under_the_wrong_token_is_refused(home, work, monkeypatch):
    with running_gateway(home, monkeypatch) as server:
        port = server.server_address[1]
        request = _signed_request(home, port, "not-the-token", b'{"answer": "x"}')
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(request, timeout=5)
    assert refused.value.code == 401
    assert _receipts(home) == []


def test_the_old_bearer_scaffold_route_still_refuses_a_hook_without_a_token(
        home, work, monkeypatch):
    """What the audit probed: the unauthenticated POST the old hook sent."""
    with running_gateway(home, monkeypatch) as server:
        port = server.server_address[1]
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/scaffold", data=b'{"answer": "x"}',
            headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(request, timeout=5)
    assert refused.value.code == 401
