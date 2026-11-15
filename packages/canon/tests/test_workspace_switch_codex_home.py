"""Codex reads its config from CODEX_HOME when that is set, else from
~/.codex, so the byte budget a switch to Codex refuses at comes from the same
place. The refusal names the setting that raises it."""
from __future__ import annotations

import io
import json

import pytest

from canon.cli import run_cli
from canon.exit_codes import EX_OK
from canon.workspace.identity import derive_identity
from canon.workspace.store import ProjectStore

from ._workspace_helpers import block, init_repo

REGION = "<!-- canon:begin scope=workspace -->\n<!-- canon:end -->\n"


@pytest.fixture()
def project(tmp_path):
    repo = init_repo(tmp_path / "repo", "https://github.com/o/repo")
    store = ProjectStore(tmp_path / "store", derive_identity(repo))
    store.put(block("voice", "Plain technical English.", 1))
    (repo / "AGENTS.md").write_text("n" * 32700 + "\n" + REGION, encoding="utf-8")
    args = ["--workspace", str(repo), "--store", str(store.root), "--home", str(tmp_path / "h")]
    return tmp_path, args


def _switch(args, environ):
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli(["--json", "switch", "--to", "codex", *args], stdin=None, stdout=stdout,
                   stderr=stderr, environ=environ)
    return code, json.loads(stdout.getvalue())


def _config(directory, budget):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "config.toml").write_text(f"project_doc_max_bytes = {budget}\n",
                                           encoding="utf-8")


def test_the_budget_follows_the_config_under_codex_home(project):
    tmp_path, args = project
    _config(tmp_path / "codex-home", 65536)
    code, payload = _switch(args, {"CODEX_HOME": str(tmp_path / "codex-home")})
    assert code == EX_OK, payload


def test_codex_home_replaces_the_home_config_rather_than_adding_to_it(project):
    tmp_path, args = project
    _config(tmp_path / "h" / ".codex", 65536)
    (tmp_path / "codex-home").mkdir()
    code, payload = _switch(args, {"CODEX_HOME": str(tmp_path / "codex-home")})
    assert payload["failure_code"] == "budget_too_small"
    assert _switch(args, {})[0] == EX_OK


def test_the_refusal_names_the_setting_that_raises_the_budget(project):
    _, args = project
    code, payload = _switch(args, {})
    assert payload["failure_code"] == "budget_too_small"
    assert "project_doc_max_bytes" in payload["message"]
    assert "CODEX_HOME" in payload["message"]
