"""CLI dispatch captures output without opening a Windows console."""
import os
import subprocess

from harness import endpoints


def test_cli_subprocess_window_contract(monkeypatch, tmp_path):
    # A stand-in CLI in the one PATH folder: the argv must name it by full path.
    cli = tmp_path / "bin" / ("codex.exe" if os.name == "nt" else "codex")
    cli.parent.mkdir()
    cli.write_bytes(b"MZ")
    cli.chmod(0o755)
    monkeypatch.setenv("PATH", str(cli.parent))
    calls = []
    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, b"answer", b"diagnostic")
    monkeypatch.setattr(endpoints.subprocess, "run", run)
    backend = endpoints.CliBackend("codex-plan", ["codex", "exec", "{prompt}"],
                                   timeout=12)
    result = backend.chat([{"role": "user", "content": "test prompt"}],
                          system="", max_tokens=8, temperature=0, seed=1)
    assert result["text"] == "answer"
    program = os.path.join(os.path.realpath(cli.parent), cli.name)
    assert [os.path.normcase(calls[0][0][0]), *calls[0][0][1:]] == [
        os.path.normcase(program), "exec", "user: test prompt"]
    assert calls[0][1]["creationflags"] == (
        subprocess.CREATE_NO_WINDOW if endpoints.os.name == "nt" else 0)
    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["timeout"] == 12
    assert calls[0][1].get("shell", False) is False
