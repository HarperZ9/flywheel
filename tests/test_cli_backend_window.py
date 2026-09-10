"""CLI dispatch captures output without opening a Windows console."""
import subprocess

from harness import endpoints


def test_cli_subprocess_window_contract(monkeypatch):
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
    assert calls[0][0] == ["codex", "exec", "user: test prompt"]
    assert calls[0][1]["creationflags"] == (
        subprocess.CREATE_NO_WINDOW if endpoints.os.name == "nt" else 0)
    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["timeout"] == 12
    assert calls[0][1].get("shell", False) is False
