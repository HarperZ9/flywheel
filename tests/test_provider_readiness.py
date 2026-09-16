"""False-success guards for provider readiness rows."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import endpoint_registry, providers
from harness.endpoint_registry import unified_roster


CONTROL_OR_WHITESPACE = tuple(chr(i) for i in range(32)) + ("\x7f", " ")
BAD_OPENAI_BASE_URLS = (
    "",
    "not-a-url",
    "ftp://example.test/v1",
    "http://[",
    "http://example.test:99999/v1",
    "http://example.test:abc/v1",
    "https://api.example.test/v 1",
    "https://api.example.test/\n/v1",
    "https://api.example.test/\x1b/v1",
    r"https://api.example.test\v1",
    "http:///v1",
    "https://user:pass@example.test/v1",
)


@pytest.mark.parametrize("bad_char", CONTROL_OR_WHITESPACE)
def test_safe_base_url_rejects_c0_del_and_whitespace_anywhere(bad_char):
    assert providers.safe_base_url(
        f"https://api.example.test/v{bad_char}1") == ""


@pytest.mark.parametrize("url", (
    "https://api.example.test/v1",
    "http://127.0.0.1:9999/v1",
    "http://[::1]:11434/v1",
))
def test_safe_base_url_preserves_ordinary_valid_urls(url):
    assert providers.safe_base_url(url) == url


def test_codex_cli_binary_only_is_account_unknown_not_usable(monkeypatch):
    monkeypatch.setattr(endpoint_registry.shutil, "which",
                        lambda binary: f"/usr/bin/{binary}")
    monkeypatch.setattr(
        endpoint_registry.claude_cli_auth,
        "public_status",
        lambda: {"state": "authenticated", "authenticated": True,
                 "cli_present": True, "executable": "claude.exe"},
    )

    r = unified_roster()
    codex = next(e for e in r["endpoints"] if e["name"] == "codex-cli")
    assert {k: codex[k] for k in (
        "credential", "account_required", "account_state",
        "account_authenticated", "receipt_capable")} == {
        "credential": "cli-auth",
        "account_required": True,
        "account_state": "unknown",
        "account_authenticated": False,
        "receipt_capable": False,
    }
    assert "codex-cli" not in r["usable_names"]


def test_byo_openai_compatible_requires_safe_configured_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key-present")
    for base_url in BAD_OPENAI_BASE_URLS:
        if base_url:
            monkeypatch.setenv("OPENAI_BASE_URL", base_url)
        else:
            monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        r = unified_roster()
        byo = next(e for e in r["endpoints"] if e["name"] == "openai-compatible")
        assert {k: byo[k] for k in (
            "credential", "configured", "receipt_capable", "host")} == {
            "credential": "present", "configured": False,
            "receipt_capable": False, "host": ""}
        assert "openai-compatible" not in r["usable_names"]

    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
    r = unified_roster()
    byo = next(e for e in r["endpoints"] if e["name"] == "openai-compatible")
    assert {k: byo[k] for k in ("configured", "receipt_capable", "host")} == {
        "configured": True, "receipt_capable": True, "host": "127.0.0.1:9999"}
    assert "openai-compatible" in r["usable_names"]
