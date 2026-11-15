"""articulate code -- static checks on code changes.

    articulate code test-diff BASE [HEAD] [--repo DIR] [--declared concept.json] [--json]
    articulate code test-diff --before OLD.py --after NEW.py [--path tests/test_x.py]

Report-only: the exit status is 0 whatever the findings, 2 on a usage or git
error. A caller that wants a gate reads `status` from the JSON and decides.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .gitdiff import GitError, changes_between
from .report import FileChange, analyze, render_text


def _read(path):
    return None if path in (None, "-") else Path(path).read_text(encoding="utf-8")


def _declared(path):
    if not path:
        return ()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("declared_test_changes", [])
    return data if isinstance(data, list) else ()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="articulate code",
                                 description="Static checks on code changes (report-only).")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("test-diff", help="did this change make the tests check less?")
    p.add_argument("base", nargs="?", help="base commit")
    p.add_argument("head", nargs="?", default="HEAD", help="head commit (default HEAD)")
    p.add_argument("--repo", default=".", help="git repository (default .)")
    p.add_argument("--before", help="old version of one test file ('-' for none)")
    p.add_argument("--after", help="new version of one test file ('-' for none)")
    p.add_argument("--path", default="tests/test_file.py",
                   help="repository path to report for --before/--after")
    p.add_argument("--declared", help="concept.json (declared_test_changes) or a JSON list")
    p.add_argument("--json", action="store_true", help="emit the JSON report")
    args = ap.parse_args(argv)
    if args.cmd != "test-diff":
        ap.print_help()
        return 2
    try:
        if args.before is not None or args.after is not None:
            changes = [FileChange(args.path, _read(args.before), _read(args.after))]
        elif args.base:
            changes = changes_between(args.repo, args.base, args.head)
        else:
            ap.error("give BASE [HEAD] or --before/--after")
        report = analyze(changes, _declared(args.declared))
    except (GitError, OSError, ValueError) as exc:
        print(f"articulate code: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2) if args.json else render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
