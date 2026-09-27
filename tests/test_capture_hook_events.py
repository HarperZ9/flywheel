"""I3, I15, I18 on the hook side: an event the hook cannot read fails
visibly with its own code and never commits to an empty prompt; a gateway
that rate-limits hellos is named as such, not as an impostor; the listener is
checked again right before each send; capture-off events reach the custody
ledger and the witness."""
import json

import pytest

from capture_channel_fixture import hook_env, prompt_event, run_hook, running_gateway
from delete_fixtures import OWNER
from harness.capture_hooks import __main__ as hook, client, spool
from harness.capture_hooks.client import CaptureFailure
from harness.trace_capture_off import record_suppressions
from harness.trace_custody_ledger import CustodyLedger
from harness.trace_witness import MemorySink

SESSION = "0f6d2c1e-4b7a-4c55-9a51-2f0e7c9d1a3b"


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    work = tmp_path / "work"
    work.mkdir()
    return home, work


def _codes(home):
    return [r["reason_code"] for r in spool.failures(home)]


@pytest.mark.parametrize("raw", [b"x" * (hook.MAX_EVENT + 1), b"{not json", b"[1, 2]"],
                         ids=["oversized", "not-json", "not-an-object"])
def test_an_unreadable_event_fails_visibly_and_sends_nothing(home, raw):
    home, work = home
    code, out, err = hook.run(["prompt", "--client", "codex", "--home", str(home)], raw,
                              {}, str(work))
    assert "EVENT_UNREADABLE" in out + err
    assert _codes(home) == ["EVENT_UNREADABLE"]


def test_a_prompt_event_without_a_prompt_is_prompt_missing(tmp_path, monkeypatch):
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    with running_gateway(home, monkeypatch):
        event = {"session_id": SESSION, "hook_event_name": "UserPromptSubmit"}
        done = run_hook(home, "prompt", event, client="codex", cwd=work)
    assert b"PROMPT_MISSING" in done.stdout + done.stderr
    assert _codes(home) == ["PROMPT_MISSING"]


def test_a_rate_limited_hello_is_named_and_retried_once(monkeypatch):
    calls = []
    monkeypatch.setattr(client.listener_owner, "check_listener", lambda *a: None)
    channel = client.Channel({"host": "127.0.0.1", "port": 9, "pid": 1}, "t" * 43, 1.0)
    monkeypatch.setattr(channel, "_exchange", lambda *a: calls.append(a) or (429, b""))
    monkeypatch.setattr(client.time, "sleep", lambda s: None)
    with pytest.raises(CaptureFailure) as failure:
        channel.hello()
    assert failure.value.code == "HELLO_RATE_LIMITED" and len(calls) == 2


def test_the_listener_is_checked_again_before_each_send(monkeypatch):
    answers = iter([None, "LISTENER_NOT_OWNED"])
    monkeypatch.setattr(client.listener_owner, "check_listener", lambda *a: next(answers))
    channel = client.Channel({"host": "127.0.0.1", "port": 9, "pid": 1}, "t" * 43, 1.0)
    channel.sn = "a" * 32
    sent = []
    monkeypatch.setattr(channel, "_exchange", lambda *a: sent.append(a) or (200, b"{}"))
    assert channel.request("POST", "/api/traces/capture/prompt", {"x": 1}) == {}
    with pytest.raises(CaptureFailure) as failure:
        channel.request("POST", "/api/traces/capture/prompt", {"x": 1})
    assert failure.value.code == "LISTENER_NOT_OWNED" and len(sent) == 1


def test_capture_off_events_reach_the_ledger_and_the_witness(home):
    home, work = home
    raw = json.dumps(prompt_event("never sent", session=SESSION)).encode()
    for _ in range(2):
        hook.run(["prompt", "--client", "claude-code", "--home", str(home)], raw,
                 {"FLYWHEEL_CAPTURE": "off"}, str(work))
    sink = MemorySink()
    assert record_suppressions(home, OWNER, sink=sink) == 2
    entries = [e for e in CustodyLedger(home, OWNER).entries()
               if e["kind"] == "capture_suppressed"]
    assert len(entries) == 1 and entries[0]["fields"]["count"] == 2
    assert entries[0]["fields"]["client"] == "claude-code"
    assert [e["kind"] for e in sink.read()] == ["capture_suppressed"]
    assert record_suppressions(home, OWNER, sink=sink) == 0
    assert len(spool.suppressions(home)) == 2
    stored = b"".join(p.read_bytes() for p in (home / "state").rglob("*") if p.is_file())
    assert b"never sent" not in stored and str(work).encode() not in stored


def test_the_gateway_folds_capture_off_records_in_at_hello(tmp_path, monkeypatch):
    from harness import trace_witness
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    monkeypatch.setattr(trace_witness, "default_sink", trace_witness.MemorySink)
    with running_gateway(home, monkeypatch):
        run_hook(home, "prompt", prompt_event("off"), cwd=work,
                 env=hook_env({"FLYWHEEL_CAPTURE": "off"}))
        run_hook(home, "prompt", prompt_event("on"), cwd=work)
        owner = (home / "owner.ref").read_text()
        kinds = [e["kind"] for e in CustodyLedger(home, owner).entries()]
    assert "capture_suppressed" in kinds
