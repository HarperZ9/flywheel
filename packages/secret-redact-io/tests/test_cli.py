from __future__ import annotations

import json
import subprocess
import sys


def test_cli_read_emits_redacted_json(tmp_path) -> None:
    secret = "sk-" + ("a" * 48)
    target = tmp_path / "sample.txt"
    target.write_text(f"OPENAI_API_KEY={secret}", encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-m", "secret_redact_io", "read", str(target), "--json"],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert secret not in completed.stdout
    assert "[REDACTED:openai_api_key]" in payload["text"]
    assert payload["receipt"]["operation"] == "read"


def test_cli_exec_splits_command_after_separator() -> None:
    token = "ghp_" + ("b" * 36)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "secret_redact_io",
            "exec",
            "--json",
            "--",
            sys.executable,
            "-c",
            f"print('token={token}')",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert token not in completed.stdout
    assert "[REDACTED:github_token]" in payload["stdout"]
    assert payload["returncode"] == 0
