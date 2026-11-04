"""Recall index: a deterministic transcript distiller and its recall path.

Every test builds a synthetic transcript, so nothing here reads a real
session. The assertions cover the claims the module makes: typed split,
noise removal, gates, incremental reads, near-duplicate and boilerplate
collapse, recall with a not-found answer, cards, and pointer reads.
"""

import json

from harness.recall_index import query as Q
from harness.recall_index.finalize import finalize
from harness.recall_index.ingest import ingest_transcript
from harness.recall_index.refs import ingest_reference
from harness.recall_index.store import open_db


def _rec(kind, content, **extra):
    base = {"type": kind, "uuid": extra.pop("uuid", "u"), "timestamp": "2026-11-02T10:00:00Z",
            "isSidechain": False, "message": {"role": kind, "content": content}}
    base.update(extra)
    return json.dumps(base) + "\n"


def _tool_use(tid, name, inp):
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def _write(path, lines):
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.writelines(lines)


def _session(tmp_path, name="s1", extra=()):
    p = tmp_path / f"{name}.jsonl"
    _write(p, [
        _rec("user", 'We want this: "always keep the qdb engine in build-universe, never a new repo"'),
        json.dumps({"type": "attachment", "attachment": {"type": "hook_additional_context",
                    "content": ["Canon shared context zebrafish"]}}) + "\n",
        _rec("assistant", [{"type": "text", "text": "Decision: the verdict is PASS for F219, "
                            "tagged ideas survived at 0.90 and untagged at 0.02."},
                           _tool_use("t1", "Bash", {"command": "pytest tests/test_x.py -q"})]),
        _rec("user", [{"type": "tool_result", "tool_use_id": "t1", "is_error": True,
                       "content": "x" * 5000 + " traceback secretsauce"}]),
        _rec("user", "<task-notification><status>completed</status><summary>Agent finished "
                     "the qdb audit</summary><output-file>C:/tmp/a.out</output-file>"
                     "</task-notification>"),
        _rec("user", "hello <system-reminder>injected walrus text</system-reminder> there"),
    ] + list(extra))
    return p


def _build(tmp_path, *paths):
    con = open_db(str(tmp_path / "idx.sqlite"))
    for p in paths:
        ingest_transcript(con, str(p))
    finalize(con)
    return con


def _texts(con):
    return " ".join(r[0] for r in con.execute("SELECT text FROM units"))


def test_split_keeps_signal_and_drops_noise(tmp_path):
    con = _build(tmp_path, _session(tmp_path))
    kinds = dict(con.execute("SELECT kind, count(*) FROM units GROUP BY 1"))
    assert kinds.get("author") and kinds.get("assistant") and kinds.get("tool_call")
    assert kinds.get("relay"), "task notification summary should be a relay unit"
    text = _texts(con)
    assert "zebrafish" not in text, "hook context leaked into the index"
    assert "walrus" not in text, "system reminder leaked into the index"
    assert "secretsauce" not in text and "xxxxx" not in text, "tool-result body was stored"
    assert "C:/tmp/a.out" not in text, "notification wrapper was stored"


def test_tool_outcome_joins_its_call(tmp_path):
    con = _build(tmp_path, _session(tmp_path))
    meta = json.loads(con.execute("SELECT meta FROM units WHERE kind='tool_call'").fetchone()[0])
    assert meta["command"].startswith("pytest") and meta["outcome"] == "error"


def test_classifier_stop_is_never_stored(tmp_path):
    stopped = _rec("assistant", [{"type": "text", "text": "partial reply about forbidden kelp"}],
                   isApiErrorMessage=True)
    con = _build(tmp_path, _session(tmp_path, extra=[stopped]))
    assert "kelp" not in _texts(con)
    reasons = [r[0] for r in con.execute("SELECT reason FROM skipped")]
    assert "classifier_stop" in reasons


def test_gates_skip_secrets_and_personal_and_redact_contacts(tmp_path):
    extra = [_rec("user", "the key is sk-" + "A" * 30),
             _rec("user", "my father said something private about the orchard"),
             _rec("user", "mail me at someone@example.net about the qdb build")]
    con = _build(tmp_path, _session(tmp_path, extra=extra))
    text = _texts(con)
    assert "AAAAAAAA" not in text and "orchard" not in text
    assert "someone@example.net" not in text and "[contact]" in text
    reasons = sorted(r[0] for r in con.execute("SELECT reason FROM skipped"))
    assert reasons == ["personal", "secret"]


