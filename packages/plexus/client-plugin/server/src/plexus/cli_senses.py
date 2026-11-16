"""cli_senses.py: the kinds, senses, fanout and fanout-verify commands."""
from __future__ import annotations

import json


def add_parsers(sub) -> None:
    kp = sub.add_parser("kinds", help="input kinds of a path, URL or literal")
    kp.add_argument("item")
    sp = sub.add_parser("senses", help="list the sense manifests, or check them")
    sp.add_argument("--check", action="store_true", help="exit 1 if the manifests differ from SENSES.tsv")
    sp.add_argument("--kind", action="append", default=[], help="only senses that accept this kind")
    fp = sub.add_parser("fanout", help="run an item through every tool that accepts it")
    fp.add_argument("item")
    fp.add_argument("--out", default="plexus-fanout", help="bundles are written in a new folder here")
    fp.add_argument("--kind", action="append", default=[],
                    help="add a kind the bytes cannot show (e.g. geometry, claim)")
    fp.add_argument("--grant-network", action="append", default=[], metavar="TOOL",
                    help="let this tool use the network (its manifest must also declare it)")
    fp.add_argument("--grant-kind", action="append", default=[], metavar="KIND",
                    help="allow a kind the policy holds behind a grant (e.g. screen)")
    fp.add_argument("--only", action="append", default=[], metavar="TOOL",
                    help="run only these tools; the rest are listed as skipped")
    fp.add_argument("--config", default=None, help="local config with roots and MCP servers")
    fp.add_argument("--dry-run", action="store_true", help="plan and check policy; run nothing")
    vp = sub.add_parser("fanout-verify", help="re-hash a bundle's outputs against its receipt")
    vp.add_argument("bundle")


def _summary(result: dict) -> dict:
    rows = [{k: r.get(k) for k in ("tool", "on", "status", "reason", "seconds", "peak_mb", "error")
             if r.get(k) not in (None, "")} for r in result["tools"]]
    return {"item": result["item"], "kinds": result["kinds"], "counts": result["counts"],
            "seconds": result["seconds"], "bundle": result.get("bundle", ""), "tools": rows}


def run_senses(args) -> int:
    if args.cmd == "kinds":
        from .kinds import detect
        print(json.dumps(detect(args.item), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "senses":
        from . import senses
        if args.check:
            problems = senses.check()
            print(json.dumps({"in_step": not problems, "problems": problems}, indent=2))
            return 1 if problems else 0
        rows = [{"tool": m.organ, "accepts": m.sense["accepts"], "runnable": bool(m.sense.get("run")),
                 "network": m.sense.get("network", False), "verified": m.sense.get("verified", "")}
                for m in senses.load()
                if not args.kind or set(args.kind) & set(m.sense["accepts"])]
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "fanout":
        from .runner.fanout import fanout, load_config
        grants = {"network": args.grant_network, "kinds": args.grant_kind}
        result = fanout(args.item, args.out, extra_kinds=args.kind, cfg=load_config(args.config),
                        grants=grants, dry_run=args.dry_run, only=set(args.only) or None)
        print(json.dumps(_summary(result), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "fanout-verify":
        from .runner.fanout import verify
        res = verify(args.bundle)
        print(json.dumps(res, indent=2))
        return 0 if res["verified"] else 1
    return 2
