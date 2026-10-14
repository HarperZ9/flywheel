"""`flywheel mcp`: list, add and remove the MCP servers `flywheel code` starts.

  flywheel mcp list
  flywheel mcp add NAME -- COMMAND [ARGS...]      in FLYWHEEL_HOME/mcp.json
  flywheel mcp add NAME --url https://host/mcp
  flywheel mcp add NAME --project -- COMMAND ...   in .flywheel/mcp.json here
  flywheel mcp remove NAME [--project]

The files use the mcpServers shape Claude Code and Cursor read.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .mcp_config import PROJECT_FILES, USER_FILE, load_specs


def _home() -> str:
    from harness.lane_workdir import flywheel_home
    return str(flywheel_home(os.environ))


def _target(project: bool) -> Path:
    return Path.cwd() / PROJECT_FILES[0] if project else Path(_home()) / USER_FILE


def _read(path: Path) -> dict:
    if not path.is_file():
        return {"mcpServers": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("mcpServers", {})
    return data


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def cmd_list(_args) -> int:
    specs, errors = load_specs(os.getcwd(), _home())
    for err in errors:
        print(f"[error] {err}", file=sys.stderr)
    if not specs:
        print("no MCP servers configured")
    for s in specs:
        where = "trusted" if s.trusted else "project, asks before starting"
        print(f"{s.name:<20} {s.url or ' '.join(s.command)}  ({where}; {s.source})")
    return 1 if errors else 0


def cmd_add(args) -> int:
    if bool(args.url) == bool(args.command):
        print("give either --url or -- COMMAND [ARGS...]", file=sys.stderr)
        return 2
    path = _target(args.project)
    data = _read(path)
    entry = {"type": "http", "url": args.url} if args.url else \
        {"command": args.command[0], "args": args.command[1:]}
    data["mcpServers"][args.name] = entry
    _write(path, data)
    print(f"added {args.name} to {path}")
    return 0


def cmd_remove(args) -> int:
    path = _target(args.project)
    data = _read(path)
    if data["mcpServers"].pop(args.name, None) is None:
        print(f"{args.name} is not in {path}", file=sys.stderr)
        return 1
    _write(path, data)
    print(f"removed {args.name} from {path}")
    return 0


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(prog="flywheel mcp", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="every configured server and where it comes from")
    add = sub.add_parser("add", help="add a server")
    add.add_argument("name")
    add.add_argument("--url", default="", help="a Streamable HTTP server")
    add.add_argument("--project", action="store_true", help="write .flywheel/mcp.json here")
    add.epilog = "Put the server command after --: flywheel mcp add NAME -- COMMAND [ARGS...]"
    rm = sub.add_parser("remove", help="remove a server")
    rm.add_argument("name")
    rm.add_argument("--project", action="store_true")
    raw = list(sys.argv[1:] if argv is None else argv)
    command = raw[raw.index("--") + 1:] if "--" in raw else []
    args = ap.parse_args(raw[:raw.index("--")] if "--" in raw else raw)
    args.command = command
    return {"list": cmd_list, "add": cmd_add, "remove": cmd_remove}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
