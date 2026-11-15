from __future__ import annotations

from secret_redact_io import GuardrailPolicy


def test_redacts_common_secret_shapes_without_leaking_values() -> None:
    openai_key = "sk-" + ("a" * 48)
    github_token = "ghp_" + ("b" * 36)
    jwt = "eyJhbGciOiJIUzI1NiJ9." + ("c" * 24) + "." + ("d" * 24)
    text = (
        f"OPENAI_API_KEY={openai_key}\n"
        f"Authorization: Bearer {github_token}\n"
        f"session={jwt}"
    )

    result = GuardrailPolicy.default().redact_text(text)

    assert openai_key not in result.text
    assert github_token not in result.text
    assert jwt not in result.text
    assert "[REDACTED:openai_api_key]" in result.text
    assert "[REDACTED:github_token]" in result.text
    assert "[REDACTED:jwt]" in result.text
    assert result.total >= 3


def test_redacts_credential_fields_and_pem_blocks() -> None:
    pem = (
        "-----BEGIN PRIVATE KEY-----\n"
        "abcdefghijklmnopqrstuvwxyz0123456789\n"
        "-----END PRIVATE KEY-----"
    )
    text = f"password = hunter2\napi_key: abc123456789\n{pem}"

    result = GuardrailPolicy.default().redact_text(text)

    assert "hunter2" not in result.text
    assert "abc123456789" not in result.text
    assert "BEGIN PRIVATE KEY" not in result.text
    assert result.counts["credential_field"] == 2
    assert result.counts["private_key"] == 1


def test_redacts_quoted_credential_field_without_swallowing_quotes() -> None:
    result = GuardrailPolicy.default().redact_text('password="hunter2"')

    assert result.text == 'password="[REDACTED:credential_field]"'
    assert result.counts["credential_field"] == 1
