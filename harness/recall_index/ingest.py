"""Stream new bytes of a transcript into the index: one pass, bounded memory.

A source is identified by its path and the sha256 of its first 64 KiB.
When the head still matches, reading starts at the last complete line that
was processed; when it differs, the file was rewritten and is re-indexed.
Only complete lines are consumed, so a file still being written is safe.
"""

import hashlib
import os

from harness.recall_index import features as F
from harness.recall_index import store
from harness.recall_index.gates import redact_contacts, text_gate
from harness.recall_index.records import split_line
from harness.recall_index.simhash import line_hash

HEAD = 64 * 1024
CLIP = {"summary": 6000, "author": 4000, "assistant": 1500, "relay": 1200, "tool_call": 300,
        "reference": 1500}


def head_sha(path: str, length: int = HEAD) -> str:
    """Identity of a source: the hash of its first bytes, up to HEAD.

    The length is capped by what was read before, so appending to a short
    file does not look like a rewrite."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read(min(HEAD, length))).hexdigest()


def _paragraphs(kind: str, text: str) -> list[tuple[int, str]]:
    """Assistant prose is split into paragraphs so each is scored on its own."""
    if kind not in ("assistant", "summary"):
        return [(0, text)]
    out, pos = [], 0
    for para in text.split("\n\n"):
        if para.strip():
            out.append((pos, para.strip()))
        pos += len(para) + 2
    return out


def _count_lines(con, text: str, session: str, uid: str) -> None:
    for raw in text.splitlines():
        if len(raw.strip()) < 24:
            continue
        h = line_hash(raw)
        row = con.execute("SELECT sessions, last_session FROM lines WHERE h=?", (h,)).fetchone()
        if row is None:
            con.execute("INSERT INTO lines VALUES(?,?,?,?)", (h, 1, uid, session))
        elif row[1] != session:
            con.execute("UPDATE lines SET sessions=sessions+1, last_session=? WHERE h=?",
                        (session, h))


def emit(con, ctx: dict, offset: int, ts: str, unit: dict, seq: int) -> int:
    """Gate, score and stage one unit. Returns 1 if stored, 0 otherwise."""
    kind, text, meta = unit["kind"], unit["text"], unit["meta"]
    if kind == "tool_result":
        if meta.get("tuid"):
            con.execute("UPDATE units SET meta=json_set(meta,'$.outcome',?) WHERE id="
                        "(SELECT unit FROM calls WHERE tuid=?)",
                        ("error" if meta.get("error") else "ok", meta["tuid"]))
        return 0
    reason = text_gate(text)
    if reason:
        store.put_skip(con, ctx["source"], offset, kind, reason)
        ctx["skipped"] += 1
        return 0
    text, _ = redact_contacts(text)
    feats = F.features(kind, text)
    s = F.score(kind, feats)
    if not F.keep(kind, s):
        return 0
    text = text[: CLIP.get(kind, 1200)]
    uid = store.unit_id(ctx["source"], offset, kind, text, seq)
    store.put_unit(con, {"id": uid, "scope": ctx["scope"], "session": ctx["session"],
                         "source": ctx["source"], "ts": ts, "offset": offset, "kind": kind,
                         "score": s, "text": text, "meta": meta, "feats": feats})
    if kind == "tool_call" and meta.get("tuid"):
        con.execute("INSERT OR REPLACE INTO calls VALUES(?,?)", (meta["tuid"], uid))
    _count_lines(con, text, ctx["session"], uid)
    return 1


def _handle_line(con, ctx: dict, line: bytes, offset: int) -> None:
    units, facts = split_line(line)
    if facts["stopped"]:
        store.put_skip(con, ctx["source"], offset, "assistant", "classifier_stop")
        ctx["skipped"] += 1
        return
    if facts["sidechain"]:
        return
    seq = 0
    for unit in units:
        for _, para in _paragraphs(unit["kind"], unit["text"]):
            ctx["units"] += emit(con, ctx, offset, facts["ts"], dict(unit, text=para), seq)
            seq += 1


def ingest_transcript(con, path: str, scope: str = "session") -> dict:
    """Index the unread tail of one JSONL transcript."""
    path = os.path.abspath(path)
    size = os.path.getsize(path)
    state = store.source_state(con, path)
    start = 0
    if state and state[0] == head_sha(path, state[1]):
        start = state[1]
    elif state:
        store.drop_source(con, path)
    session = os.path.splitext(os.path.basename(path))[0]
    ctx = {"source": path, "scope": scope, "session": session, "units": 0, "skipped": 0}
    done = start
    with open(path, "rb") as f:
        f.seek(start)
        for line in f:
            if not line.endswith(b"\n"):
                break
            _handle_line(con, ctx, line, done)
            done += len(line)
    store.save_source(con, path, scope, session, head_sha(path, done), done, size, ctx["units"],
                      ctx["skipped"])
    con.commit()
    return {"source": path, "read": done - start, "units": ctx["units"],
            "skipped": ctx["skipped"]}
