"""Workspace state hashes (landscape import 7): a run's pre and post
workspace are content-addressed, so 'the agent changed nothing' and 'the
revert restored everything' are checkable statements. Caps are visible —
skipped files are counted, never silently omitted."""

from harness.workspace_state import workspace_snapshot


def _tree(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "b.py").write_text("y = 2\n", encoding="utf-8")
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")
    return tmp_path


def test_snapshot_is_deterministic_and_ignores_vcs_internals(tmp_path):
    _tree(tmp_path)
    a = workspace_snapshot(tmp_path)
    b = workspace_snapshot(tmp_path)
    assert a["workspace_sha256"] == b["workspace_sha256"]
    assert a["files"] == 2  # .git contents never counted
    assert len(a["workspace_sha256"]) == 64


def test_any_content_change_moves_the_hash(tmp_path):
    _tree(tmp_path)
    before = workspace_snapshot(tmp_path)["workspace_sha256"]
    (tmp_path / "a.py").write_text("x = 2\n", encoding="utf-8")
    after = workspace_snapshot(tmp_path)["workspace_sha256"]
    assert before != after


def test_caps_are_visible_not_silent(tmp_path):
    _tree(tmp_path)
    (tmp_path / "big.bin").write_bytes(b"0" * 64)
    doc = workspace_snapshot(tmp_path, max_bytes=16)
    assert doc["skipped"] == 1
    assert "counted" in doc["note"]
