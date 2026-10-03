"""cli_extra.py -- the owner commands added with the OASP alignment, split out of cli.py.

owner          print the effective owner config and its digest
witness        join harness transcripts and exported chain heads against a store
import-ocsf    turn an OpenShell OCSF JSONL file into sealed records
sandbox        write an OpenShell policy and print (or run) the sandbox commands

Exit codes for witness and import-ocsf: 0 MATCH, 1 DRIFT, 3 UNVERIFIABLE.
"""
from __future__ import annotations

import json
from pathlib import Path

COMMANDS = ("owner", "witness", "import-ocsf", "sandbox")
_EXIT = {"MATCH": 0, "DRIFT": 1, "UNVERIFIABLE": 3}


def register(sub) -> None:
    po = sub.add_parser("owner")
    po.add_argument("--owner-config", dest="owner_config", default="")
    pw = sub.add_parser("witness")
    pw.add_argument("--home", required=True)
    pw.add_argument("--witness-dir", dest="witness_dir", required=True)
    pw.add_argument("--transcripts", nargs="*", default=[])
    pw.add_argument("--grace", type=int, default=60)
    pw.add_argument("--now", default="")
    pi = sub.add_parser("import-ocsf")
    pi.add_argument("file")
    pi.add_argument("--home", required=True)
    pi.add_argument("--metrics", default="")
    ps = sub.add_parser("sandbox")
    ps.add_argument("client", choices=("claude-code", "codex"))
    ps.add_argument("--workspace", required=True)
    ps.add_argument("--out", required=True)
    ps.add_argument("--name", default="flywheel-hooked")
    ps.add_argument("--image", default="")
    ps.add_argument("--owner-config", dest="owner_config", default="")
    ps.add_argument("--run", action="store_true")


def _owner(args, stdout) -> int:
    from .owner import load
    from .rules import load_pack, pack_digest
    o = load(args.owner_config or None)
    stdout.write(json.dumps({"source": o.source, "path": o.path, "digest": o.digest(),
                             "installed_rules_digest": pack_digest(load_pack()),
                             "effective": o.effective()}, indent=2) + "\n")
    return 0


def _witness(args, stdout) -> int:
    from .witness import run_witness
    files = []
    for t in args.transcripts:
        p = Path(t)
        files += sorted(p.rglob("*.jsonl")) if p.is_dir() else [p]
    rec = run_witness(args.home, args.witness_dir, files, grace_seconds=args.grace, now=args.now)
    stdout.write(json.dumps(rec) + "\n")
    return _EXIT[rec["verdict"]]


def _import(args, stdout) -> int:
    from .ocsf_import import import_file
    metrics = Path(args.metrics).read_text(encoding="utf-8") if args.metrics else None
    summary = import_file(args.file, args.home, metrics_text=metrics)
    stdout.write(json.dumps(summary) + "\n")
    return _EXIT[summary["completeness"]]


def _sandbox(args, stdout, stderr) -> int:
    from . import openshell_launch as osl
    from .owner import load
    p = osl.plan(args.client, owner=load(args.owner_config or None), workspace=args.workspace,
                 out_dir=args.out, name=args.name, image=args.image)
    stdout.write(osl.to_json(p) + "\n")
    if not args.run:
        return 0
    if not p["available"]:
        stderr.write(f"OpenShell is not available here: {p['reason']}\n")
        return 3
    return osl.run(p)


def dispatch(args, stdout, stderr) -> int:
    if args.cmd == "owner":
        return _owner(args, stdout)
    if args.cmd == "witness":
        return _witness(args, stdout)
    if args.cmd == "import-ocsf":
        return _import(args, stdout)
    return _sandbox(args, stdout, stderr)
