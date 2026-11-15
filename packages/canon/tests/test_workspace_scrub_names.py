"""The words after a password word in a name decide what the name holds. A
word that describes the password (`min`, `policy`, `path`, `url`) makes the
name about the password, so its value must look random. Any other word
(`prod`, `admin`, `2`, `confirmation`) names which password it is, so a
human-chosen password is redacted. After a token or key word any following
word makes the name a description, and a token under it is caught by its
random shape. A value that starts at `/` after a name that holds a secret is
a path only when it has a second segment and is not shaped like a base64
key. Every secret-shaped value is built at run time."""
from __future__ import annotations

import io
import json

import pytest

from canon.cli import run_cli
from canon.exit_codes import EX_SECURITY
from canon.workspace.scrub import find_secrets, scrub

from ._workspace_helpers import init_repo

PW = "Summer" + "2024!"


@pytest.mark.parametrize("text, secret", [
    ("DB_PASSWORD_PROD=" + PW, PW),
    ("POSTGRES_PASSWORD_PROD=" + PW, PW),
    ('MYSQL_PASSWORD_STAGING: "Winter' + '2023#"', "Winter2023#"),
    ("PASSWORD_ADMIN=hunter" + "2", "hunter2"),
    ("ADMIN_PASSWORD_2=let" + "mein", "letmein"),
    ("db_password_prod: " + PW, PW),
    ('{"password_confirmation": "' + PW + '"}', PW),
    ('{"passwordConfirmation": "' + PW + '"}', PW),
    ("SMTP_PASS_PROD=" + PW, PW),
    ("GITHUB_TOKEN_CI=" + "a8f3k2j9" + "x7m1q5w4", "a8f3k2j9"),
    ("DB_PASSWORD=/hunter" + "2", "hunter2"),
    ("DB_PASSWORD=/hunter" + "22", "hunter22"),
    ("AWS_SECRET_ACCESS_KEY=/wJalrXUtnFEMI/K7MDENG/bPxRfiCY" + "EXAMPLE", "wJalrXUtnFEMI"),
    ("AWS_SECRET_ACCESS_KEY=/ggVbgxoXbOTYWulzQug" + "nxNX/gsamyKxkoVVFFKC", "ggVbgxoX"),
    ("key=/ggVbgxoXbOTYWulzQug" + "nxNX/gsamyKxkoVVFFKC", "ggVbgxoX"),
])
def test_a_secret_under_a_name_that_says_which_one_is_redacted(text, secret):
    result = scrub(text)
    assert result.hits, text
    assert secret not in result.text
    assert find_secrets(result.text) == []


@pytest.mark.parametrize("text", [
    "password_policy: strict",
    "PASSWORD_MIN_LENGTH=12",
    "password_hint: favourite colour",
    "token_type_hint: access_token",
    "pass_through: enabled",
    "TOKEN_URL_PROD=https://auth.example.com/oauth/token",
    "secret_name: prod-db-secret",
    "DB_PASSWORD_FILE=/run/secrets/db_password",
    "DB_PASSWORD=/run/secrets/db_password",
    "KEY_DIR=/Users/dev/Project2",
    "password_reset: enabled",
    "PASSWORD_MANAGER=bitwarden",
    "credential.helper=manager-core",
])
def test_a_name_that_describes_the_secret_keeps_a_plain_value(text):
    assert find_secrets(text) == [], text
    assert scrub(text).text == text


def test_the_store_refuses_a_task_that_carries_a_suffixed_password(tmp_path):
    repo = init_repo(tmp_path / "r", "https://github.com/o/r")
    base = ["--workspace", str(repo), "--store", str(tmp_path / "s")]
    task = ('curl -d {"password_confirmation": "' + PW + '"} rotate '
            "POSTGRES_PASSWORD_PROD=" + PW)
    stdout = io.StringIO()
    code = run_cli(["--json", "workspace", "task", task, *base], stdin=None,
                   stdout=stdout, stderr=io.StringIO(), environ={})
    assert code == EX_SECURITY
    assert json.loads(stdout.getvalue())["failure_code"] == "secret_quarantine"
    assert PW not in stdout.getvalue()
    listed = io.StringIO()
    run_cli(["workspace", "list", *base], stdin=None, stdout=listed,
            stderr=io.StringIO(), environ={})
    assert PW not in listed.getvalue()
