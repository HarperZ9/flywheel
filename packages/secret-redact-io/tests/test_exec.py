from __future__ import annotations

import sys

from secret_redact_io import run_guarded


def test_run_guarded_redacts_stdout_and_keeps_receipt_hash_only() -> None:
    token = "ghp_" + ("b" * 36)

    result = run_guarded([sys.executable, "-c", f"print('token={token}')"])

    assert result.returncode == 0
    assert token not in result.stdout
    assert "[REDACTED:github_token]" in result.stdout
    assert result.receipt.operation == "exec"
    assert result.receipt.metadata["returncode"] == 0
    assert token not in result.receipt.to_json()
