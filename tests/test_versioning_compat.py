"""Falsifiers for the compatibility promises in docs/VERSIONING.md."""
import json
import re
import shutil
from pathlib import Path

import pytest

from harness.code_session import resume, store
from harness.code_session.backends import build_agent
from harness.code_session.session import new_session
from tests.test_code_session import ScriptBackend, _bare_runner

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "compat"
OLD_ID = "20261015-085137-866364"


def _home_with_old_session(tmp_path):
    home = tmp_path / "home"
    shutil.copytree(FIXTURES / "code-session-1.6.0", home / "sessions")
    return home


def test_a_session_saved_by_1_6_0_loads_and_verifies(tmp_path):
    meta, ledger = store.load(str(_home_with_old_session(tmp_path)), OLD_ID)
    assert meta["schema"] == store.SCHEMA == "flywheel.code-session/v1"
    assert ledger.verify() and meta["ledger_head"] == ledger.checkpoint()
    assert any(e.kind == "save" for e in ledger.entries)


def test_a_session_saved_by_1_6_0_resumes_and_takes_a_new_turn(tmp_path):
    home = _home_with_old_session(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    s = new_session(build_agent([ScriptBackend(["still here"])]), str(work), mode="auto",
                    runner=_bare_runner)
    meta = resume.restore(s, str(home), OLD_ID)
    assert s.turns == meta["turns"] == 1
    s.turn("go on")
    assert s.ledger.verify()
    assert [e.kind for e in s.ledger.entries].count("resume") == 1


def test_an_edited_old_conversation_is_refused(tmp_path):
    home = _home_with_old_session(tmp_path)
    meta_path = home / "sessions" / OLD_ID / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["history"][0]["content"] = "something the user never asked"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(store.ResumeRefused):
        store.load(str(home), OLD_ID)


def _version_key(name):
    return tuple(int(x) for x in re.match(r"RELEASE-NOTES-([0-9.]+)\.md$", name).group(1).split("."))


def test_release_notes_from_1_9_0_link_the_licensing_page():
    notes = [p for p in ROOT.glob("RELEASE-NOTES-*.md")
             if re.match(r"RELEASE-NOTES-[0-9]+\.[0-9]+\.[0-9]+\.md$", p.name)]
    assert notes
    for path in notes:
        if _version_key(path.name) >= (1, 9, 0):
            assert "docs/LICENSING.md" in path.read_text(encoding="utf-8"), path.name


def test_the_versioning_page_names_the_schemas_the_code_writes():
    from harness.code_session import print_mode
    page = (ROOT / "docs" / "VERSIONING.md").read_text(encoding="utf-8")
    assert print_mode.SCHEMA in page
