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


def test_allowlist_refuses_a_root_outside_the_permitted_prefixes(tmp_path,
                                                                 monkeypatch):
    """With an allowlist set, an EXISTING directory outside every permitted
    prefix is refused by name -- existence is not authorization. Otherwise any
    request could scope the ToolExecutor to e.g. a home or credentials dir."""
    permitted = tmp_path / "allowed"
    permitted.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    monkeypatch.setenv("FLYWHEEL_WORKSPACE_ROOTS", str(permitted))
    # a root under the allowlisted prefix resolves
    inside = permitted / "proj"
    inside.mkdir()
    root, err = _resolve_workspace_root(str(inside), tmp_path)
    assert err is None and root == inside.resolve()
    # an existing dir outside the allowlist is refused by name
    root, err = _resolve_workspace_root(str(outside), tmp_path)
    assert err is not None and str(outside) in err
    assert root == tmp_path                    # the default comes back, not the ask


def test_no_allowlist_preserves_open_resolution(tmp_path, monkeypatch):
    """Unset allowlist = unchanged behavior: any existing dir still resolves."""
    monkeypatch.delenv("FLYWHEEL_WORKSPACE_ROOTS", raising=False)
    ws = tmp_path / "anywhere"
    ws.mkdir()
    root, err = _resolve_workspace_root(str(ws), tmp_path)
    assert err is None and root == ws.resolve()
