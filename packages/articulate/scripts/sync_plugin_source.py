#!/usr/bin/env python
"""Rewrite claude-plugin/src/articulate from src/articulate.

    python scripts/sync_plugin_source.py [--check]

The Claude plugin folder carries the package modules its MCP server and edit
hook import, so a directory install that receives only claude-plugin/ starts.
The copy holds exactly build_claude_plugin.package_files(): the modules
reachable from the server and hook entry points and the package's tracked
files that are not Python source. Files use LF line endings. --check reports
drift and exits 1 instead of writing.
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_claude_plugin as build  # noqa: E402  (the path is set just above)

TARGET = build.REPO / "claude-plugin" / "src" / "articulate"


def _lf(data):
    return data.replace(b"\r\n", b"\n")


def expected(repo=build.REPO):
    source = Path(repo) / "src" / "articulate"
    return {rel.as_posix(): _lf((source / rel).read_bytes()) for rel in build.package_files(repo)}


def committed(target=TARGET):
    if not target.is_dir():
        return {}
    return {p.relative_to(target).as_posix(): _lf(p.read_bytes()) for p in sorted(target.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo")}


def drift(repo=build.REPO, target=TARGET):
    want, have = expected(repo), committed(target)
    return sorted(set(want) ^ set(have)) + sorted(n for n in set(want) & set(have) if want[n] != have[n])


def sync(repo=build.REPO, target=TARGET):
    want, have = expected(repo), committed(target)
    for name in set(have) - set(want):
        (target / name).unlink()
    for name, data in want.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if have.get(name) != data:
            path.write_bytes(data)
    return sorted(want)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report drift and exit 1")
    args = parser.parse_args(argv)
    if args.check:
        problems = drift()
        for name in problems:
            print("differs from src/articulate: " + name)
        return 1 if problems else 0
    print("%d files in claude-plugin/src/articulate" % len(sync()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
