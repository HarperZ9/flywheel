"""check_release_digest.py -- the rule-pack digest in the release notes is the shipped one.

The notes for the declared version must print the digest of the installed
pre-action rule pack. Owners re-pin against that number, so a stale or
hand-typed digest would send every owner to a value that blocks all calls.

  python scripts/check_release_digest.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.preaction.rules import load_pack, pack_digest  # noqa: E402


def declared_version(root: Path = ROOT) -> str:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version\s*=\s*"(.+?)"', text, re.M).group(1)


def check(root: Path = ROOT) -> list[str]:
    notes = root / f"RELEASE-NOTES-{declared_version(root)}.md"
    if not notes.exists():
        return []          # no notes for this version yet: nothing to bind
    printed = set(re.findall(r"\b[0-9a-f]{64}\b", notes.read_text(encoding="utf-8")))
    shipped = pack_digest(load_pack())
    problems = []
    if shipped not in printed:
        problems.append(f"{notes.name} does not print the shipped rule-pack digest {shipped}")
    return problems


def main() -> int:
    problems = check()
    for p in problems:
        print(p)
    if not problems:
        print("release notes print the shipped rule-pack digest")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
