"""verification_share_cli.py -- `flywheel verify-share`: verified share over time and cost to verify.

  flywheel verify-share items.jsonl            shipped-item records, one JSON object per line
  flywheel verify-share prs.json --github      output of `gh pr list --state merged --json
                                               number,title,mergedAt,additions,deletions,
                                               author,reviews,statusCheckRollup`

For GitHub pull requests: person when someone other than the author approved
it, machine when every reported check passed and at least one ran, unchecked
otherwise. The family is the repository (a "repository" field added to each
pull request, as when several repositories are merged into one file), or with
--family-from prefix the conventional-commit prefix of the title (feat, fix,
docs, ...), or "other". Size is lines added plus lines deleted. GitHub
records no review time, so reviewer minutes stay empty for these items.
Exit code 0, or 1 when any week is flagged.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .verification_meter import render, report
from .verification_share import Item, item_from_dict

_PREFIX = re.compile(r"^\s*([A-Za-z]+)(\([^)]*\))?!?:")
_PASS = {"SUCCESS", "NEUTRAL", "SKIPPED"}


def _check_state(check: dict) -> str:
    return str(check.get("conclusion") or check.get("state") or "").upper()


def pr_route(pr: dict) -> str:
    author = (pr.get("author") or {}).get("login", "")
    if any(r.get("state") == "APPROVED" and (r.get("author") or {}).get("login") not in ("", author)
           for r in pr.get("reviews") or []):
        return "person"
    states = [_check_state(c) for c in pr.get("statusCheckRollup") or []]
    if states and all(s in _PASS for s in states) and "SUCCESS" in states:
        return "machine"
    return "unchecked"


def pr_family(title: str) -> str:
    m = _PREFIX.match(title or "")
    return m.group(1).lower() if m else "other"


def item_from_pr(pr: dict, family_from: str = "repo") -> Item:
    repo = pr.get("repository") or ""
    family = repo if family_from == "repo" and repo else pr_family(pr.get("title", ""))
    return Item(f"{repo}#{pr['number']}", pr["mergedAt"], family,
                pr_route(pr), int(pr.get("additions", 0)) + int(pr.get("deletions", 0)))


def load_items(path: str, github: bool, family_from: str = "repo") -> list:
    text = Path(path).read_text(encoding="utf-8")
    if github:
        return [item_from_pr(pr, family_from) for pr in json.loads(text) if pr.get("mergedAt")]
    return [item_from_dict(json.loads(line)) for line in text.splitlines() if line.strip()]


def main(argv=None, *, stdout=None, stderr=None) -> int:
    stdout = stdout if stdout is not None else sys.stdout
    stderr = stderr if stderr is not None else sys.stderr
    p = argparse.ArgumentParser(prog="flywheel verify-share")
    p.add_argument("items")
    p.add_argument("--github", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--family-from", dest="family_from", choices=("repo", "prefix"), default="repo")
    try:
        args = p.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 2)
    try:
        rep = report(load_items(args.items, args.github, args.family_from))
    except (OSError, ValueError, KeyError) as exc:
        stderr.write(f"cannot read shipped items from {args.items}: {type(exc).__name__}: {exc}\n")
        return 2
    stdout.write((json.dumps(rep) if args.json else render(rep)) + "\n")
    return 1 if rep["flags"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
