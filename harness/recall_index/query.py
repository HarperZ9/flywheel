"""Recall: an FTS5 lookup, an IDF coverage gate, and a pointer read.

The coverage gate is what lets the index say "not found". A hit must
contain enough of the query's information, measured as the IDF-weighted
share of query terms present in the hit. A term the index has never seen
carries the maximum IDF, so a query about something absent cannot pass on
common words alone. MIN_COVERAGE was fixed before any evaluation run.
"""

import json
import math
import re

from harness.recall_index.gates import redact_contacts, text_gate
from harness.recall_index.records import split_line

MIN_COVERAGE = 0.6
SNIPPET = 320
_TERM = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_STOP = set("""a an the of to in on for and or is are was were be been it its this that
these those what which who whom where when why how does do did done with by from at as
about into over under than then there their our we you i me my your he she they them
not no yes can could should would will shall may might must has have had""".split())


def terms(query: str) -> list[str]:
    seen, out = set(), []
    for t in _TERM.findall(query.lower()):
        if t not in _STOP and t not in seen and len(t) > 1:
            seen.add(t)
            out.append(t)
    return out


def _idf(con, toks: list[str]) -> dict:
    n = con.execute("SELECT count(*) FROM fts").fetchone()[0] or 1
    out = {}
    for t in toks:
        row = con.execute("SELECT doc FROM fts_vocab WHERE term=?", (t,)).fetchone()
        df = row[0] if row else 0
        out[t] = math.log((n + 1) / (df + 0.5))
    return out


def _coverage(text: str, ents: str, idf: dict) -> float:
    have = set(_TERM.findall((text + " " + ents).lower()))
    total = sum(idf.values()) or 1.0
    return sum(w for t, w in idf.items() if t in have) / total


def _match_expr(toks: list[str]) -> str:
    return " OR ".join('"' + t.replace('"', "") + '"' for t in toks)


def recall(con, query: str, k: int = 5, scope: str | None = None, pool: int = 60) -> dict:
    toks = terms(query)
    if not toks:
        return {"query": query, "status": "not_found", "hits": [], "reason": "no terms"}
    idf = _idf(con, toks)
    sql = ("SELECT u.id, u.kind, u.session, u.source, u.ts, u.offset, u.text, f.ents, "
           "bm25(fts) AS r FROM fts f JOIN units u ON u.id=f.uid WHERE fts MATCH ? ")
    args = [_match_expr(toks)]
    if scope:
        sql += "AND u.scope=? "
        args.append(scope)
    rows = con.execute(sql + "ORDER BY r LIMIT ?", args + [pool]).fetchall()
    ranked = []
    for uid, kind, session, source, ts, off, text, ents, r in rows:
        cov = _coverage(text, ents or "", idf)
        bonus = 0.5 if kind == "author" else 0.0
        ranked.append((cov * 10 - r * 0.2 + bonus, cov, uid, kind, session, source, ts, off,
                       text))
    ranked.sort(key=lambda x: (-x[0], x[2]))
    hits = [{"id": uid, "kind": kind, "session": session, "ts": ts, "coverage": round(cov, 3),
             "pointer": f"{source}#{off}", "text": text[:SNIPPET]}
            for _, cov, uid, kind, session, source, ts, off, text in ranked
            if cov >= MIN_COVERAGE][:k]
    status = "found" if hits else "not_found"
    return {"query": query, "status": status, "terms": toks, "hits": hits}


def cards(con, entity: str, k: int = 10) -> list[dict]:
    rows = con.execute("SELECT c.id, c.session, c.ts, c.source, c.offset, c.quote FROM cards c "
                       "JOIN entities e ON e.unit=c.unit WHERE e.entity=? ORDER BY c.ts "
                       "LIMIT ?", (entity.lower(), k)).fetchall()
    return [{"id": i, "session": s, "ts": ts, "pointer": f"{src}#{off}", "quote": q}
            for i, s, ts, src, off, q in rows]


def read_pointer(pointer: str, limit: int = 2000) -> dict:
    """Re-read the source record behind a pointer, through the same gates."""
    source, _, off = pointer.rpartition("#")
    with open(source, "rb") as f:
        f.seek(int(off))
        line = f.readline()
    if source.endswith(".jsonl"):
        units, facts = split_line(line)
        if facts["stopped"]:
            return {"pointer": pointer, "skipped": "classifier_stop"}
        text = "\n\n".join(u["text"] for u in units if u["text"])
    else:
        text = line.decode("utf-8", "replace")
    reason = text_gate(text)
    if reason:
        return {"pointer": pointer, "skipped": reason}
    return {"pointer": pointer, "text": redact_contacts(text)[0][:limit]}


def as_text(result: dict) -> str:
    """Compact rendering for a model: one line per hit."""
    if result["status"] != "found":
        return f"not found: {result['query']}"
    lines = [f"{h['ts'][:10]} {h['kind']} {h['pointer']}\n  {h['text']}" for h in result["hits"]]
    return "\n".join(lines)


def dumps(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, indent=1)
