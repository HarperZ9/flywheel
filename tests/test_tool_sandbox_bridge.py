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


def _no_sandbox(monkeypatch):
    """Make the host look like one with no sandbox, on any platform.

    The bridge imports sandboxed_run inside the call, so replacing the module
    attribute reaches it. This lets the refusal be tested on Windows as well,
    where the real sandbox exists and would otherwise hide the branch.
    """
    from harness import sandboxed_runner

    def _raise(*a, **k):
        raise sandboxed_runner.SandboxUnavailable("no sandbox on this host")

    monkeypatch.setattr(sandboxed_runner, "sandboxed_run", _raise)


def test_a_sandboxed_runner_refuses_when_there_is_no_sandbox(tmp_path,
                                                             monkeypatch):
    """The default. A caller who asked for isolation does not get bare shell."""
    _no_sandbox(monkeypatch)
    from harness.tool_sandbox_bridge import make_sandboxed_runner
    ok, out = make_sandboxed_runner(bindings=None)("echo open", str(tmp_path))
    assert not ok
    assert "[refused]" in out
    # The refusal has to be actionable, so it names the way out.
    assert "FLYWHEEL_ALLOW_UNSANDBOXED" in out


def test_a_refused_command_never_runs(tmp_path, monkeypatch):
    """The control on the refusal.

    A refusal that still executed the command would read the same from the
    outside, differing only in a string. The evidence is the side effect it
    would have left on disk.
    """
    _no_sandbox(monkeypatch)
    from harness.tool_sandbox_bridge import make_sandboxed_runner
    marker = tmp_path / "ran.txt"
    ok, _ = make_sandboxed_runner(bindings=None)(
        f"echo ran > {marker.name}", str(tmp_path))
    assert not ok
    assert not marker.exists()


def test_disclose_restores_the_bare_run_and_labels_it(tmp_path, monkeypatch):
    """The opt-in still exists, and still says what it did."""
    _no_sandbox(monkeypatch)
    from harness.tool_sandbox_bridge import make_sandboxed_runner
    runner = make_sandboxed_runner(bindings=None, on_unavailable="disclose")
    ok, out = runner("echo fallback", str(tmp_path))
    assert ok
    assert "fallback" in out
    assert "[UNVERIFIABLE: sandbox unavailable]" in out


def test_an_unknown_policy_fails_where_it_is_written():
    """A typo in a security setting is caught at construction, not at use."""
    from harness.tool_sandbox_bridge import make_sandboxed_runner
    with pytest.raises(ValueError, match="on_unavailable"):
        make_sandboxed_runner(bindings=None, on_unavailable="disclosee")


def test_an_unset_host_is_a_host_that_says_no():
    from harness.tool_sandbox_bridge import fallback_from_env
    assert fallback_from_env({}) == "refuse"
    assert fallback_from_env({"FLYWHEEL_ALLOW_UNSANDBOXED": ""}) == "refuse"
    assert fallback_from_env({"FLYWHEEL_ALLOW_UNSANDBOXED": "0"}) == "refuse"
    for yes in ("1", "true", "YES", " on "):
        assert fallback_from_env({"FLYWHEEL_ALLOW_UNSANDBOXED": yes}) \
            == "disclose"


def test_every_shipped_entry_point_asks_the_environment(tmp_path):
    """The three callers that ship must not take the library default silently.

    Reading the source is the check that survives refactoring of any one of
    them: a call site that dropped the policy would still construct a working
    runner, and nothing at runtime would look wrong until a Linux host ran a
    command bare.
    """
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "harness"
    for name in ("local_agent_cli.py", "local_mcp.py", "router_agent.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "make_sandboxed_runner(" in text, name
        assert "on_unavailable=fallback_from_env()" in text, name


@pytest.mark.skipif(os.name == "nt",
                    reason="Windows has the sandbox, so nothing to refuse")
def test_a_real_posix_host_refuses_without_any_patching(tmp_path):
    """The same claim, with the platform doing the work instead of a stub."""
    from harness.tool_sandbox_bridge import make_sandboxed_runner
    ok, out = make_sandboxed_runner(bindings=None)("echo open", str(tmp_path))
    assert not ok
    assert "[refused]" in out


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
