"""Accountable hooks: event-triggered automations with teeth.

A registration binds an event type to an argv command (never a shell)
and a blocking flag. Firing an event runs every matching hook through
the real runner, seals a receipt per run (event, argv, exit, output
hash, duration), and a failing BLOCKING hook blocks the event:
fail-closed, by registration, not by mood. Secret-shaped commands are
refused at registration; nothing here ever interpolates a shell.
"""
import pytest

from harness.accountable_hooks import (
    EVENTS,
    load_registry,
    register_hook,
    run_hooks,
    save_registry,
)

ARGS = ["python", "-c", "print('hook ran')"]


def _reg(hook_id="hook_a", event="bench.completed", blocking=False,
         argv=None):
    return register_hook(
        event=event, argv=argv or ARGS, blocking=blocking,
        hook_id=hook_id, created_at="2026-08-24T12:00:00Z")


def test_registration_schema_and_seal():
    reg = _reg()
    assert reg["schema"] == "flywheel.hook-registration/v1"
    assert reg["hook_sha256"]


def test_unknown_event_is_refused():
    with pytest.raises(ValueError):
        _reg(event="on.everything")


def test_secret_shaped_commands_are_refused():
    with pytest.raises(ValueError):
        _reg(argv=["python", "-c",
                   "import os; os.environ['API_KEY']"])


def test_a_bare_shell_invocation_is_refused():
    with pytest.raises(ValueError):
        _reg(argv=["bash", "-c", "echo hi"])
    with pytest.raises(ValueError):
        _reg(argv=["cmd", "/c", "echo hi"])


def test_events_allowlist_covers_the_platform():
    for expected in ("bench.completed", "journey.stage",
                     "agent.completed", "route.completed",
                     "hook.registered"):
        assert expected in EVENTS


def test_firing_runs_matching_hooks_and_seals_receipts():
    reg = _reg()
    receipts = run_hooks("bench.completed", [reg],
                         runner=lambda argv: {"exit_code": 0,
                                              "output": "ran"},
                         context={"bench_sha256": "a" * 64})
    assert len(receipts) == 1
    r = receipts[0]
    assert r["hook_id"] == "hook_a"
    assert r["event"] == "bench.completed"
    assert r["exit_code"] == 0
    assert r["blocked"] is False
    assert len(r["output_sha256"]) == 64
    assert r["context_sha256"]


def test_non_matching_events_fire_nothing():
    receipts = run_hooks("agent.completed", [_reg()],
                         runner=lambda argv: {"exit_code": 0,
                                              "output": ""},
                         context={})
    assert receipts == []


def test_a_failing_blocking_hook_blocks_the_event():
    reg = _reg(blocking=True)

    def runner(argv):
        return {"exit_code": 3, "output": "gate refused"}

    receipts = run_hooks("bench.completed", [reg], runner=runner,
                         context={})
    assert receipts[0]["exit_code"] == 3
    assert receipts[0]["blocked"] is True


def test_a_failing_non_blocking_hook_never_blocks():
    receipts = run_hooks("bench.completed", [_reg(blocking=False)],
                         runner=lambda argv: {"exit_code": 3,
                                              "output": "x"},
                         context={})
    assert receipts[0]["blocked"] is False


def test_a_timeout_is_a_failure(tmp_path):
    reg = _reg(blocking=True)

    def runner(argv):
        raise TimeoutError("hook exceeded its budget")

    receipts = run_hooks("bench.completed", [reg], runner=runner,
                         context={})
    assert receipts[0]["exit_code"] == -1
    assert receipts[0]["blocked"] is True
    assert receipts[0]["error"] == "timeout"


def test_registry_round_trips(tmp_path):
    reg = _reg()
    path = save_registry([reg], registry_path=tmp_path / "hooks.json")
    loaded = load_registry(path)
    assert loaded == [reg]


def test_registry_refuses_a_blocked_or_unknown_row(tmp_path):
    path = tmp_path / "hooks.json"
    path.write_text(json := __import__("json").dumps(
        [{"event": "on.everything"}]), encoding="utf-8")
    with pytest.raises(ValueError):
        load_registry(path)
