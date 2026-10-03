"""SP-30 on Windows: the importer opens each source sharing read, write and
delete, so a client sweep or a Codex compression renaming the file during the
read proceeds, and the importer sees the changed identity and stores nothing."""
import sys

import pytest

from harness.trace_import_claude import plan_claude
from harness.trace_import_core import run_import
from import_fixtures import OWNER, PROJECT, SESSION, claude_tree
from trace_enc_fakes import StreamTestProvider, using


@pytest.fixture
def tree(tmp_path):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    root, _, _ = claude_tree(tmp_path)
    with using(StreamTestProvider()):
        yield home, root


@pytest.mark.skipif(sys.platform != "win32", reason="Windows sharing modes")
def test_a_rename_during_the_read_succeeds_and_gives_source_changed(tree):
    home, root = tree
    target = root / "projects" / PROJECT / f"{SESSION}.jsonl"
    renamed = target.with_name("renamed-by-a-sweep.jsonl")

    def rename(path):
        if path == target:
            path.rename(renamed)  # the importer's handle must allow this
    result = run_import(home, plan_claude(home, root=root), on_read=rename)
    assert renamed.exists() and not target.exists()
    assert result["refused"] == {"SOURCE_CHANGED": 1}
