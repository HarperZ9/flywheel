import json

from adapters.proof_surface_receipt import receipt, verdict_line


class CoreResult:
    returncode = 0
    stdout = "MATCH README.md\n"


def test_receipt_json_omits_authority_tokens():
    data = receipt(
        "verify",
        [{"name": "README.md", "digest": {"sha256": "0" * 64}}],
        CoreResult(),
    )

    encoded = json.dumps(data)
    assert "TRUSTED" not in encoded
    assert "APPROVED" not in encoded
    assert "SAFE" not in encoded


def test_verdict_line_requires_whole_governed_token():
    assert verdict_line("MISMATCH README.md\n") == ("UNVERIFIABLE", "")
    assert verdict_line("MATCH README.md\n") == ("MATCH", "MATCH README.md")


def test_receipt_refuses_authority_token_from_core_stdout():
    class AuthorityResult:
        returncode = 0
        stdout = "result=TRUSTED README.md\n"

    data = receipt(
        "verify",
        [{"name": "README.md", "digest": {"sha256": "0" * 64}}],
        AuthorityResult(),
    )

    encoded = json.dumps(data)
    assert data["verdict"] == "UNVERIFIABLE"
    assert data["evidence"]["stdout_verdict_line"] == "authority token refused by receipt adapter"
    assert "TRUSTED" not in encoded