def test_incremental_reads_only_appended_bytes(tmp_path):
    p = _session(tmp_path)
    con = open_db(str(tmp_path / "idx.sqlite"))
    first = ingest_transcript(con, str(p))
    again = ingest_transcript(con, str(p))
    assert first["read"] == p.stat().st_size and again["read"] == 0
    tail = _rec("user", "standing rule: never run memo in a subagent", uuid="u9")
    _write(p, [tail])
    third = ingest_transcript(con, str(p))
    assert third["read"] == len(tail.encode()) and third["units"] == 1


def test_partial_last_line_waits_for_its_newline(tmp_path):
    p = _session(tmp_path)
    with open(p, "a", encoding="utf-8") as f:
        f.write('{"type": "user", "message": {"content": "half')
    con = open_db(str(tmp_path / "idx.sqlite"))
    r = ingest_transcript(con, str(p))
    assert r["read"] < p.stat().st_size


def test_rewritten_head_is_reindexed(tmp_path):
    p = _session(tmp_path)
    con = open_db(str(tmp_path / "idx.sqlite"))
    ingest_transcript(con, str(p))
    p.write_text(_rec("user", "a brand new first line about lattice cranes"), encoding="utf-8")
    ingest_transcript(con, str(p))
    finalize(con)
    text = _texts(con)
    assert "lattice cranes" in text and "build-universe" not in text


def test_ids_are_deterministic(tmp_path):
    p = _session(tmp_path)
    a = _build(tmp_path, p)
    ids_a = sorted(r[0] for r in a.execute("SELECT id FROM units"))
    (tmp_path / "b").mkdir()
    b = open_db(str(tmp_path / "b" / "idx.sqlite"))
    ingest_transcript(b, str(p))
    finalize(b)
    assert ids_a == sorted(r[0] for r in b.execute("SELECT id FROM units"))


def test_near_duplicates_collapse(tmp_path):
    long = ("The recall index decision: we keep author rulings verbatim, collapse repeats, "
            "and store pointers so a reader can go back to the source line. ") * 3
    p1 = tmp_path / "a.jsonl"
    _write(p1, [_rec("user", long, uuid="1"), _rec("user", long + " Also yes.", uuid="2")])
    con = _build(tmp_path, p1)
    states = dict(con.execute("SELECT state, count(*) FROM units GROUP BY 1"))
    assert states.get("dup") == 1 and states.get("live") == 1


def test_boilerplate_lines_kept_only_where_first_seen(tmp_path):
    line = "Workspace rules: no renames without a checklist and branch before committing."
    paths = []
    for i in range(6):
        p = tmp_path / f"b{i}.jsonl"
        _write(p, [_rec("user", f"{line}\nunique note number {i} about otter{i}", uuid=str(i))])
        paths.append(p)
    con = _build(tmp_path, *paths)
    with_line = con.execute("SELECT count(*) FROM units WHERE text LIKE '%Workspace rules%'")
    assert with_line.fetchone()[0] < 6
    assert "otter5" in _texts(con)


def test_recall_found_and_not_found(tmp_path):
    con = _build(tmp_path, _session(tmp_path))
    hit = Q.recall(con, "qdb engine build-universe")
    assert hit["status"] == "found" and "build-universe" in hit["hits"][0]["text"]
    miss = Q.recall(con, "Kubernetes helm chart rollout")
    assert miss["status"] == "not_found" and miss["hits"] == []


def test_cards_hold_verbatim_rulings_with_pointers(tmp_path):
    con = _build(tmp_path, _session(tmp_path))
    quotes = [r[0] for r in con.execute("SELECT quote FROM cards")]
    assert any("never a new repo" in q for q in quotes)
    pointer = Q.recall(con, "qdb engine build-universe")["hits"][0]["pointer"]
    back = Q.read_pointer(pointer)
    assert "build-universe" in back["text"]


def test_reference_paragraphs_keep_heading_and_scope(tmp_path):
    ref = tmp_path / "INTAKE.md"
    ref.write_text("# Lenses\n\nA prism splits light; Newton 1672 measured the spectrum "
                   "and the verdict held across 3 of 3 trials.\n\nshort\n", encoding="utf-8")
    con = open_db(str(tmp_path / "idx.sqlite"))
    ingest_reference(con, str(ref))
    finalize(con)
    res = Q.recall(con, "prism spectrum Newton", scope="reference")
    assert res["status"] == "found"
    meta = json.loads(con.execute("SELECT meta FROM units WHERE scope='reference'").fetchone()[0])
    assert meta == {"heading": "Lenses", "use": "internal"}
