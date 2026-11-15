"""The writer-held process record (PLAN section 5).

Local and opt-in; salted commitments, never plain hashes; order and day by
default, with sizes and times only by opt-in and never in a default export; no
score of any kind; a private input method; a reveal a reader can check; and a
summary shaped like the C2PA data model that never calls itself a credential.

These tests guard the record's contract. They measure nothing about fairness
and nothing about who wrote any text.
"""
import ast
import hashlib
import json
import pathlib

import pytest

import articulate
from articulate import backends, editor
from articulate import process_events as ev
from articulate import process_export as px
from articulate import process_ledger as pl

PKG = pathlib.Path(articulate.__file__).parent
TEXT1 = "The rain fell for three days on the low field.\n"
TEXT2 = "The rain fell for three days. Water pooled behind the barn.\n"


@pytest.fixture
def doc(tmp_path):
    p = tmp_path / "essay.md"
    p.write_text(TEXT1, encoding="utf-8")
    return str(p)


def _log_text(doc):
    return pathlib.Path(pl.paths(doc)["log"]).read_text(encoding="utf-8")


def test_init_hides_the_log_from_git_unless_tracked(doc, tmp_path):
    pl.init(doc)
    assert (pathlib.Path(pl.folder(doc)) / ".gitignore").read_text() == "*\n"
    other = tmp_path / "b" / "notes.md"
    other.parent.mkdir()
    other.write_text("x\n", encoding="utf-8")
    pl.init(str(other), track=True)
    # A tracked log still keeps its private files away from git.
    ignore = (pathlib.Path(pl.folder(str(other))) / ".gitignore").read_text()
    assert ignore == pl.PRIVATE_IGNORE


def test_nothing_records_before_init(doc):
    with pytest.raises(FileNotFoundError):
        ev.record_draft(doc, TEXT1)


def test_a_default_draft_holds_a_commitment_sequence_and_day_only(doc):
    pl.init(doc)
    e = ev.record_draft(doc, TEXT1)
    assert set(e) == {"schema", "seq", "kind", "day", "commitment", "prev", "hash"}


def test_opt_in_fields_appear_only_when_opted_in(doc):
    pl.init(doc, opt_in=("words", "diff", "time"))
    ev.record_draft(doc, TEXT1)
    e = ev.record_draft(doc, TEXT2)
    assert {"words", "lines_added", "lines_removed", "time"} <= set(e)


def test_commitments_are_salted(doc):
    pl.init(doc)
    a = ev.record_draft(doc, TEXT1)
    ev.record_draft(doc, TEXT2)
    b = ev.record_draft(doc, TEXT1)
    assert a["commitment"] != b["commitment"]
    plain = "sha256:" + hashlib.sha256(TEXT1.encode()).hexdigest()
    assert plain not in _log_text(doc)


def test_an_unchanged_draft_is_not_recorded_twice(doc):
    pl.init(doc)
    ev.record_draft(doc, TEXT1)
    assert ev.record_draft(doc, TEXT1) is None


def test_no_entry_or_module_carries_a_score(doc):
    pl.init(doc, opt_in=("words", "diff", "time"))
    ev.record_draft(doc, TEXT1)
    ev.record_draft(doc, TEXT2)
    for line in _log_text(doc).splitlines():
        keys = set(json.loads(line))
        assert not {k for k in keys if any(w in k for w in ("score", "texture", "density"))}
    for name in ("process_ledger.py", "process_commit.py", "process_events.py",
                 "process_export.py", "disclose.py", "provenance.py", "cli_process.py"):
        tree = ast.parse((PKG / name).read_text(encoding="utf-8"))
        mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not mods & {"gate", "detector", "density", "scan", "cadence"}, name


def test_dictation_is_an_input_method_never_an_assist_verb(doc):
    pl.init(doc)
    with pytest.raises(ValueError):
        ev.record_assist(doc, "phone keyboard", "dictated", ["all"])
    ev.record_input_method(doc, "dictation")
    summ = px.summary(doc)
    assert all(e["kind"] != "input_method" for e in summ["entries"])
    assert "dictation" not in summ["disclosure"]
    assert "input_methods" not in summ
    shown = px.summary(doc, include=("input_method",))
    assert shown["input_methods"] == [{"method": "dictation", "sections": ["whole document"]}]
    assert "dictation" in shown["disclosure"]


def test_a_default_export_leaves_opt_in_fields_out(doc):
    pl.init(doc, opt_in=("words", "time"))
    ev.record_draft(doc, TEXT1)
    summ = px.summary(doc)
    drafts = [e for e in summ["entries"] if e["kind"] == "draft"]
    assert drafts and all("words" not in e and "time" not in e for e in drafts)
    wide = px.summary(doc, include=("words",))
    assert "words" in [e for e in wide["entries"] if e["kind"] == "draft"][0]


