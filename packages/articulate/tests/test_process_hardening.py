"""Review findings on the process record, one test per failure mode.

Each test fails on the implementation the review found: withheld fields that a
default export leaked through entry hashes, a `continue` that dropped recorded
assistance, a `disclose` and a `verify` that ignored the chain, a git anchor
read from the wrong repository, snapshots and salts that collided, and a
`--track` log whose private files git could stage.
"""
import json
import pathlib
import shutil
import subprocess

import pytest

from articulate import backends, editor
from articulate import process_commit as pc
from articulate import process_events as ev
from articulate import process_export as px
from articulate import process_ledger as pl
from articulate.cli import main

TEXT1 = "The rain fell for three days on the low field.\n"
TEXT2 = "The rain fell for three days. Water pooled behind the barn.\n"


@pytest.fixture
def doc(tmp_path):
    p = tmp_path / "essay.md"
    p.write_text(TEXT1, encoding="utf-8")
    return str(p)


def _lines(doc):
    return pathlib.Path(pl.paths(doc)["log"]).read_text(encoding="utf-8").splitlines(True)


def _write_lines(doc, lines):
    pathlib.Path(pl.paths(doc)["log"]).write_text("".join(lines), encoding="utf-8")


def _fixed_salt(monkeypatch):
    monkeypatch.setattr(pc, "new_salt", lambda: "11" * 32)


# --- 1. a default export carries nothing computed from a withheld field ----- #

def _log_with(tmp_path, name, hhmm, citation, reviewer, method):
    from datetime import datetime, timezone
    d = tmp_path / name
    d.mkdir()
    doc = str(d / "essay.md")
    pathlib.Path(doc).write_text(TEXT1, encoding="utf-8")
    now = datetime(2026, 9, 26, int(hhmm[:2]), int(hhmm[3:]), tzinfo=timezone.utc)
    pl.init(doc, opt_in=("words", "time"), now=now)
    ev.record_draft(doc, TEXT1, now=now)
    ev.record_source(doc, citation, now=now)
    ev.record_review(doc, "tutor", "draft 2", "revise", name=reviewer, now=now)
    if method:
        ev.record_input_method(doc, method, now=now)
    return doc


def test_a_default_export_is_the_same_whatever_the_withheld_fields_hold(tmp_path, monkeypatch):
    # If two logs that differ only in withheld fields export the same bytes, no
    # dictionary or brute-force test can recover those fields from the export.
    _fixed_salt(monkeypatch)
    a = px.summary(_log_with(tmp_path, "a", "14:37", "Smith 2020", "Dana", None))
    b = px.summary(_log_with(tmp_path, "b", "09:05", "Jones 2019", "Lee", "dictation"))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert all("hash" not in e and "prev" not in e for e in a["entries"])
    assert set(a["chain"]) == {"state", "problems"}


def test_an_input_method_leaves_no_gap_in_the_sequence(doc):
    pl.init(doc)
    ev.record_input_method(doc, "dictation")
    ev.record_draft(doc, TEXT1)
    seqs = [e["seq"] for e in px.summary(doc)["entries"]]
    assert seqs == list(range(1, len(seqs) + 1))
    assert "dictation" not in "".join(_lines(doc))


# --- 2 and 3. continue and disclose respect the chain ----------------------- #

def test_continue_is_refused_on_an_intact_log(doc):
    pl.init(doc)
    ev.record_assist(doc, "claude", "generated", ["intro"])
    with pytest.raises(ValueError):
        pl.restart(doc, "tidy")
    assert main(["process", "continue", doc, "--reason", "tidy"]) == 2
    assert main(["disclose", doc, "--claim", "No AI was used."]) == 2


def test_a_continuation_carries_recorded_assistance_forward(doc, capsys):
    pl.init(doc)
    ev.record_assist(doc, "claude", "generated", ["intro"])
    ev.record_draft(doc, TEXT1)
    lines = _lines(doc)
    _write_lines(doc, [lines[0], lines[2], lines[1]])     # reorder the last two
    assert px.verify_log(doc)["state"] == "broken"
    c = pl.restart(doc, "sync conflict")
    assert [a["tool"] for a in c["carried_assist"]] == ["claude"]
    capsys.readouterr()
    assert main(["disclose", doc]) == 0
    assert "Generated with claude: intro." in capsys.readouterr().out
    assert main(["disclose", doc, "--claim", "No AI was used."]) == 2
    acts = px.summary(doc)["actions"]
    assert any(a.get("softwareAgent", {}).get("name") == "claude" for a in acts)


