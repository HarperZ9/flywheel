from __future__ import annotations

import json
import subprocess
import sys
import traceback

import pytest

from tests.enterprise_envs import service_desk_cli_diagnostics as diag


CANARIES = (
    "PRIVATE_PATH_CANARY",
    "RAW_STDOUT_CANARY",
    "RAW_STDERR_CANARY",
    "SECRET_ENV_CANARY",
    "unknown_symbol_canary",
    "--out",
)


def _diag_line(record):
    return diag.PREFIX + json.dumps(record, sort_keys=True)


def _entry(phase="cli_module"):
    return {"event": "entry", "phase": phase}


def _full_snapshot():
    frame = {"module": "external", "function": "other", "line": 0}
    return {
        "event": "deadline_snapshot",
        "phase": "cli_module",
        "threads": [
            {"main": index == 0, "frames": [dict(frame) for _ in range(24)]}
            for index in range(8)
        ],
    }


def test_run_e2e_dispatches_bootstrap_once_with_retained_thirty_second_timeout(
    tmp_path, monkeypatch,
):
    calls = []
    stdout = '{"schema": "source-cli-result"}\n'

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout, "")

    monkeypatch.setattr(diag.subprocess, "run", run)
    env = {"PYTHONPATH": "package-src", "SECRET_ENV_CANARY": "do-not-echo"}
    out = tmp_path / "out"

    result = diag.run_e2e(out, env)

    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd == [
        sys.executable,
        "-m",
        "tests.enterprise_envs.service_desk_cli_diagnostics",
        "e2e",
        "--out",
        str(out),
    ]
    assert kwargs["cwd"] == diag.ROOT
    assert kwargs["env"] is env
    assert kwargs["text"] is True
    assert kwargs["stdout"] is subprocess.PIPE
    assert kwargs["stderr"] is subprocess.PIPE
    assert kwargs["timeout"] == 30
    assert result.returncode == 0
    assert result.stdout == stdout
    assert result.stderr == "ServiceDesk CLI diagnostics unavailable"


def test_timeout_expired_is_rethrown_without_private_output_or_argv(
    tmp_path, monkeypatch,
):
    valid = _diag_line(_entry())
    raw_stderr = f"RAW_STDERR_CANARY\n{valid}\nPRIVATE_PATH_CANARY --out"

    def run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd, kwargs["timeout"],
            output="RAW_STDOUT_CANARY",
            stderr=raw_stderr,
        )

    monkeypatch.setattr(diag.subprocess, "run", run)
    out = tmp_path / "PRIVATE_PATH_CANARY" / "out"
    env = {"PYTHONPATH": "pkg"}
    env["SECRET_ENV_CANARY"] = "value"

    with pytest.raises(subprocess.TimeoutExpired) as raised:
        diag.run_e2e(out, env)

    exc = raised.value
    rendered = "".join(traceback.format_exception(exc))
    assert exc.cmd == "ServiceDesk source CLI e2e"
    assert exc.timeout == 30
    assert exc.__cause__ is None
    assert json.loads(getattr(exc, "__notes__", [""])[0]) == _entry()
    for canary in CANARIES:
        assert canary not in rendered


def test_nonzero_result_keeps_failure_and_filters_raw_stderr(monkeypatch, tmp_path):
    valid = _diag_line(_entry("run_e2e"))

    def run(cmd, **kwargs):
        stderr = "\n".join([
            "Traceback RAW_STDERR_CANARY PRIVATE_PATH_CANARY --out",
            valid,
            _diag_line({**_entry(), "path": "PRIVATE_PATH_CANARY"}),
        ])
        return subprocess.CompletedProcess(cmd, 2, "RAW_STDOUT_CANARY", stderr)

    monkeypatch.setattr(diag.subprocess, "run", run)

    result = diag.run_e2e(tmp_path / "out", {"PYTHONPATH": "pkg"})

    assert result.returncode == 2
    assert result.stdout == ""
    assert json.loads(result.stderr) == _entry("run_e2e")
    for canary in CANARIES:
        assert canary not in repr(result)


def test_diagnostics_keep_only_last_two_valid_records_and_roundtrip_full_snapshot():
    first = _entry("run_e2e")
    second = _entry()
    snapshot = _full_snapshot()
    full_line = _diag_line(snapshot)
    stderr = "\n".join([
        "arbitrary text RAW_STDERR_CANARY",
        _diag_line(first),
        diag.PREFIX + "{not-json",
        _diag_line({**_entry(), "unknown": "PRIVATE_PATH_CANARY"}),
        _diag_line(second),
        full_line,
    ])

    parsed = [json.loads(line) for line in diag._diagnostics(stderr).splitlines()]

    assert len(full_line) <= 32768
    assert parsed == [second, snapshot]
    for canary in CANARIES:
        assert canary not in diag._diagnostics(stderr)


