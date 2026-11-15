"""The markdown target carries no instruction block, and the command says so:
on stderr beside a printed brief, on the result line beside a written one,
and in `--json` as a count and a reason. A switch to markdown warns the same
way, and a pool with no block says nothing."""
from __future__ import annotations

import io
import json

import pytest

from canon.cli import run_cli
from canon.exit_codes import EX_OK
from canon.workspace import authoring
from canon.workspace.identity import derive_identity
from canon.workspace.store import ProjectStore

from ._workspace_helpers import block, init_repo

REASON = "the markdown target has no instruction file"


def _run(argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli(argv, stdin=None, stdout=stdout, stderr=stderr, environ={})
    return code, stdout.getvalue(), stderr.getvalue()


@pytest.fixture()
def args(tmp_path):
    repo = init_repo(tmp_path / "repo", "https://github.com/o/repo")
    store = ProjectStore(tmp_path / "store", derive_identity(repo))
    store.put(block("voice", "Plain technical English.", 1))
    store.put(block("review", "Review every diff.", 2))
    store.put(authoring.work_item(store, title="Write the tests"))
    return ["--workspace", str(repo), "--store", str(store.root)]


def test_a_printed_markdown_brief_says_on_stderr_what_it_left_out(args):
    code, out, err = _run(["handoff", "--to", "markdown", *args])
    assert code == EX_OK
    assert out.startswith("# Resume brief") and "instruction block" not in out
    assert "2 instruction blocks omitted" in err and REASON in err


def test_the_json_result_counts_the_omitted_blocks_and_names_the_reason(args):
    code, out, _ = _run(["--json", "handoff", "--to", "markdown", *args])
    payload = json.loads(out)
    assert code == EX_OK
    assert "2 instruction blocks omitted" in payload["message"]
    omitted = payload["data"]["omitted_blocks"]
    assert omitted["count"] == 2 and sorted(omitted["ids"]) == ["review", "voice"]
    assert REASON in omitted["reason"]


def test_a_written_markdown_brief_says_it_on_the_result_line(args, tmp_path):
    code, out, _ = _run(["handoff", "--to", "markdown", "--out", str(tmp_path / "B.md"), *args])
    assert code == EX_OK and "2 instruction blocks omitted" in out


def test_a_switch_to_markdown_warns_about_the_omitted_blocks(args):
    code, out, _ = _run(["--json", "switch", "--to", "markdown", *args])
    data = json.loads(out)["data"]
    assert code == EX_OK and data["omitted_blocks"]["count"] == 2
    assert any("2 instruction blocks omitted" in w for w in data["warnings"])


def test_a_target_with_a_file_omits_nothing(args):
    code, out, err = _run(["--json", "handoff", "--to", "codex", *args])
    assert code == EX_OK and err == ""
    assert json.loads(out)["data"]["omitted_blocks"] == {"count": 0, "ids": [], "reason": None}