def test_disclose_refuses_a_broken_log_and_a_missing_one(doc, tmp_path, capsys):
    pl.init(doc)
    ev.record_draft(doc, TEXT1)
    ev.record_assist(doc, "claude", "generated", ["intro"])
    ev.record_draft(doc, TEXT2)
    lines = _lines(doc)
    _write_lines(doc, lines[:2] + lines[3:])              # delete the middle assist
    assert main(["disclose", doc, "--claim", "No AI was used."]) == 2
    assert main(["disclose", doc]) == 2
    other = tmp_path / "never.md"
    other.write_text("x\n", encoding="utf-8")
    assert main(["disclose", str(other)]) == 2
    assert "no process log" in capsys.readouterr().err


def test_reordering_or_removing_a_middle_entry_breaks_the_chain(doc):
    pl.init(doc)
    for t in (TEXT1, TEXT2, TEXT1 + "x"):
        ev.record_draft(doc, t)
    lines = _lines(doc)
    for broken in (lines[:1] + lines[2:], [lines[0], lines[2], lines[1], lines[3]]):
        _write_lines(doc, broken)
        assert px.verify_log(doc)["state"] == "broken"
    # Tail truncation leaves a valid shorter chain; the docstring says so.
    _write_lines(doc, lines[:2])
    assert px.verify_log(doc)["state"] == "intact"
    assert "cannot detect that" in pl.__doc__


# --- 4. verify never reports intact with nothing to check ------------------- #

def test_verify_reports_a_missing_log(doc, tmp_path, capsys):
    assert px.verify_log(doc)["state"] == "missing"
    # No log is no record: exit 3, apart from a broken log's 1 (C4a).
    assert main(["process", "verify", doc]) == 3
    assert main(["process", "verify", str(tmp_path / "no-such-file.md")]) == 3


def test_verify_reads_a_summary_by_its_schema_and_its_chain(doc, tmp_path):
    pl.init(doc)
    e = ev.record_draft(doc, TEXT1)
    out = tmp_path / "x.json"
    assert main(["process", "export", doc, "--reveal", str(e["seq"]), "--out", str(out)]) != 0
    assert main(["process", "export", doc, "--out", str(out)]) == 0
    assert main(["process", "verify", str(out)]) == 0
    summ = json.loads(out.read_text(encoding="utf-8"))
    summ["chain"]["state"] = "broken"
    out.write_text(json.dumps(summ), encoding="utf-8")
    assert main(["process", "verify", str(out)]) == 1


@pytest.mark.parametrize("bad", [
    {"schema": px.SCHEMA, "chain": {"state": "intact"}, "entries": ["x"]},
    {"schema": px.SCHEMA, "chain": "intact", "reveals": [{"seq": 1}]},
    {"schema": px.SCHEMA, "chain": {"state": "intact"}, "reveals": 3},
])
def test_verify_treats_malformed_summary_json_as_broken(bad):
    assert px.verify_summary(bad)["state"] == "broken"


# --- 6. the git anchor reads the repository the document sits in ------------ #

def _repo(root, branch, sha, packed=False):
    git = root / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text(f"ref: refs/heads/{branch}\n")
    if packed:
        (git / "packed-refs").write_text(f"# pack-refs\n{sha} refs/heads/{branch}\n")
    else:
        (git / "refs" / "heads" / branch).write_text(sha + "\n")
    return git


def test_the_anchor_follows_a_worktree_git_file(tmp_path):
    main_repo = tmp_path / "main"
    git = _repo(main_repo, "main", "a" * 40)
    (git / "refs" / "heads" / "feat").write_text("b" * 40 + "\n")
    wt_git = git / "worktrees" / "wt"
    wt_git.mkdir(parents=True)
    (wt_git / "HEAD").write_text("ref: refs/heads/feat\n")
    (wt_git / "commondir").write_text("../..\n")
    wt = tmp_path / "wt"
    (wt / "docs").mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {wt_git}\n")
    assert ev.git_head(str(wt / "docs")) == "b" * 40


def test_the_anchor_reads_packed_refs(tmp_path):
    _repo(tmp_path, "main", "c" * 40, packed=True)
    assert ev.git_head(str(tmp_path)) == "c" * 40


# --- 7 and 8. snapshots and salts stay per document and per commitment ------ #

