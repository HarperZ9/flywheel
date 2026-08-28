"""Sandboxed runner: shell commands under low-integrity with output capture."""
import os

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows low-integrity only")
class TestSandboxedRunner:

    def test_captures_stdout(self, tmp_path):
        from harness.sandboxed_runner import sandboxed_run
        source = tmp_path / "source"; source.mkdir()
        ok, out = sandboxed_run("echo hello world", str(source))
        assert ok
        assert "hello world" in out

    def test_captures_exit_code(self, tmp_path):
        from harness.sandboxed_runner import sandboxed_run
        source = tmp_path / "source"; source.mkdir()
        ok, out = sandboxed_run("exit /b 42", str(source))
        assert not ok
        assert "exit 42" in out

    def test_timeout_reports_honestly(self, tmp_path):
        from harness.sandboxed_runner import sandboxed_run
        source = tmp_path / "source"; source.mkdir()
        ok, out = sandboxed_run("ping -n 30 127.0.0.1", str(source),
                                timeout_seconds=2)
        assert not ok
        assert "timeout" in out.lower()

    def test_denied_command_never_runs(self, tmp_path):
        from harness.sandboxed_runner import sandboxed_run
        source = tmp_path / "source"; source.mkdir()
        ok, out = sandboxed_run("rm -rf /", str(source))
        assert not ok
        assert "blocked" in out.lower() or "denied" in out.lower()

    def test_credential_values_not_in_output(self, tmp_path):
        from harness.sandboxed_runner import sandboxed_run
        from harness.credential_handles import CredentialBindings
        bindings = CredentialBindings({"MY_SECRET": "super-secret-value"})
        source = tmp_path / "source"; source.mkdir()
        ok, out = sandboxed_run("set MY_SECRET", str(source),
                                bindings=bindings)
        assert "super-secret-value" not in repr(out)


def test_non_windows_fails_closed():
    if os.name == "nt":
        pytest.skip("only tests the non-Windows path")
    from harness.sandboxed_runner import SandboxUnavailable, sandboxed_run
    with pytest.raises(SandboxUnavailable):
        sandboxed_run("echo hi", ".")
