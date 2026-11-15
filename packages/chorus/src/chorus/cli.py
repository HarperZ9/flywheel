"""chorus CLI. Phase 1: `chorus run <corpus>` emits a discourse digest as JSON."""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys

_SHA256 = re.compile(r"[0-9a-f]{64}")

from chorus.item import normalize
from chorus.sentiment import score
from chorus.synthesize import synthesize
from chorus.receipt import verify as verify_digest


def _load_rows(path: str) -> list[dict]:
    if os.path.isdir(path):
        return _load_corpus_dir(path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_corpus_dir(path: str) -> list[dict]:
    """Load a gather corpus dir: catalog.jsonl rows, comment text from objects/<sha[:2]>/<sha[2:]>."""
    rows = []
    cat = os.path.join(path, "catalog.jsonl")
    with open(cat, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("kind") != "comment":
                continue
            sha = r.get("sha256", "")
            if _SHA256.fullmatch(sha):      # never build a read path from an unvalidated field
                obj = os.path.join(path, "objects", sha[:2], sha[2:])
                if os.path.exists(obj):
                    with open(obj, encoding="utf-8") as of:
                        r["text"] = of.read()
            rows.append(r)
    return rows


def _digest_to_dict(digest) -> dict:
    return dataclasses.asdict(digest)


def _cmd_run(args) -> int:
    if not os.path.exists(args.path):
        print(f"chorus: not found: {args.path}", file=sys.stderr)
        return 1
    try:
        rows = _load_rows(args.path)
    except (json.JSONDecodeError, OSError) as e:
        print(f"chorus: could not read corpus {args.path}: {e}", file=sys.stderr)
        return 1
    if not isinstance(rows, list):
        print("chorus: corpus JSON must be a list of rows", file=sys.stderr)
        return 1
    scored = score(normalize(rows))
    model_scores, model_ref = _run_model_pass(args, scored)
    digest = synthesize(scored, model_scores=model_scores, model_ref=model_ref)
    out = _digest_to_dict(digest)
    if args.verify:
        out["verified"] = verify_digest(digest, scored)
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def _run_model_pass(args, scored):
    """Optionally overlay a model sentiment read on the lexicon-uncertain items. The model command
    reads a JSON array of texts on stdin and emits ``[{compound, label}]``. Returns
    (model_scores, model_ref), or (None, None) when no --model was given."""
    cmd = getattr(args, "model", None)
    if not cmd:
        return None, None
    import shlex
    from chorus.model import SubprocessModel
    from chorus.sentiment import model_pass
    ref = getattr(args, "model_ref", None) or cmd
    model = SubprocessModel(shlex.split(cmd), ref=ref)
    overlays = model_pass(scored, model, model_ref=ref,
                          ambiguous_cut=getattr(args, "ambiguous_cut", 0.1))
    return overlays, ref


def _cmd_corpora(args) -> int:
    from chorus.corpora import list_corpora
    out = list_corpora(args.root)
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    return 1 if "error" in out else 0


def _cmd_watch(args) -> int:
    from chorus.daemon import Watchlist
    wl = Watchlist.load(args.watchlist) if os.path.exists(args.watchlist) else Watchlist([])
    if args.op == "add":
        if not args.corpus:
            print("chorus: watch add needs a corpus path", file=sys.stderr)
            return 1
        wl.add(args.corpus)
        wl.save(args.watchlist)
    elif args.op == "remove":
        wl.remove(args.corpus or "")
        wl.save(args.watchlist)
    print(json.dumps({"watchlist": args.watchlist, "sources": wl.sources}, indent=2))
    return 0


def _cmd_mcp(args) -> int:
    from chorus.mcp import serve
    return serve()


def _cmd_digests(args) -> int:
    from chorus.daemon import DigestStore
    store = DigestStore(args.store)
    print(json.dumps({"store": args.store, "digests": store.recent(args.limit)},
                     indent=2, ensure_ascii=False))
    return 0


def _cmd_decision(args) -> int:
    from chorus.decision import decision_from_paths
    public_projection_policy = None
    if args.public_policy:
        try:
            with open(args.public_policy, encoding="utf-8") as f:
                public_projection_policy = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"chorus: could not read public projection policy {args.public_policy}: {exc}", file=sys.stderr)
            return 1
        if not isinstance(public_projection_policy, dict):
            print("chorus: public projection policy JSON must be an object", file=sys.stderr)
            return 1
    out = decision_from_paths(
        args.current,
        args.reference,
        task=args.task,
        public_projection_policy=public_projection_policy,
    )
    body = out["public_projection"] if args.public else out
    print(json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if out.get("ok") else 2


def _cmd_daemon(args) -> int:
    import time
    from chorus.daemon import Watchlist, DigestStore, tick
    if not os.path.exists(args.watchlist):
        print(f"chorus: watchlist not found: {args.watchlist}", file=sys.stderr)
        return 1
    store = DigestStore(args.store)
    if args.once:
        out = tick(Watchlist.load(args.watchlist), store)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    # scheduled poll: re-read the watchlist each tick so edits take effect live.
    print(f"chorus daemon: polling {args.watchlist} every {args.interval}s -> {args.store}")
    try:
        while True:
            out = tick(Watchlist.load(args.watchlist), store)
            synthesized = [r for r in out["results"] if r.get("status") == "synthesized"]
            print(json.dumps({"ticked": out["ticked"], "synthesized": len(synthesized)}))
            time.sleep(max(1, args.interval))
    except KeyboardInterrupt:
        return 0


def main(argv: list[str] | None = None) -> int:
    # Emit UTF-8 regardless of the console/redirect codepage: a digest of real comments carries
    # emoji and non-Latin text, which would crash a cp1252 stdout on Windows. Guarded because a
    # capture stream (pytest capsys) has no reconfigure().
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="chorus")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="synthesize a discourse digest from a corpus")
    run.add_argument("path", help="a JSON file of gather-style rows, or a gather corpus directory")
    run.add_argument("--verify", action="store_true", help="re-derive and confirm the receipt")
    run.add_argument("--model", help="a command that reads texts (JSON) on stdin and emits "
                                     "[{compound,label}]; overlays a model read on uncertain items")
    run.add_argument("--model-ref", help="a name for the model, recorded in the receipt")
    run.add_argument("--ambiguous-cut", type=float, default=0.1,
                     help="|lexicon compound| below this is sent to the model (default 0.1)")
    run.set_defaults(func=_cmd_run)
    corpora = sub.add_parser("corpora", help="discover gather corpora under a root as discourse sources")
    corpora.add_argument("root", help="a directory to scan for gather corpora (dirs holding catalog.jsonl)")
    corpora.set_defaults(func=_cmd_corpora)
    watch = sub.add_parser("watch", help="manage the daemon watchlist")
    watch.add_argument("op", choices=["add", "list", "remove"])
    watch.add_argument("corpus", nargs="?", help="a corpus path (for add/remove)")
    watch.add_argument("--watchlist", default="watchlist.json")
    watch.set_defaults(func=_cmd_watch)
    daemon = sub.add_parser("daemon", help="poll the watchlist and synthesize on change")
    daemon.add_argument("--watchlist", default="watchlist.json")
    daemon.add_argument("--store", default=".chorus-run", help="where digests are stored")
    daemon.add_argument("--once", action="store_true", help="run a single tick and exit")
    daemon.add_argument("--interval", type=int, default=300, help="seconds between ticks")
    daemon.set_defaults(func=_cmd_daemon)
    digests = sub.add_parser("digests", help="list recent digests the daemon has stored")
    digests.add_argument("store", help="the daemon's digest store directory")
    digests.add_argument("--limit", type=int, default=20)
    digests.set_defaults(func=_cmd_digests)
    decision = sub.add_parser("decision", help="run a source-change review gate")
    decision.add_argument("current", help="current gather-style JSON row list or gather corpus directory")
    decision.add_argument("--reference", required=True,
                          help="reference gather-style JSON row list or gather corpus directory")
    decision.add_argument("--task", default="Compare current sources against the reference.",
                          help="human-readable source-review task")
    decision.add_argument("--public", action="store_true",
                          help="emit the safe public source-change projection")
    decision.add_argument("--public-policy",
                          help="operator-authored JSON policy for public ids, source names, refs, and URLs")
    decision.set_defaults(func=_cmd_decision)
    mcp = sub.add_parser("mcp", help="run the chorus MCP stdio server")
    mcp.set_defaults(func=_cmd_mcp)
    args = parser.parse_args(argv)
    return args.func(args)
