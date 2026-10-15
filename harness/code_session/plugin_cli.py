"""`flywheel plugin`: install, list and remove plugins for `flywheel code`.

  flywheel plugin install <folder or git URL> [--yes]
  flywheel plugin list
  flywheel plugin remove NAME
"""
from __future__ import annotations

import argparse
import os
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


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(prog="flywheel plugin", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ins = sub.add_parser("install", help="install from a folder or a git URL")
    ins.add_argument("source")
    ins.add_argument("--yes", action="store_true", help="install without asking")
    sub.add_parser("list", help="installed plugins")
    rm = sub.add_parser("remove", help="remove an installed plugin")
    rm.add_argument("name")
    args = ap.parse_args(argv)
    home = _home()
    if args.cmd == "list":
        print(listing(home))
        return 0
    if args.cmd == "remove":
        ok = remove(args.name, home)
        print(f"removed {args.name}" if ok else f"{args.name} is not installed")
        return 0 if ok else 1
    try:
        record = install(args.source, home, confirm=None if args.yes else _confirm)
    except PluginError as e:
        print(f"[plugin] {e}", file=sys.stderr)
        return 1
    print(f"installed {record['name']} from {record['source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