def test_a_reveal_opens_its_commitment_and_a_wrong_text_does_not(doc, tmp_path):
    pl.init(doc)
    e = ev.record_draft(doc, TEXT1)
    summ = px.summary(doc, reveal={e["seq"]: TEXT1})
    assert px.verify_summary(summ)["state"] == "intact"
    with pytest.raises(ValueError):
        px.summary(doc, reveal={e["seq"]: TEXT2})
    summ["reveals"][0]["text"] = TEXT2
    assert px.verify_summary(summ)["state"] == "broken"


def test_a_snapshot_can_be_revealed_without_the_file(doc):
    pl.init(doc, opt_in=("snapshot",))
    e = ev.record_draft(doc, TEXT1)
    summ = px.summary(doc, reveal={e["seq"]: None})
    assert summ["reveals"][0]["text"] == TEXT1


def test_the_salts_never_leave_through_an_export(doc):
    pl.init(doc)
    ev.record_draft(doc, TEXT1)
    salts = json.loads(pathlib.Path(pl.paths(doc)["salts"]).read_text())
    blob = json.dumps(px.summary(doc))
    assert all(v["salt"] not in blob for v in salts.values())


def test_a_tampered_log_is_broken_and_never_extended(doc):
    pl.init(doc)
    ev.record_draft(doc, TEXT1)
    log = pathlib.Path(pl.paths(doc)["log"])
    log.write_text(log.read_text().replace('"draft"', '"note"'), encoding="utf-8")
    assert px.verify_log(doc)["state"] == "broken"
    with pytest.raises(pl.LogBroken):
        ev.record_draft(doc, TEXT2)
    c = pl.restart(doc, "sync conflict")
    assert c["kind"] == "continuation" and c["continues"].startswith("sha256:")
    assert c["carried_assist"] == []
    assert ev.record_draft(doc, TEXT2)["seq"] == 2
    assert px.verify_log(doc)["state"] == "intact"


def test_verify_reports_no_gaps_intervals_or_clock_notes(doc):
    pl.init(doc)
    ev.record_draft(doc, TEXT1)
    assert set(px.verify_log(doc)) == {"state", "entries", "problems"}


def test_anchor_reads_git_refs_without_a_subprocess(doc, tmp_path):
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "refs" / "heads" / "main").write_text("a" * 40 + "\n")
    pl.init(doc)
    assert ev.record_anchor(doc)["git_commit"] == "a" * 40


def test_two_labelled_document_hashes(doc):
    pathlib.Path(doc).write_bytes(TEXT1.replace("\n", "\r\n").encode())
    pl.init(doc)
    summ = px.summary(doc)
    assert summ["file_sha256"] != summ["text_sha256"]
    assert summ["file_sha256"] == "sha256:" + hashlib.sha256(
        pathlib.Path(doc).read_bytes()).hexdigest()


def test_actions_follow_the_c2pa_shape(doc):
    pl.init(doc)
    ev.record_draft(doc, TEXT1)
    ev.record_assist(doc, "claude", "edited", ["section 2"], model="as declared")
    ev.record_assist(doc, "a translator", "translated", ["all"],
                     source_type="compositeWithTrainedAlgorithmicMedia", languages=("es", "en"))
    acts = px.summary(doc)["actions"]
    assert acts[0]["action"] == "c2pa.created"
    assert acts[0]["digitalSourceType"].endswith("/digitalCreation")
    assert acts[1]["digitalSourceType"].endswith("/compositeWithTrainedAlgorithmicMedia")
    assert acts[1]["changes"] == [{"type": "textual", "description": "section 2"}]
    assert acts[2]["action"] == "c2pa.translated"
    assert (acts[2]["sourceLanguage"], acts[2]["targetLanguage"]) == ("es", "en")
    assert "minorHumanEdits" not in json.dumps(acts)


def test_a_translation_needs_languages_and_the_writers_choice(doc):
    pl.init(doc)
    with pytest.raises(ValueError):
        ev.record_assist(doc, "t", "translated", ["all"])


def test_the_source_type_mapping_is_pinned():
    from articulate import provenance as pv
    assert pv.SOURCE_TYPE == {
        "written": "digitalCreation", "human-edit": "humanEdits",
        "deterministic-fix": "algorithmicallyEnhanced",
        "edited": "compositeWithTrainedAlgorithmicMedia",
        "generated": "trainedAlgorithmicMedia", "drafted": "trainedAlgorithmicMedia"}
    with pytest.raises(ValueError):
        pv.iptc_uri("minorHumanEdits")


def test_the_summary_never_calls_itself_a_credential(doc):
    pl.init(doc)
    summ = px.summary(doc)
    assert summ["title"] == "Articulate process summary"
    assert "does not show who composed the words" in summ["limits"]
    blob = json.dumps(summ).lower()
    assert "content credential" not in blob.replace("not a content credential", "")


