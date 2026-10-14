"""Falsifiers for `/undo` checkpoints and saved, resumable `flywheel code` sessions."""
import hashlib
import json

import pytest

from harness.code_session import cli, slash, store
from harness.code_session.backends import build_agent
from harness.code_session.checkpoints import CheckpointStore, target_paths
from harness.code_session.session import new_session
from tests.test_code_session import ScriptBackend, _bare_runner


def _session(tmp_path, replies, home=None):
    s = new_session(build_agent([ScriptBackend(replies)]), str(tmp_path), mode="auto",
                    runner=_bare_runner)
    if home is not None:
        s.home = str(home)
    return s


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_undo_restores_the_turn_byte_for_byte_and_deletes_created_files(tmp_path):
    (tmp_path / "keep.txt").write_bytes(b"line one\r\nline two\n")
    before = _sha(tmp_path / "keep.txt")
    s = _session(tmp_path, [
        'TOOL edit_file {"path": "keep.txt", "old": "one", "new": "ONE"}',
        'TOOL write_file {"path": "new/made.txt", "content": "fresh"}',
        "done",
    ])
    s.turn("change things")
    assert _sha(tmp_path / "keep.txt") != before and (tmp_path / "new" / "made.txt").exists()
    restored = s.undo()
    assert _sha(tmp_path / "keep.txt") == before
    assert not (tmp_path / "new" / "made.txt").exists()
    assert {r["path"].replace("\\", "/") for r in restored} == {"keep.txt", "new/made.txt"}
    assert any(e.kind == "undo" for e in s.ledger.entries) and s.ledger.verify()


def test_undo_takes_back_only_the_newest_changing_turn(tmp_path):
    s = _session(tmp_path, [
        'TOOL write_file {"path": "a.txt", "content": "1"}', "one",
        'TOOL write_file {"path": "a.txt", "content": "2"}', "two",
        "just talking",
    ])
    s.turn("first")
    s.turn("second")
    s.turn("third, no files")
    s.undo()
    assert (tmp_path / "a.txt").read_text() == "1"
    s.undo()
    assert not (tmp_path / "a.txt").exists()
    assert s.undo() is None


def test_the_model_is_told_about_an_undo_on_the_next_turn(tmp_path):
    backend = ScriptBackend(['TOOL write_file {"path": "a.txt", "content": "1"}', "ok", "noted"])
    s = new_session(build_agent([backend]), str(tmp_path), mode="auto", runner=_bare_runner)
    s.turn("write")
    s.undo()
    s.turn("go on")
    assert "undid your previous file changes" in backend.seen[-1][-1]["content"]


def test_patch_targets_are_found_and_confined(tmp_path):
    patch = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n--- a/y\n+++ b/../escape\n"
    paths = target_paths(str(tmp_path), "apply_patch", {"patch": patch})
    assert [p.replace("\\", "/").rsplit("/", 1)[-1] for p in paths] == ["x.py"]


def test_denied_writes_take_no_snapshot(tmp_path):
    s = new_session(build_agent([ScriptBackend(
        ['TOOL write_file {"path": "a.txt", "content": "1"}', "ok"])]),
        str(tmp_path), mode="ask", approver=lambda n, a: "no", runner=_bare_runner)
    s.turn("write")
    assert s.checkpoints.undoable() == 0


def test_save_then_resume_restores_conversation_and_ledger(tmp_path):
    home = tmp_path / "home"
    work = tmp_path / "work"
    work.mkdir()
    s = _session(work, ["first answer"], home=home)
    s.turn("remember the word heron")
    rows = store.list_sessions(str(home), root=str(work))
    assert len(rows) == 1 and rows[0]["turns"] == 1
    args = cli.parse_args(["--root", str(work), "--continue", "--no-instructions"])
    monkey_home = str(home)
    resumed_backend = ScriptBackend(["second answer"])
    cli_home = cli._home
    try:
        cli._home = lambda: monkey_home
        r = cli.build_session(args, backends=[resumed_backend], runner=_bare_runner)
    finally:
        cli._home = cli_home
    assert r.session_id == rows[0]["id"] and r.turns == 1
    r.turn("what was the word?")
    sent = resumed_backend.seen[-1]
    assert any("heron" in m["content"] for m in sent)
    assert r.ledger.verify()


@pytest.mark.parametrize("tamper", ["ledger", "history", "head"])
def test_a_tampered_session_is_refused(tmp_path, tamper):
    home = tmp_path / "home"
    s = _session(tmp_path, ["a"], home=home)
    s.turn("hello")
    folder = store.sessions_dir(str(home)) / s.session_id
    if tamper == "ledger":
        lines = (folder / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
        row = json.loads(lines[1])
        row["content"] = row["content"] + " (edited)"
        lines[1] = json.dumps(row)
        (folder / "ledger.jsonl").write_text("\n".join(lines), encoding="utf-8")
    else:
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        if tamper == "history":
            meta["history"][0]["content"] = "something the user never said"
        else:
            meta["ledger_head"] = "0" * 64
        (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(store.ResumeRefused):
        store.load(str(home), s.session_id)


def test_resume_rejects_a_path_shaped_id(tmp_path):
    with pytest.raises(store.ResumeRefused):
        store.load(str(tmp_path), "../../etc")


def test_continue_with_nothing_saved_is_a_clear_refusal(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_home", lambda: str(tmp_path / "home"))
    monkeypatch.setattr(cli, "ladder", lambda **kw: [ScriptBackend([])])
    assert cli.main(["--continue", "--root", str(tmp_path), "-p", "x"]) == 2
    assert "no saved session" in capsys.readouterr().err


def test_undo_slash_command(tmp_path):
    s = _session(tmp_path, ['TOOL write_file {"path": "a.txt", "content": "1"}', "ok"])
    assert "nothing to undo" in slash.dispatch(s, "/undo")
    s.turn("write")
    assert slash.dispatch(s, "/undo").startswith("restored: a.txt")


def test_checkpoint_store_handles_an_unwritten_turn():
    store_ = CheckpointStore(".")
    store_.begin_turn()
    assert store_.undo() is None
