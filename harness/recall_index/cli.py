"""Command line: build, query, cards, show, stats.

  python -m harness.recall_index build --db INDEX.sqlite --transcripts DIR [DIR ...]
         [--refs FILE ...] [--refs-list FILE] [--exclude SESSION ...]
  python -m harness.recall_index query --db INDEX.sqlite "question" [-k 5] [--scope S]
  python -m harness.recall_index cards --db INDEX.sqlite ENTITY
  python -m harness.recall_index show POINTER
  python -m harness.recall_index stats --db INDEX.sqlite
"""

import argparse
import glob
import json
import os
import sys
import time

from harness.recall_index import query as Q
from harness.recall_index.finalize import finalize
from harness.recall_index.ingest import ingest_transcript
from harness.recall_index.refs import ingest_reference
from harness.recall_index.store import open_db


def _transcripts(dirs: list[str], exclude: set[str]) -> list[str]:
    files = []
    for d in dirs:
        files += glob.glob(os.path.join(d, "*.jsonl")) if os.path.isdir(d) else [d]
    keep = [p for p in files if os.path.splitext(os.path.basename(p))[0] not in exclude]
    return sorted(keep, key=os.path.getmtime)


def _refs(args) -> list[str]:
    refs = list(args.refs or [])
    if args.refs_list:
        with open(args.refs_list, encoding="utf-8") as f:
            refs += [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    return [r for r in refs if os.path.isfile(r)]


def cmd_build(args) -> int:
    con, t0, totals = open_db(args.db), time.time(), {"read": 0, "units": 0, "skipped": 0}
    for path in _transcripts(args.transcripts or [], set(args.exclude or [])):
        try:
            r = ingest_transcript(con, path)
        except OSError as exc:
            print(f"recall-index: cannot read {path}: {exc}", file=sys.stderr)
            continue
        for key in totals:
            totals[key] += r[key]
    for path in _refs(args):
        r = ingest_reference(con, path)
        for key in totals:
            totals[key] += r[key]
    fin = finalize(con)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    out = dict(totals, **fin, seconds=round(time.time() - t0, 1),
               db_bytes=os.path.getsize(args.db))
    print(json.dumps(out, sort_keys=True))
    return 0


def cmd_query(args) -> int:
    con = open_db(args.db)
    res = Q.recall(con, args.question, k=args.k, scope=args.scope)
    print(Q.dumps(res) if args.json else Q.as_text(res))
    return 0 if res["status"] == "found" else 3


def cmd_cards(args) -> int:
    print(json.dumps(Q.cards(open_db(args.db), args.entity, args.k), indent=1,
                     ensure_ascii=False))
    return 0


def cmd_show(args) -> int:
    print(json.dumps(Q.read_pointer(args.pointer), indent=1, ensure_ascii=False))
    return 0


def cmd_stats(args) -> int:
    con = open_db(args.db)
    one = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    out = {"sources": one("SELECT count(*) FROM sources"),
           "bytes_read": one("SELECT coalesce(sum(done_offset),0) FROM sources"),
           "units_by_state": dict(con.execute("SELECT state, count(*) FROM units GROUP BY 1")),
           "units_by_kind": dict(con.execute("SELECT kind, count(*) FROM units "
                                             "WHERE state='live' GROUP BY 1")),
           "skipped_by_reason": dict(con.execute("SELECT reason, count(*) FROM skipped "
                                                 "GROUP BY 1")),
           "cards": one("SELECT count(*) FROM cards"),
           "db_bytes": os.path.getsize(args.db)}
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="recall-index", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--db", required=True)
    b.add_argument("--transcripts", nargs="*")
    b.add_argument("--refs", nargs="*")
    b.add_argument("--refs-list")
    b.add_argument("--exclude", nargs="*")
    q = sub.add_parser("query")
    q.add_argument("--db", required=True)
    q.add_argument("question")
    q.add_argument("-k", type=int, default=5)
    q.add_argument("--scope")
    q.add_argument("--json", action="store_true")
    c = sub.add_parser("cards")
    c.add_argument("--db", required=True)
    c.add_argument("entity")
    c.add_argument("-k", type=int, default=10)
    s = sub.add_parser("show")
    s.add_argument("pointer")
    st = sub.add_parser("stats")
    st.add_argument("--db", required=True)
    args = p.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    return {"build": cmd_build, "query": cmd_query, "cards": cmd_cards, "show": cmd_show,
            "stats": cmd_stats}[args.cmd](args)
