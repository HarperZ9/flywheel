"""A bearer, authorization or API-key header is a secret when its value is
shaped like one. The value sits on the header's own line, and a word, a
number, a date or a path after the header name is left alone, so prose that
says "bearer" and an OAuth token response stay as written. Every
secret-shaped value is built at run time."""
from __future__ import annotations

import base64
import io

import pytest

from canon.cli import run_cli
from canon.exit_codes import EX_OK
from canon.workspace.scrub import find_secrets, scrub

from ._workspace_helpers import init_repo

V = "canaryV4lue" + "Q7x9"
HEX = "9f8e7d6c5b4a" * 4


@pytest.mark.parametrize("text", [
    "token_type: bearer\nexpires_in: 3600",
    "Authorization: Bearer\nContent-Type: application/json",
    "Use bearer authentication for the admin API",
    "api-key: required",
    "X-API-Key: optional",
    "x-auth-token: disabled",
    "Authorization: Token placeholder",
    "x-api-key: 2026-10-01",
    "X-API-Key: 12345678",
    "api-key: /etc/keys/api",
])
def test_a_header_name_followed_by_a_word_a_setting_or_a_new_line_stays(text):
    assert find_secrets(text) == [], text
    assert scrub(text).text == text


@pytest.mark.parametrize("text, secret", [
    ("Authorization: Bearer " + V, V),
    ("curl -H 'authorization: bearer mF_9.B5f-4" + ".1JqM'", "mF_9.B5f-4.1JqM"),
    ("Authorization: Basic " + base64.b64encode(("admin:" + V).encode()).decode(), "YWRtaW46"),
    ("X-API-Key: " + HEX, HEX),
    ("x-auth-token: " + V, V),
    ("Authorization: Bearer " + "m" * 20, "m" * 20),
])
def test_a_token_shaped_header_value_is_redacted(text, secret):
    result = scrub(text)
    assert result.hits, text
    assert secret not in result.text
    assert find_secrets(result.text) == []


@pytest.mark.parametrize("argv", [
    ["task", "Use bearer authentication for the admin API"],
    ["task", "Every request sends X-API-Key: required"],
    ["constraint", "The token endpoint returns token_type: bearer\nexpires_in: 3600"],
])
def test_a_record_that_names_a_header_is_stored(tmp_path, argv):
    repo = init_repo(tmp_path / "r", "https://github.com/o/r")
    base = ["--workspace", str(repo), "--store", str(tmp_path / "s")]
    stdout = io.StringIO()
    code = run_cli(["--json", "workspace", *argv, *base], stdin=None, stdout=stdout,
                   stderr=io.StringIO(), environ={})
    assert code == EX_OK, stdout.getvalue()
