"""The secret rules read the value's shape, not the name alone. A name that
carries a credential word says what a value is for; a number, a date, a path,
a boolean or a short word after it is a setting, and a name that qualifies the
credential (`token_type`, `KEY_COUNT`, `private_key_path`) needs a value that
looks random. Every secret-shaped value is built at run time."""
from __future__ import annotations

import io
import json

import pytest

from canon.cli import run_cli
from canon.exit_codes import EX_OK
from canon.workspace.scrub import find_secrets, scrub

from ._workspace_helpers import init_repo

V = "canaryV4lue" + "Q7x9"
HEX = "9f8e7d6c5b4a" * 4


@pytest.mark.parametrize("argv", [
    ["task", "Set session_token_ttl=3600 in prod"],
    ["constraint", "CI floor is pass_rate=0.95"],
    ["task", "Raise KEY_COUNT=1000 for the shard map"],
    ["task", "Set KEY_VAULT_NAME=kv-prod-eastus2 in staging"],
    ["task", "Rename key=feature_flag_v2 before release"],
])
def test_a_hand_typed_setting_is_stored_as_written(tmp_path, argv):
    repo = init_repo(tmp_path / "r", "https://github.com/o/r")
    base = ["--workspace", str(repo), "--store", str(tmp_path / "s")]
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli(["--json", "workspace", *argv, *base], stdin=None, stdout=stdout,
                   stderr=stderr, environ={})
    assert code == EX_OK, stdout.getvalue()
    listed = io.StringIO()
    run_cli(["workspace", "list", *base], stdin=None, stdout=listed,
            stderr=io.StringIO(), environ={})
    assert argv[1] in listed.getvalue()


@pytest.mark.parametrize("text", [
    "KEY_PREFIX=canon",
    "token_type: bearer",
    "private_key_path: ~/.ssh/id_ed25519",
    "Cookie: consent=yes",
    "?key=value123",
    "second pass: 2026-10-01",
    "Set session_token_ttl=3600 in prod",
    "CI floor is pass_rate=0.95",
    "Raise KEY_COUNT=1000 for the shard map",
    '{"max_tokens": "4096"}',
    '{"token_type": "bearer"}',
    "API_KEY=canon",
    "GITHUB_TOKEN=false",
    "token_expiry: 2026-10-01T12:00:00Z",
    "SECRETS_DIR=/run/secrets",
    "MONKEY=banana",
])
def test_a_setting_after_a_credential_word_is_not_a_secret(text):
    assert find_secrets(text) == [], text
    assert scrub(text).text == text


@pytest.mark.parametrize("text", [
    "SECRET_KEY_BASE=" + HEX,
    "token_value: " + V,
    "private_key_path: ~/.ssh/" + V + "Xy",
    "?key=" + V + "abc",
    "?token=value123",
    "API_KEY=" + V,
    "DB_PASSWORD=letmein",
    "Cookie: sessionid=" + V,
    '{"access_token": "' + V + '"}',
    "AWS_SECRET_ACCESS_KEY=/K7MDENGbPxRfiCYEXAMPLEKEYwJalrXUtnFEMI",
])
def test_a_secret_shaped_value_is_still_redacted(text):
    result = scrub(text)
    assert result.hits, text
    for piece in (V, HEX, "value123", "letmein", "wJalrXUtnFEMI"):
        assert piece not in result.text
    assert find_secrets(result.text) == []


UUID = "1234abcd-12ab-" + "34cd-56ef-1234567890ab"


@pytest.mark.parametrize("text", [
    "key=feature_flag_v2",
    "KEY=release-2026-10",
    "key: main-v2-branch",
    "KEY_VAULT_NAME=kv-prod-eastus2",
    "CACHE_KEY_PREFIX=v2_prod_cache",
    "KEY_PAIR_NAME=deploy-keypair-2024",
    "AUTH_DOMAIN=dev-abc123.us.auth0.com",
    "cache_key: user:1234:profile",
    "kms_key_id: arn:aws:kms:us-east-1:123456789012:key/" + UUID,
    "Cookie: cookie_consent=granted_2024",
    "Cookie: _ga=GA1.2.1234567890.1234567890",
])
def test_an_identifier_with_a_version_date_or_region_digit_is_not_random(text):
    """Each run of letters and digits here is a word followed by a number, so
    none of these values looks random."""
    assert find_secrets(text) == [], text
    assert scrub(text).text == text


@pytest.mark.parametrize("text, secret", [
    ("key=" + HEX, HEX),
    ("auth: " + "a8f3k2j9" + "x7m1q5w4", "a8f3k2j9"),
    ("KEY_PREFIX=" + UUID, "1234abcd"),
    ("CACHE_KEY=build-" + "3f2a9c1b7e", "3f2a9c1b7e"),
    ("Cookie: _session=" + V, V),
])
def test_a_run_that_is_not_a_word_and_a_number_is_random(text, secret):
    result = scrub(text)
    assert result.hits, text
    assert secret not in result.text
