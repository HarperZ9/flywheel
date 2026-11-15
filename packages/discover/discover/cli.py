"""discover: a pre-release check that a project can be found by the people it serves.

    discover repo  [PATH] [--github OWNER/REPO] [--notes FILE] [--version X] [--offline]
    discover site  [ROOT] [--online]
    discover video MANIFEST.json

Every command prints a scored report and a list of fixes. --gate exits 1 when an
error-level check fails or the score is under --min-score. --json prints the
full report as JSON.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .repo import check_repo
from .site import check_site
from .video import check_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="discover", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"discover {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("repo", "site", "video"):
        cmd = sub.add_parser(name)
        cmd.add_argument("path", nargs="?" if name != "video" else None, default=".")
        cmd.add_argument("--gate", action="store_true", help="exit 1 on a blocking failure")
        cmd.add_argument("--min-score", type=int, default=0)
        cmd.add_argument("--json", action="store_true")
        cmd.add_argument("--limit", type=int, default=8, help="failures shown per check")
    repo = sub.choices["repo"]
    repo.add_argument("--github", help="OWNER/REPO; default from GITHUB_REPOSITORY or the git remote")
    repo.add_argument("--notes", help="release notes file to check instead of CHANGELOG.md")
    repo.add_argument("--release", dest="release", help="version being released; default from the tag")
    repo.add_argument("--offline", action="store_true", help="skip the GitHub metadata read")
    sub.choices["site"].add_argument("--online", action="store_true",
                                     help="compare tool versions with PyPI, npm and GitHub")
    return parser


def run(args: argparse.Namespace):
    path = Path(args.path)
    if args.command == "repo":
        return check_repo(path, args.offline, args.github, args.notes, args.release)
    if args.command == "site":
        return check_site(path, args.online)
    return check_manifest(path)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run(args)
    print(report.to_json() if args.json else report.to_text(args.limit))
    if args.gate and not report.passes(args.min_score):
        print(f"\ndiscover: gate failed ({len(report.blocking)} blocking, score {report.score})",
              file=sys.stderr)
        return 1
    return 0
