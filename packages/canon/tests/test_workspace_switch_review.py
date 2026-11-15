"""`switch` against the host file as it really is: links on the way to it, a
Codex override or nested AGENTS files, CRLF and a byte-order mark, files canon
cannot read or write, and a file with no region yet."""
from __future__ import annotations

import io
import json
import os
import sys

import pytest

from canon.cli import run_cli
from canon.exit_codes import EX_CONFLICT, EX_IO, EX_OK, EX_SECURITY
from canon.workspace import authoring
from canon.workspace.identity import derive_identity
from canon.workspace.store import ProjectStore

from ._workspace_helpers import block, init_repo

REGION = "<!-- canon:begin scope=workspace -->\n<!-- canon:end -->\n"


def _run(argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli(argv, stdin=None, stdout=stdout, stderr=stderr, environ={})
    return code, stdout.getvalue(), stderr.getvalue()


@pytest.fixture()
def project(tmp_path):
    repo = init_repo(tmp_path / "repo", "https://github.com/o/repo")
    store = ProjectStore(tmp_path / "store", derive_identity(repo))
    store.put(block("voice", "Plain technical English.", 1))
    store.put(authoring.work_item(store, title="Write the tests"))
    args = ["--workspace", str(repo), "--store", str(store.root), "--home", str(tmp_path / "h")]
    return tmp_path, repo, store, args


def _switch(args, target, *extra):
    return _run(["--json", "switch", "--to", target, *extra, *args])


def _failure(out):
    return json.loads(out)["failure_code"]


def _dir_link(link, target):
    if sys.platform == "win32":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def test_a_junction_or_symlink_on_the_way_is_refused_and_nothing_lands_outside(project):
    tmp_path, repo, _, args = project
    outside = tmp_path / "outside"
    outside.mkdir()
    _dir_link(repo / ".cursor", outside)
    _dir_link(repo / ".github", outside)
    for target in ("cursor", "copilot"):
        code, out, _ = _switch(args, target, "--create")
        assert code == EX_SECURITY and _failure(out) == "unsafe_path", target
    assert list(outside.rglob("*")) == []


def test_a_file_link_is_refused(project):
    tmp_path, repo, _, args = project
    try:
        os.symlink(tmp_path / "planted.txt", repo / "GEMINI.md")
        (repo / "AGENTS.md").write_text(REGION, encoding="utf-8")
        os.symlink(repo / "AGENTS.md", repo / "CLAUDE.md")
    except OSError:
        pytest.skip("this account cannot create file symlinks")
    assert _failure(_switch(args, "gemini-cli", "--create")[1]) == "unsafe_path"
    assert not (tmp_path / "planted.txt").exists()
    assert _failure(_switch(args, "claude-code")[1]) == "unsafe_path"


def test_codex_override_file_refuses_the_switch(project):
    _, repo, _, args = project
    (repo / "AGENTS.md").write_text(REGION, encoding="utf-8")
    (repo / "AGENTS.override.md").write_text("# local override\n", encoding="utf-8")
    code, out, _ = _switch(args, "codex")
    assert code == EX_CONFLICT and _failure(out) == "shadowed"
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == REGION


def test_a_nested_agents_file_codex_would_cut_is_named(project):
    tmp_path, repo, store, args = project
    for n in range(150):
        store.put(authoring.work_item(store, title=f"Work item number {n} with some words"))
    (repo / "AGENTS.md").write_text("# Team notes\n" + REGION, encoding="utf-8")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "AGENTS.md").write_text("x" * 28000, encoding="utf-8")
    code, out, _ = _switch(args, "codex")
    assert code == EX_OK
    warnings = json.loads(out)["data"]["warnings"]
    assert any("pkg/AGENTS.md" in w and "truncates" in w for w in warnings), warnings


def test_the_codex_byte_limit_follows_its_config(project):
    tmp_path, repo, _, args = project
    (repo / "AGENTS.md").write_text("n" * 32700 + "\n" + REGION, encoding="utf-8")
    assert _failure(_switch(args, "codex")[1]) == "budget_too_small"
    config = tmp_path / "h" / ".codex"
    config.mkdir(parents=True)
    (config / "config.toml").write_text("project_doc_max_bytes = 65536\n", encoding="utf-8")
    assert _switch(args, "codex")[0] == EX_OK


def test_a_crlf_host_stays_crlf_and_an_eol_only_change_is_no_change(project):
    _, repo, _, args = project
    path = repo / "AGENTS.md"
    path.write_bytes(b"# Notes\r\n" + REGION.replace("\n", "\r\n").encode())
    assert _switch(args, "codex")[0] == EX_OK
    raw = path.read_bytes()
    assert raw.count(b"\n") == raw.count(b"\r\n")
    code, out, _ = _switch(args, "codex")
    assert code == EX_OK and json.loads(out)["data"]["status"] == "unchanged"


def test_a_byte_order_mark_an_editor_adds_is_tolerated(project):
    _, repo, _, args = project
    assert _switch(args, "codex", "--create")[0] == EX_OK
    path = repo / "AGENTS.md"
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    code, out, _ = _switch(args, "codex")
    assert code == EX_OK, out
    assert path.read_bytes().startswith(b"\xef\xbb\xbf<!-- canon:begin")


def test_a_file_where_a_folder_should_be_is_a_named_failure(project):
    _, repo, _, args = project
    (repo / ".cursor").write_text("not a folder", encoding="utf-8")
    code, out, _ = _switch(args, "cursor", "--create")
    assert code == EX_IO and _failure(out) == "io_error"


def test_a_file_that_is_not_utf8_is_a_named_failure(project):
    _, repo, _, args = project
    (repo / "GEMINI.md").write_bytes("# notes\n".encode("utf-16"))
    code, out, _ = _switch(args, "gemini-cli")
    assert code == EX_CONFLICT and "not a UTF-8 text file" in json.loads(out)["message"]


def test_a_file_with_no_region_is_told_the_two_lines_to_add(project):
    _, repo, _, args = project
    (repo / "CLAUDE.md").write_text("# My project\n", encoding="utf-8")
    code, out, _ = _switch(args, "claude-code", "--dry-run")
    message = json.loads(out)["message"]
    assert code == EX_CONFLICT
    assert "<!-- canon:begin scope=workspace -->" in message and "<!-- canon:end -->" in message


def test_a_switch_refused_by_a_held_lock_leaves_no_receipt(project):
    from canon.concurrency import acquire_run_lock, release_run_lock

    tmp_path, repo, store, args = project
    receipt = tmp_path / "r.json"
    lock = acquire_run_lock(store.root, f"canon-project-{store.project_id}")
    try:
        code, out, _ = _switch(args, "codex", "--create", "--receipt", str(receipt))
    finally:
        release_run_lock(lock)
    assert _failure(out) == "store_busy" and not receipt.exists()
    assert _switch(args, "codex", "--create", "--receipt", str(receipt))[0] == EX_OK
    assert json.loads(receipt.read_text(encoding="utf-8"))["schema"] == "canon.handoff-receipt/v1"
