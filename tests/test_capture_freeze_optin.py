"""D3, SP-04: URL freezing is its own opt-in, off by default. Off, no URL
leaves the hook and no snapshot appears. On, credential-bearing URLs are
refused and counted without being echoed, and snapshots are encrypted and
registered."""
import json

import pytest

from capture_channel_fixture import prompt_event, run_hook, running_gateway, stop_event
from trace_enc_fakes import StreamTestProvider, using
from turn_fixtures import custody_bytes, receipts

PAGE = b"FROZEN-PAGE-BYTES-" + b"p1" * 20
PLAIN = "https://docs.example.org/guide"
SIGNED = "https://bucket.example/o?X-Amz-" + "Signature=" + "f" * 64
USERINFO = "https://" + "user:hunter2hunter2" + "@private.example/x"


@pytest.fixture
def work(tmp_path):
    path = tmp_path / "work"
    path.mkdir()
    return path


@pytest.fixture
def bodies(monkeypatch):
    from harness.gateway_request_sig import STATE
    seen, real = [], STATE.verify

    def verify(token, header, method, path, body, host, port):
        seen.append(body)
        return real(token, header, method, path, body, host, port)
    monkeypatch.setattr(STATE, "verify", verify)
    return seen


@pytest.fixture
def fetches(monkeypatch):
    from harness import web_fetch_pinned
    seen = []
    monkeypatch.setattr(web_fetch_pinned, "fetch_pinned", lambda url, **kw: seen.append(url) or (
        200, {"Content-Type": "text/plain"}, PAGE, url))
    return seen


def _freeze_on(home):
    from harness.operation_grants import load_or_create_owner_ref
    from harness.trace_capture_settings import adopt, digest, write_file
    from harness.trace_presence import confirm
    from harness.trace_witness import MemorySink
    owner = load_or_create_owner_ref(home)
    settings = write_file(home, {"freeze_urls": "on"})
    adopt(home, owner, confirm(home / "state", owner, "capture_settings", digest(settings),
                               "freeze on"), sink=MemorySink())


def test_freeze_off_sends_no_url_and_writes_no_snapshot(tmp_path, work, monkeypatch,
                                                         bodies, fetches):
    home = tmp_path / "home"
    home.mkdir()
    text = f"read {PLAIN} and {SIGNED} and {USERINFO}"
    with using(StreamTestProvider()), running_gateway(home, monkeypatch):
        proc = run_hook(home, "prompt", prompt_event(text, prompt_id="pid-1"), cwd=work)
    assert proc.returncode == 0
    assert bodies and all(b"example" not in body for body in bodies)
    assert fetches == []
    assert not list(home.rglob("*snapshots*")) and "additionalContext" not in proc.stdout.decode()


def test_freeze_on_refuses_credential_urls_and_encrypts_snapshots(tmp_path, work, monkeypatch,
                                                                   bodies, fetches):
    from harness import trace_inventory
    home = tmp_path / "home"
    home.mkdir()
    text = f"read {PLAIN} and {SIGNED} and {USERINFO}"
    with using(StreamTestProvider()), running_gateway(home, monkeypatch):
        _freeze_on(home)
        proc = run_hook(home, "prompt", prompt_event(text, prompt_id="pid-1"), cwd=work)
        run_hook(home, "stop", stop_event("done", prompt_id="pid-1"), cwd=work)
    assert fetches == [PLAIN]
    context = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
    assert PLAIN in context and "2 refused" in context
    assert "hunter2" not in context and "Signature" not in context
    data = receipts(home)[-1]["data"]
    assert (data["frozen_urls"], data["refused_urls"]) == (1, 2)
    assert len(data["freeze_commitment"]) == 64
    stored = custody_bytes(home)
    assert PAGE not in stored and b"hunter2" not in stored
    assert trace_inventory.classify("state", "capture-snapshots").id == "S8b"
    assert list((home / "state" / "capture-snapshots").rglob("*.enc"))