def test_two_documents_keep_their_own_snapshots(tmp_path):
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    for p, text in ((a, TEXT1), (b, TEXT2)):
        p.write_text(text, encoding="utf-8")
        pl.init(str(p), opt_in=("snapshot",))
        ev.record_draft(str(p), text)
    summ = px.summary(str(a), reveal={2: None})
    assert summ["reveals"][0]["text"] == TEXT1


def test_a_restart_keeps_old_salts_and_records_the_current_text(doc):
    pl.init(doc)
    old = ev.record_draft(doc, TEXT1)
    lines = _lines(doc)
    _write_lines(doc, [lines[1], lines[0]])
    pl.restart(doc, "sync conflict")
    new = ev.record_draft(doc, TEXT1)                    # same text as the old draft
    assert new is not None and new["seq"] == 2
    salts = pc.load_salts(pl.paths(doc)["salts"])
    assert {old["commitment"], new["commitment"]} <= set(salts)
    assert px.summary(doc, reveal={2: TEXT1})["reveals"][0]["seq"] == 2


def test_a_refused_draft_leaves_the_diff_baseline_alone(doc):
    pl.init(doc, opt_in=("diff",))
    ev.record_draft(doc, TEXT1)
    lines = _lines(doc)
    _write_lines(doc, [lines[1], lines[0]])
    with pytest.raises(pl.LogBroken):
        ev.record_draft(doc, TEXT2)
    assert pathlib.Path(pl.paths(doc)["last"]).read_text(encoding="utf-8") == TEXT1


@pytest.mark.skipif(not shutil.which("git"), reason="git is not installed")
def test_a_tracked_log_never_stages_its_private_files(tmp_path):
    doc = tmp_path / "essay.md"
    doc.write_text(TEXT1, encoding="utf-8")
    run = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True,  # noqa: E731
                                    capture_output=True, text=True)
    run("init", "-q")
    pl.init(str(doc), track=True, opt_in=("diff", "snapshot"))
    ev.record_draft(str(doc), TEXT1)
    ev.record_draft(str(doc), TEXT2)
    ev.record_input_method(str(doc), "dictation")
    run("add", "-A")
    staged = run("ls-files").stdout.splitlines()
    assert any(s.endswith("essay.md.jsonl") for s in staged)
    assert not [s for s in staged if s.endswith((".salts.json", ".last.txt", ".private.jsonl"))
                or ".objects/" in s]


# --- 10. an editor pass that wrote a rewrite is logged even when a later pass fails #

def test_fix_logs_the_rewrite_when_pass_two_fails(doc, monkeypatch, capsys):
    pl.init(doc)
    calls = []
    # The guard refuses a rewrite that adds a device, so the original already
    # carries the devices that keep the gate blocked after pass one.
    pathlib.Path(doc).write_text(
        "As mentioned above, the rain fell for three days in order to flood the field.\n",
        encoding="utf-8")

    accepted = "As mentioned above, the rain fell in order to flood the field.\n"

    def fake(instr, text, timeout=600, **kwargs):
        calls.append(1)
        if len(calls) > 1:
            return "", backends.BackendInfo("none", None, [{"backend": "stub", "reason": "backend down"}])
        return accepted, backends.BackendInfo("stub", "stub", [])

    monkeypatch.setattr(backends, "complete", fake)
    assert editor.fix(doc, doc + ".fixed.md", passes=2) == 0
    assert len(calls) == 2
    assert pathlib.Path(doc + ".fixed.md").read_text(encoding="utf-8") == accepted
    printed = capsys.readouterr().out
    assert "backend down" in printed and "kept the best checked version" in printed
    kinds = [e["kind"] for e in pl.load(doc)[0]]
    assert kinds[-1] == "assist"


def test_polish_logs_an_accepted_pass(doc, monkeypatch):
    pl.init(doc)
    judged = iter([{k: 3 for k in editor.QUALITIES}] + [{k: 5 for k in editor.QUALITIES}] * 5)
    rc = editor.polish(doc, doc + ".polished.md", 1, 4,
                       rewrite_fn=lambda *a, **k: TEXT2,
                       judge_fn=lambda *a, **k: next(judged))
    assert rc == 0
    assert [e["kind"] for e in pl.load(doc)[0]][-1] == "assist"


# --- crash paths ----------------------------------------------------------- #

def test_an_assist_entry_missing_its_verb_never_crashes_the_export(doc, capsys):
    pl.init(doc)
    pl.append(doc, "assist", {"tool": "x"})
    summ = px.summary(doc)
    assert summ["chain"]["state"] == "broken"
    assert any("malformed" in p for p in summ["chain"]["problems"])
    assert main(["disclose", doc]) == 2
