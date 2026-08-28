"""Bridge between ToolExecutor and the sandbox."""
import os
import pytest


def test_make_sandboxed_runner_returns_callable():
    from harness.tool_sandbox_bridge import make_sandboxed_runner
    runner = make_sandboxed_runner(bindings=None)
    assert callable(runner)


@pytest.mark.skipif(os.name != "nt", reason="Windows sandbox only")
def test_sandboxed_runner_executes_and_returns_output(tmp_path):
    from harness.tool_sandbox_bridge import make_sandboxed_runner
    runner = make_sandboxed_runner(bindings=None)
    ok, out = runner("echo sandboxed", str(tmp_path))
    assert ok
    assert "sandboxed" in out


def test_unsandboxed_fallback_marks_output(tmp_path):
    from harness.tool_sandbox_bridge import make_unsandboxed_runner
    runner = make_unsandboxed_runner()
    ok, out = runner("echo fallback", str(tmp_path))
    assert ok
    assert "fallback" in out


def test_make_sandboxed_runner_with_bindings():
    from harness.credential_handles import CredentialBindings
    from harness.tool_sandbox_bridge import make_sandboxed_runner
    bindings = CredentialBindings({"TEST_KEY": "test_value"})
    runner = make_sandboxed_runner(bindings=bindings)
    assert callable(runner)


def test_sandboxed_runner_falls_back_off_windows(tmp_path, monkeypatch):
    """On a non-Windows host sandboxed_run raises SandboxUnavailable; the
    bridge must fall back to bare subprocess rather than propagate it."""
    if os.name == "nt":
        pytest.skip("fallback path only triggers where the sandbox is unavailable")
    from harness.tool_sandbox_bridge import make_sandboxed_runner
    runner = make_sandboxed_runner(bindings=None)
    ok, out = runner("echo fallback", str(tmp_path))
    assert ok
    assert "fallback" in out


def test_make_unsandboxed_runner_reports_nonzero_exit(tmp_path):
    from harness.tool_sandbox_bridge import make_unsandboxed_runner
    runner = make_unsandboxed_runner()
    cmd = "exit 3" if os.name == "nt" else "exit 3"
    ok, out = runner(cmd, str(tmp_path))
    assert not ok
    assert "[exit 3]" in out


def test_make_unsandboxed_runner_times_out(tmp_path):
    from harness.tool_sandbox_bridge import make_unsandboxed_runner
    runner = make_unsandboxed_runner(timeout_seconds=1)
    cmd = "ping -n 5 127.0.0.1 >NUL" if os.name == "nt" else "sleep 5"
    ok, out = runner(cmd, str(tmp_path))
    assert not ok
    assert "timeout after 1s" in out


# ── wired into ToolExecutor (the `runner` injection point in local_tools.py) ──

def test_exec_wired_to_unsandboxed_bridge_runner(tmp_path):
    # the bridge's bare-subprocess runner slots into ToolExecutor exactly like
    # any other injected runner: the gate still runs first, the runner only
    # sees a call that already cleared it.
    from harness.local_tools import ToolExecutor, ToolGate
    from harness.tool_sandbox_bridge import make_unsandboxed_runner
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_exec=True),
                      runner=make_unsandboxed_runner())
    r = ex.execute("run", {"cmd": "echo wired"})
    assert r.ok and "wired" in r.output
    blocked = ex.execute("run", {"cmd": "rm -rf /"})
    assert not blocked.ok and "denylist" in blocked.output  # gate still runs first


@pytest.mark.skipif(os.name != "nt", reason="Windows sandbox only")
def test_exec_wired_to_sandboxed_bridge_runner(tmp_path):
    # on Windows this actually enters the low-integrity sandbox via ToolExecutor.
    from harness.local_tools import ToolExecutor, ToolGate
    from harness.tool_sandbox_bridge import make_sandboxed_runner
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_exec=True),
                      runner=make_sandboxed_runner(bindings=None))
    r = ex.execute("run", {"cmd": "echo wired"})
    assert r.ok and "wired" in r.output


def test_exec_default_runner_unchanged_when_none(tmp_path):
    # zero behavioral change: with runner=None (the default, untouched by this
    # task), _t_run still falls through to bare subprocess exactly as before.
    from harness.local_tools import ToolExecutor, ToolGate
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_exec=True))
    assert ex.runner is None
    r = ex.execute("run", {"cmd": "echo untouched"})
    assert r.ok and "untouched" in r.output
