from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .hook_pack import HOOK_DIR, audit_hooks, discover_hooks, install_hooks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Utility wrapper for local public-safe agent hooks"
    )
    parser.add_argument(
        "command",
        choices=["audit", "install", "list", "path"],
        nargs="?",
        default="audit",
    )
    parser.add_argument("--source", default=str(HOOK_DIR))
    parser.add_argument("--target", default=".claude/hooks")
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "path":
        print(HOOK_DIR)
        return 0
    if args.command == "list":
        for path in discover_hooks(Path(args.source)):
            print(path.name)
        return 0
    if args.command == "audit":
        findings = audit_hooks(args.source)
        if findings:
            for path, issue in findings:
                print(f"{path}: {issue}")
            return 1
        print("findings: none")
        return 0
    copied = install_hooks(args.source, args.target)
    print(f"copied {copied} hook file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