def test_a_fix_pass_appends_an_assist_entry_when_a_log_exists(doc, monkeypatch, capsys):
    pl.init(doc)
    monkeypatch.setattr(backends, "complete", lambda *a, **k: (TEXT2, backends.BackendInfo("stub", "stub", [])))
    editor.fix(doc, doc + ".fixed.md", passes=1)
    entries, _ = pl.load(doc)
    assert entries[-1]["kind"] == "assist" and entries[-1]["verb"] == "edited"


def test_no_log_means_no_record(doc, monkeypatch, capsys):
    monkeypatch.setattr(backends, "complete", lambda *a, **k: (TEXT2, backends.BackendInfo("stub", "stub", [])))
    editor.fix(doc, doc + ".fixed.md", passes=1)
    assert not pathlib.Path(pl.paths(doc)["log"]).exists()


def test_main_cli_fix_with_output_records_delivered_edit(doc, monkeypatch, capsys):
    from articulate.cli import main
    pl.init(doc)
    monkeypatch.setattr(backends, "complete", lambda *a, **k: (TEXT2, backends.BackendInfo("stub", "stub", [])))
    output = doc + ".fixed.md"
    assert main(["fix", doc, "--out", output]) == 0
    assert pathlib.Path(output).read_text(encoding="utf-8").strip() == TEXT2.strip()
    entries, _ = pl.load(doc)
    assert entries[-1]["kind"] == "assist" and entries[-1]["verb"] == "edited"
    result = json.loads(capsys.readouterr().out)
    assert result["backend"] == result["receipt"]["backend"] == "stub"
    assert entries[-1]["model"] == "stub"
    assert "backend: stub" in entries[-1]["receipt"]


def test_main_cli_deterministic_edit_records_no_model_assistance(doc, monkeypatch, capsys):
    from articulate.cli import main
    pathlib.Path(doc).write_text("The rain  fell.\n", encoding="utf-8")
    pl.init(doc)
    monkeypatch.setattr(backends, "complete", lambda *a, **k: ("", backends.BackendInfo("none", None, [])))
    output = doc + ".fixed.md"
    assert main(["fix", doc, "--out", output, "--backend", "none"]) == 0
    assert pathlib.Path(output).read_text(encoding="utf-8") == "The rain fell.\n"
    entry = pl.load(doc)[0][-1]
    assert entry["verb"] == "deterministic-fix"
    assert "model" not in entry
    assert "backend: none" in entry["receipt"]


def test_main_cli_failed_output_does_not_record_an_edit(doc, monkeypatch, capsys):
    from articulate.cli import main
    pl.init(doc)
    monkeypatch.setattr(backends, "complete", lambda *a, **k: (TEXT2, backends.BackendInfo("stub", "stub", [])))
    output = str(pathlib.Path(doc).parent / "missing" / "fixed.md")
    assert main(["fix", doc, "--out", output]) == 2
    assert all(entry["kind"] != "assist" for entry in pl.load(doc)[0])


@pytest.mark.parametrize("backend,model,verb", [
    ("ollama", "local-model", "edited"),
    ("host", "caller-model", "edited"),
    ("none", None, "deterministic-fix"),
    (None, None, "edited"),
])
def test_editor_process_record_names_actual_backend_without_inventing_model(doc, backend, model, verb):
    pl.init(doc)
    ev.record_editor_pass(doc, "fix", backend=backend, model=model)
    entry = pl.load(doc)[0][-1]
    assert entry["verb"] == verb
    assert entry.get("model") == model
    assert "backend: " + (backend or "unknown") in entry["receipt"]
    assert "claude CLI" not in entry.get("model", "")
    summary = px.summary(doc)
    assert summary["chain"]["state"] == "intact"
    if backend == "none":
        assert summary["actions"][-1]["digitalSourceType"].endswith("/algorithmicallyEnhanced")


def test_the_cli_runs_the_whole_record(doc, capsys):
    from articulate.cli import main
    assert main(["process", "init", doc, "--opt-in", "words"]) == 0
    assert main(["process", "draft", doc]) == 0
    assert main(["process", "assist", doc, "--tool", "claude", "--verb", "edited",
                 "--sections", "intro"]) == 0
    assert main(["process", "input", doc, "--method", "dictation"]) == 0
    assert main(["process", "assist", doc, "--tool", "x", "--verb", "dictated"]) == 2
    assert main(["process", "export", doc, "--reveal", "2=" + doc]) == 0
    out = doc[:-3] + ".process-summary.json"
    assert main(["process", "verify", out]) == 0
    assert main(["process", "verify", doc]) == 0
    capsys.readouterr()
    assert main(["disclose", doc]) == 0
    text = capsys.readouterr().out
    assert "Edited with claude" in text and "dictation" not in text
    assert main(["disclose", doc, "--claim", "No AI was used."]) == 2
