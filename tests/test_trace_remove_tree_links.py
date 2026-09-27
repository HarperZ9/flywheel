"""A whole-store deletion and import staging discard remove a tree by
handle: a junction or symbolic link inside it is removed as a link, and the
folder it points at keeps its files (rglob would have deleted them)."""
from harness.trace_keystore_adapters import delete_all as keys_delete_all
from harness.trace_meta_adapters import remove_tree
from import_fixtures import link_dir


def test_a_junction_in_a_removed_tree_keeps_its_target(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_bytes(b"not custody")
    tree = tmp_path / "state" / "presence"
    (tree / "v1").mkdir(parents=True)
    (tree / "v1" / "a.json").write_bytes(b"{}")
    assert link_dir(tree / "v1" / "linked", outside)
    assert remove_tree(tree) >= 1
    assert not tree.exists()
    assert (outside / "keep.txt").read_bytes() == b"not custody"


def test_the_keystore_delete_does_not_follow_a_junction(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_bytes(b"not custody")
    keys = tmp_path / "home" / "state" / "keys" / "v1"
    keys.mkdir(parents=True)
    assert link_dir(keys / "linked", outside)
    keys_delete_all(tmp_path / "home")
    assert (outside / "keep.txt").exists()
    assert remove_tree(tmp_path / "missing") == 0
