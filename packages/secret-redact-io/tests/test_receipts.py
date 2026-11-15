from __future__ import annotations

import json

from secret_redact_io import GuardrailReceipt


def test_receipt_json_is_stable_and_hash_only() -> None:
    receipt = GuardrailReceipt.create(
        operation="read",
        target="sample.txt",
        raw_bytes=b"password=secret",
        redacted_text="password=[REDACTED:credential_field]",
        redactions={"credential_field": 1},
    )

    payload = receipt.to_json()
    data = json.loads(payload)

    assert "secret" not in payload
    assert data["operation"] == "read"
    assert data["target"] == "sample.txt"
    assert data["raw_bytes"] == len(b"password=secret")
    assert data["redacted_bytes"] == len("password=[REDACTED:credential_field]".encode())
    assert data["redactions"]["credential_field"] == 1
    assert len(receipt.input_sha256) == 64
    assert len(receipt.redacted_sha256) == 64
