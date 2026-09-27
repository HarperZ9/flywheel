"""S16: the read is checked on the handle, after the open. A project folder
swapped for a junction between the session route's check and the background
read reaches a file outside the client root, and the import refuses it as
OUTSIDE_ROOT; nothing is stored. The prefix probes open by handle too."""
import shutil

import pytest

from harness.trace_import_core import ImportStore
from harness.trace_import_read import SourceRefused, read_prefix, read_source
from harness.trace_import_session import prepare, run
from import_fixtures import OWNER, PROJECT, SESSION, claude_tree, link_dir
from trace_enc_fakes import StreamTestProvider, using


def test_a_read_outside_the_root_is_refused(tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "x.jsonl").write_bytes(b"{}\n")
    with pytest.raises(SourceRefused) as refused:
        read_source(outside / "x.jsonl", lambda chunk: None, root=root)
    assert refused.value.code == "OUTSIDE_ROOT"
    got = []
    read_prefix(outside / "x.jsonl", 2, got.append)
    assert b"".join(got) == b"{}"


def test_a_folder_swapped_for_a_junction_after_the_check_is_refused(tmp_path):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    root, _, _ = claude_tree(tmp_path)
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    shutil.copy(root / "projects" / PROJECT / f"{SESSION}.jsonl", decoy / f"{SESSION}.jsonl")
    with using(StreamTestProvider()):
        resolved_root, path = prepare("claude-code", SESSION, root=root, now=1.0)
        shutil.rmtree(root / "projects" / PROJECT)
        if not link_dir(root / "projects" / PROJECT, decoy):
            pytest.skip("cannot create a junction here")
        result = run(home, OWNER, "claude-code", SESSION, resolved_root, path)
        assert result["imported"] == 0 and result["refused"] == {"OUTSIDE_ROOT": 1}
        assert ImportStore(home, OWNER).item_refs() == []
