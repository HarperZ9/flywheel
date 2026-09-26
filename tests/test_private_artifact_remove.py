"""SP-21: removal inside a pinned private root, by handle, never following a
link. A junction or symbolic link is removed as a link and its target stays."""
import os
import subprocess
import sys

import pytest

from harness.private_artifact_fs import root_identity
from harness.private_artifact_remove import RemovalError, remove


def _tree(root):
    (root / "item" / "nested").mkdir(parents=True)
    (root / "item" / "a.json").write_bytes(b"a")
    (root / "item" / "nested" / "b.json").write_bytes(b"b")
    (root / "keep.json").write_bytes(b"keep")


def _link_dir(link, target) -> bool:
    if sys.platform == "win32":
        done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                              capture_output=True)
        return done.returncode == 0
    os.symlink(target, link, target_is_directory=True)
    return True


def test_a_tree_inside_the_root_is_removed_and_siblings_stay(tmp_path):
    root = tmp_path / "root"
    _tree(root)
    counts = remove(root, "item", expected=root_identity(root))
    assert counts == {"files": 2, "dirs": 2, "links": 0}
    assert not (root / "item").exists() and (root / "keep.json").exists()


def test_a_single_file_is_removed(tmp_path):
    root = tmp_path / "root"
    _tree(root)
    assert remove(root, "item/a.json")["files"] == 1
    assert not (root / "item" / "a.json").exists() and (root / "item" / "nested").exists()


def test_a_junction_or_symlink_is_removed_as_a_link_and_its_target_stays(tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    _tree(root)
    outside.mkdir()
    (outside / "precious.txt").write_bytes(b"do not touch")
    if not _link_dir(root / "item" / "link", outside):
        pytest.skip("cannot create a directory link here")
    counts = remove(root, "item")
    assert counts["links"] == 1
    assert not (root / "item").exists()
    assert (outside / "precious.txt").read_bytes() == b"do not touch"


def test_a_link_given_as_the_target_is_removed_itself(tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "precious.txt").write_bytes(b"x")
    if not _link_dir(root / "link", outside):
        pytest.skip("cannot create a directory link here")
    assert remove(root, "link") == {"files": 0, "dirs": 0, "links": 1}
    assert (outside / "precious.txt").exists()


def test_a_changed_root_identity_is_refused(tmp_path):
    root = tmp_path / "root"
    _tree(root)
    identity = root_identity(root)
    root.rename(tmp_path / "moved")
    _tree(root)
    with pytest.raises(RemovalError) as refused:
        remove(root, "item", expected=identity)
    assert refused.value.code == "ROOT_CHANGED"
    assert (root / "item" / "a.json").exists()


@pytest.mark.parametrize("rel", ["../outside", "item/../../x", "C:/abs", "/abs", ""])
def test_a_path_that_leaves_the_root_is_refused(tmp_path, rel):
    root = tmp_path / "root"
    _tree(root)
    with pytest.raises(RemovalError) as refused:
        remove(root, rel)
    assert refused.value.code == "UNSAFE_PATH"


def test_a_missing_target_is_reported_not_raised(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    assert remove(root, "absent") == {"files": 0, "dirs": 0, "links": 0}
