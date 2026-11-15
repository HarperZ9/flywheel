"""A URL's user part: the password of any `user:password@` is redacted, and a
user part with no password is redacted when it is shaped like a token. A
plain user name, an email address, a port (followed by a path, a query or a
fragment) and a placeholder stay as written. Every token-shaped
value is built at run time."""
from __future__ import annotations

import io

import pytest

from canon.cli import run_cli
from canon.exit_codes import EX_OK
from canon.workspace.scrub import find_secrets, scrub

from ._workspace_helpers import init_repo

V = "canaryV4lue" + "Q7x9"


@pytest.mark.parametrize("text, secret", [
    ("https://" + V + "@github.com/o/r.git", V),
    ("https://aB3" + "dE5fG@host.example/x", "aB3dE5fG"),
    ("https://" + "9f8e7d6c5b4a3210" * 2 + "@github.com/o/r", "9f8e7d6c5b4a3210"),
    ("https://deploy:" + "pw" + "@host.example/x", ":pw@"),
    ("ssh://git:" + "hunter" + "@host.example/o/r", "hunter"),
    ("https://oauth2:" + V + "@gitlab.com/o/r.git", V),
])
def test_a_token_or_a_password_in_a_url_user_part_is_redacted(text, secret):
    result = scrub(text)
    assert result.hits.get("connection-string") == 1, text
    assert secret not in result.text
    assert find_secrets(result.text) == []


@pytest.mark.parametrize("text", [
    "ssh://git@github.com/o/r.git",
    "https://first.last@example.com/repo",
    "https://github-actions-bot@github.com/o/r",
    "https://x-access-token@github.com/o/r",
    "https://user123@host.example/x",
    "https://registry.npmjs.org:443/@scope/pkg",
    "https://${GITHUB_TOKEN}@github.com/o/r",
    "https://deploy:<password>@host.example/x",
    "ssh://deploy-bot-2024@git.example.com/o/r",
    "sftp://backup-user-01@files.example.com",
    "https://GitHubUser42@github.com/o/r.git",
    "https://ci-runner-01@git.example.com/o/r.git",
    "https://john.doe%40example.com@host.example.com/x",
    "http://localhost:8080?next=user@example.com",
    "http://localhost:3000#/users/@me",
])
def test_a_plain_user_name_a_port_and_a_placeholder_stay(text):
    assert find_secrets(text) == [], text
    assert scrub(text).text == text


@pytest.mark.parametrize("task", [
    "Clone ssh://deploy-bot-2024@git.example.com/o/r on the runner",
    "Pin https://GitHubUser42@github.com/o/r.git as the mirror",
    "Open http://localhost:8080?next=user@example.com after login",
])
def test_a_task_that_names_a_service_account_url_is_stored(tmp_path, task):
    repo = init_repo(tmp_path / "r", "https://github.com/o/r")
    base = ["--workspace", str(repo), "--store", str(tmp_path / "s")]
    stdout = io.StringIO()
    code = run_cli(["--json", "workspace", "task", task, *base], stdin=None,
                   stdout=stdout, stderr=io.StringIO(), environ={})
    assert code == EX_OK, stdout.getvalue()
