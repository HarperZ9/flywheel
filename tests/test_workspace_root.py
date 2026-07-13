"""The workspace-root resolver must refuse what does not exist and scope
what does: a bad root is a named refusal (never a silent substitute), a good
root is resolved absolute, and no root means the gateway's own default."""

from pathlib import Path

from harness.gateway import _resolve_workspace_root


def test_no_root_uses_default(tmp_path):
    root, err = _resolve_workspace_root(None, tmp_path)
    assert err is None and root == tmp_path
    root, err = _resolve_workspace_root("", tmp_path)
    assert err is None and root == tmp_path


def test_existing_directory_is_resolved_absolute(tmp_path):
    ws = tmp_path / "project"
    ws.mkdir()
    root, err = _resolve_workspace_root(str(ws), tmp_path)
    assert err is None
    assert root == ws.resolve()
    assert root.is_absolute()


def test_missing_directory_is_refused_by_name(tmp_path):
    requested = str(tmp_path / "nope")
    root, err = _resolve_workspace_root(requested, tmp_path)
    assert err is not None and requested in err
    # The default comes back so the caller can see what would have run,
    # but the gateway returns 400 on err instead of proceeding.
    assert root == tmp_path


def test_file_is_not_a_workspace(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    _, err = _resolve_workspace_root(str(f), tmp_path)
    assert err is not None