@pytest.mark.parametrize("bad_record", [
    {
        "event": "deadline_snapshot",
        "phase": "cli_module",
        "threads": [{"main": True, "frames": [{
            "module": "unknown_symbol_canary",
            "function": "unknown_symbol_canary",
            "line": 1,
        }]}],
    },
    {"event": "entry", "phase": ["unknown_symbol_canary"]},
    {"event": "deadline_snapshot", "phase": "cli_module", "threads": [[[]]]},
])
def test_diagnostics_reject_close_malicious_records_without_replacing_failure(bad_record):
    stderr = "\n".join([
        "RAW_STDERR_CANARY",
        _diag_line(bad_record),
        diag.PREFIX + "[" * 400,
    ])

    result = diag._diagnostics(stderr)

    assert result == "ServiceDesk CLI diagnostics unavailable"
    for canary in CANARIES:
        assert canary not in result


def test_safe_stack_strips_paths_locals_and_unknown_symbols():
    class Code:
        def __init__(self, name):
            self.co_name = name

    class Frame:
        def __init__(self, module, function, line, back=None):
            self.f_globals = {
                "__name__": module,
                "__file__": "C:/PRIVATE_PATH_CANARY/source.py",
            }
            self.f_code = Code(function)
            self.f_lineno = line
            self.f_back = back
            self.f_locals = {"secret": "SECRET_ENV_CANARY"}

    private = Frame("private.unknown_symbol_canary", "unknown_symbol_canary", 99)
    known_unknown = Frame("service_desk_incident_env.cli", "unknown_symbol_canary", 41, private)
    known = Frame("service_desk_incident_env.cli", "main", 12, known_unknown)

    rows = diag._safe_stack(known)

    assert rows == [
        {"module": "service_desk_incident_env.cli", "function": "main", "line": 12},
        {"module": "service_desk_incident_env.cli", "function": "other", "line": 41},
        {"module": "external", "function": "other", "line": 0},
    ]
    rendered = json.dumps(rows, sort_keys=True)
    for canary in CANARIES:
        assert canary not in rendered


def test_watchdog_uses_short_delay_control_and_suppresses_when_stopped(monkeypatch):
    records = []
    snapshot = _full_snapshot()

    class Stop:
        def __init__(self, stopped):
            self.stopped = stopped
            self.delays = []

        def wait(self, delay):
            self.delays.append(delay)
            return self.stopped

    monkeypatch.setattr(diag, "_emit", records.append)
    monkeypatch.setattr(diag, "_snapshot", lambda: snapshot)

    expired = Stop(False)
    stopped = Stop(True)
    diag._watchdog(expired, delay=0.01)
    diag._watchdog(stopped, delay=0.01)

    assert records == [snapshot]
    assert expired.delays == [0.01]
    assert stopped.delays == [0.01]


def test_main_dispatches_real_cli_module_and_stops_watchdog_on_cli_error(monkeypatch):
    records = []
    run_calls = []
    threads = []
    observed_argv = []

    class Stop:
        def __init__(self):
            self.set_called = False

        def set(self):
            self.set_called = True

    class Thread:
        def __init__(self, *, target, args, daemon):
            threads.append({"target": target, "args": args, "daemon": daemon})

        def start(self):
            threads[-1]["started"] = True

    stop = Stop()

    def run_module(module, *, run_name, alter_sys):
        run_calls.append((module, run_name, alter_sys))
        observed_argv.append(list(diag.sys.argv))
        raise RuntimeError("cli failure is not swallowed")

    monkeypatch.setattr(diag, "_emit", records.append)
    monkeypatch.setattr(diag.threading, "Event", lambda: stop)
    monkeypatch.setattr(diag.threading, "Thread", Thread)
    monkeypatch.setattr(diag.runpy, "run_module", run_module)
    monkeypatch.setattr(diag.sys, "argv", ["pytest"])

    with pytest.raises(RuntimeError, match="not swallowed"):
        diag.main(["e2e", "--out", "PRIVATE_PATH_CANARY"])

    assert records == [_entry()]
    assert threads == [{
        "target": diag._watchdog,
        "args": (stop,),
        "daemon": True,
        "started": True,
    }]
    assert run_calls == [("service_desk_incident_env.cli", "__main__", True)]
    assert observed_argv == [["service_desk_incident_env.cli", "e2e", "--out", "PRIVATE_PATH_CANARY"]]
    assert stop.set_called is True
