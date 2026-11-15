"""A URL query parameter is one name and one value. The value ends at the next
`&` or `#`, and it takes the same name and shape rules as an assignment, so a
later parameter never joins it. A command-line flag (`--api-token=...`) is a
name too. Every secret-shaped value is built at run time."""
from __future__ import annotations

import io

import pytest

from canon.cli import run_cli
from canon.exit_codes import EX_OK
from canon.workspace.scrub import find_secrets, scrub

from ._workspace_helpers import init_repo

V = "canaryV4lue" + "Q7x9"
HEX = "9f8e7d6c5b4a" * 4


@pytest.mark.parametrize("text", [
    "?key=value123&page=2",
    "https://example.com/s?q=1&key=value123&page=2",
    "?key=value123#top",
    "https://example.com/?token=bearer&page=2",
    "https://example.com/?sort_key=name&dir=asc&page=10",
    "https://example.com/?country_code=US&code_style=pep8",
    "https://cdn.example.com/app.js?key=main&v=" + "a8f3k2j9x7m1",
])
def test_a_plain_query_parameter_stays_whatever_follows_it(text):
    assert find_secrets(text) == [], text
    assert scrub(text).text == text


@pytest.mark.parametrize("text, secret, kept", [
    ("https://api.example.com/x?access_token=" + V + "&page=2", V, "&page=2"),
    ("https://db.example.com/?db_password=hunter" + "22&x=1", "hunter22", "&x=1"),
    ("https://gitlab.example.com/api?private_token=" + V + "#top", V, "#top"),
    ("https://s3.example.com/o?X-Amz-Signature=" + HEX + "&v=1", HEX, "&v=1"),
    ("deploy --api-token=" + V + " --verbose", V, " --verbose"),
    ("make&&DB_PASSWORD=hunter" + "22 ./run", "hunter22", " ./run"),
])
def test_a_secret_query_value_or_flag_is_redacted_up_to_its_end(text, secret, kept):
    result = scrub(text)
    assert result.hits, text
    assert secret not in result.text
    assert result.text.endswith(kept)
    assert find_secrets(result.text) == []


def test_a_task_that_names_a_paged_url_is_stored(tmp_path):
    repo = init_repo(tmp_path / "r", "https://github.com/o/r")
    base = ["--workspace", str(repo), "--store", str(tmp_path / "s")]
    task = "Check https://example.com/search?key=value123&page=2 for the paging bug"
    stdout = io.StringIO()
    code = run_cli(["--json", "workspace", "task", task, *base], stdin=None,
                   stdout=stdout, stderr=io.StringIO(), environ={})
    assert code == EX_OK, stdout.getvalue()
