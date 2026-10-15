"""`flywheel plugin`: install, list and remove plugins for `flywheel code`.

  flywheel plugin install <folder, git URL or NAME@MARKETPLACE> [--yes]
  flywheel plugin list
  flywheel plugin remove NAME
  flywheel plugin marketplace add <folder or git URL>
  flywheel plugin marketplace list
  flywheel plugin search [words]
"""
from __future__ import annotations

import argparse
import os
import re
import sys

from .plugins import PluginError, install, listing, remove


def _home() -> str:
    from harness.lane_workdir import flywheel_home
    return str(flywheel_home(os.environ))


def _confirm(name: str, info: dict) -> bool:
    print(f"Plugin {name}: {info['commands']} command(s), {info['agents']} agent(s), "
          f"{info['skills']} skill(s).")
    for line in info["hooks"]:
        print(f"  hook runs: {line}")
    for line in info["mcp_servers"]:
        print(f"  MCP server: {line}")
    if info["hooks"] or info["mcp_servers"]:
        print("Hooks and MCP servers run these programs as you, outside the command sandbox.")
    try:
        return input("Install? [y/N]: ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def _market(args, home: str) -> int:
    from .marketplace import add, markets, search
    try:
        if args.cmd == "search":
            rows = search(home, " ".join(args.words))
            print("\n".join(f"{n:<32} {d[:80]}" for n, d in rows) or "nothing matches")
            return 0
        if args.action == "list":
            found = markets(home)
            print("\n".join(f"{n:<20} {len(c['plugins'])} plugin(s)" for n, (_f, c) in found.items())
                  or "no marketplaces added")
            return 0
        if not args.source:
            print("give the marketplace folder or git URL", file=sys.stderr)
            return 2
        info = add(args.source, home)
        print(f"added marketplace {info['name']} ({info['plugins']} plugin(s)) from {info['source']}")
        return 0
    except PluginError as e:
        print(f"[plugin] {e}", file=sys.stderr)
        return 1


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(prog="flywheel plugin", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ins = sub.add_parser("install", help="install from a folder or a git URL")
    ins.add_argument("source")
    ins.add_argument("--yes", action="store_true", help="install without asking")
    sub.add_parser("list", help="installed plugins")
    rm = sub.add_parser("remove", help="remove an installed plugin")
    rm.add_argument("name")
    mk = sub.add_parser("marketplace", help="add or list plugin marketplaces")
    mk.add_argument("action", choices=("add", "list"))
    mk.add_argument("source", nargs="?", default="")
    se = sub.add_parser("search", help="search the added marketplaces")
    se.add_argument("words", nargs="*")
    args = ap.parse_args(argv)
    home = _home()
    if args.cmd in ("marketplace", "search"):
        return _market(args, home)
    if args.cmd == "list":
        print(listing(home))
        return 0
    if args.cmd == "remove":
        ok = remove(args.name, home)
        print(f"removed {args.name}" if ok else f"{args.name} is not installed")
        return 0 if ok else 1
    try:
        source = args.source
        if re.fullmatch(r"[A-Za-z0-9._-]+@[A-Za-z0-9._-]+", source):
            from .marketplace import resolve
            source = resolve(source, home)
        record = install(source, home, confirm=None if args.yes else _confirm)
    except PluginError as e:
        print(f"[plugin] {e}", file=sys.stderr)
        return 1
    print(f"installed {record['name']} from {record['source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
