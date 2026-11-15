"""cli.py — plexus command line.

  plexus discover [--builtin] [--dir DIR]   # the mesh: organs, edges, orphans
  plexus wiring   [...]                      # capability -> (producer, consumer) pairs
  plexus plan --goal ORGAN [...]             # upstream pipeline that feeds ORGAN
  plexus route --from A --to B [...]         # capability path from A to B
  plexus pick "REQUEST" [--threshold P]      # pick a tool for a request, or abstain
  plexus validate [...]                      # manifest problems (exit 1 if any)
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from . import __version__
from .graph import to_dot, to_mermaid
from .manifest import content_hash, duplicate_organs, validate
from .mesh import discover
from .plan import plan_to, route
from .registry import builtin_manifests, export_all, load_dir
from .run import pipeline_script


def _load(args) -> list:
    mans = list(builtin_manifests()) if (args.builtin or not args.dir) else []
    if args.dir:
        mans += load_dir(args.dir)
    return mans


def _receipt(mesh) -> dict:
    """A re-runnable provenance receipt for the mesh: which manifests were read,
    from where, and a content hash a stranger can recompute from the same bytes."""
    return {
        "plexus_version": __version__,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "manifests": [{"organ": m.organ, "source": m.source,
                       "sha256": content_hash(m)}
                      for m in sorted(mesh.manifests.values(), key=lambda m: m.organ)],
    }


def _mesh_json(mesh) -> dict:
    return {
        "organs": mesh.organs,
        "edges": [{"producer": e.producer, "consumer": e.consumer,
                   "capability": e.capability, "self_loop": e.self_loop,
                   "via": e.producer_module, "evidence": e.evidence}
                  for e in mesh.edges],
        "orphans": mesh.orphans(),
        "collisions": mesh.collisions,
        "receipt": _receipt(mesh),
    }


def _add_source_flags(p):
    p.add_argument("--builtin", action="store_true", help="include the built-in flagship manifests")
    p.add_argument("--dir", default="", help="load *.interop.json manifests from this directory")


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(prog="plexus", description=__doc__)
    ap.add_argument("--version", action="version", version=f"plexus {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("discover", "wiring", "validate"):
        sp = sub.add_parser(name)
        _add_source_flags(sp)
    pp = sub.add_parser("plan"); _add_source_flags(pp)
    pp.add_argument("--goal", required=True, help="organ you want to feed")
    rp = sub.add_parser("route"); _add_source_flags(rp)
    rp.add_argument("--from", dest="src", required=True)
    rp.add_argument("--to", dest="dst", required=True)
    kp = sub.add_parser("pick", help="pick a tool for a request, or abstain")
    _add_source_flags(kp)
    kp.add_argument("request", help="the request in plain language")
    kp.add_argument("--threshold", type=float, default=0.23,
                    help="abstain when the top tool's probability is under this")
    vp = sub.add_parser("verify"); _add_source_flags(vp)
    vp.add_argument("--plan", required=True,
                    help="a plan/route JSON file (from `plexus plan`/`route`) to re-derive "
                         "and re-verify against the current mesh")
    gp = sub.add_parser("graph"); _add_source_flags(gp)
    gp.add_argument("--format", default="mermaid", choices=["mermaid", "dot"])
    up = sub.add_parser("run"); _add_source_flags(up)
    up.add_argument("--goal", required=True, help="organ you want to feed")
    ep = sub.add_parser("export")
    ep.add_argument("--dir", default="manifests", help="write <organ>.interop.json files here")
    sub.add_parser("mcp")   # stdio MCP server: discover/wiring/plan/route as tools

    args = ap.parse_args(argv)

    if args.cmd == "mcp":
        from .mcp import serve
        return serve()
    if args.cmd == "export":
        print("\n".join(export_all(args.dir)))
        return 0

    mans = _load(args)

    if args.cmd == "discover":
        print(json.dumps(_mesh_json(discover(mans)), indent=2))
        return 0
    if args.cmd == "wiring":
        print(json.dumps(discover(mans).wiring(), indent=2))
        return 0
    if args.cmd == "plan":
        print(json.dumps(plan_to(discover(mans), args.goal), indent=2))
        return 0
    if args.cmd == "route":
        print(json.dumps(route(discover(mans), args.src, args.dst), indent=2))
        return 0
    if args.cmd == "pick":
        from .pick import pick
        result = pick(discover(mans), args.request, threshold=args.threshold)
        print(json.dumps(result, indent=2))
        return 0
    if args.cmd == "verify":
        from .receipt import verify_plan
        with open(args.plan, encoding="utf-8") as f:
            plan = json.load(f)
        ok = verify_plan(plan, discover(mans))
        print(json.dumps({"verified": ok, "target": plan.get("target"),
                          "source": plan.get("source")}, indent=2))
        return 0 if ok else 1
    if args.cmd == "graph":
        mesh = discover(mans)
        print(to_mermaid(mesh) if args.format == "mermaid" else to_dot(mesh))
        return 0
    if args.cmd == "run":
        print(pipeline_script(discover(mans), args.goal))
        return 0
    if args.cmd == "validate":
        problems = {m.organ: validate(m) for m in mans}
        report = {k: v for k, v in problems.items() if v}
        dups = duplicate_organs(mans)
        if dups:
            # A set-level clash the per-organ dict above cannot show (its own key
            # collapses the duplicates); name it so a collision can never launder
            # to {"ok": true}.
            report["duplicate_organs"] = dups
        print(json.dumps(report or {"ok": True}, indent=2))
        return 1 if report else 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
