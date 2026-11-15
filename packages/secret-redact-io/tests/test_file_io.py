from __future__ import annotations

from secret_redact_io import read_text_guarded, write_text_guarded


def test_read_text_guarded_returns_redacted_text_and_receipt(tmp_path) -> None:
    secret = "sk-" + ("a" * 48)
    target = tmp_path / "sample.txt"
    target.write_text(f"OPENAI_API_KEY={secret}\nhello", encoding="utf-8")

    result = read_text_guarded(target)

    assert secret not in result.text
    assert "[REDACTED:openai_api_key]" in result.text
    assert result.receipt.operation == "read"
    assert result.receipt.target.endswith("sample.txt")
    assert result.receipt.redactions["openai_api_key"] == 1
    assert secret not in result.receipt.to_json()


def test_write_text_guarded_dry_run_does_not_write(tmp_path) -> None:
    target = tmp_path / "created.txt"

    result = write_text_guarded(target, "password=hunter2", dry_run=True)

    assert not target.exists()
    assert "hunter2" not in result.text
    assert result.receipt.operation == "write.dry_run"
    assert result.receipt.metadata["written"] is False


def test_write_text_guarded_redacts_before_atomic_write(tmp_path) -> None:
    token = "ghp_" + ("b" * 36)
    target = tmp_path / "created.txt"

    result = write_text_guarded(target, f"token={token}", dry_run=False)

    assert target.exists()
    assert token not in target.read_text(encoding="utf-8")
    assert "[REDACTED:github_token]" in target.read_text(encoding="utf-8")
    assert result.receipt.operation == "write"
    assert result.receipt.metadata["written"] is True
