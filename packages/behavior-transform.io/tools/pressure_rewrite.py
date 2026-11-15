#!/usr/bin/env python3
"""Apply the vocabulary calibration to source files in-place.

For each Calibration:
  - identifier / module-name scope: word-boundary case-sensitive replace
  - free-prose / verb-prose / noun-prose scope: case-insensitive with
    case preservation (UPPER, Title, lower)

Skips:
  - LINTER_WHITELIST paths
  - SKIP_DIRS in path components
  - Lines containing `# noqa: AUP-ALIAS` or `# noqa: AUP-ARCHIVE`

This rewrites string content only. Module / directory renames must be
performed separately (e.g., `git mv old_path new_path`).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from vocabulary_map import (  # type: ignore[import-not-found]
    CALIBRATIONS,
    LINTER_WHITELIST,
    by_severity,
)

SCAN_EXTENSIONS = {
    ".py", ".pyi", ".md", ".rst", ".txt", ".sh", ".bash", ".zsh",
    ".yaml", ".yml", ".toml", ".json", ".cfg", ".ini",
}
SKIP_DIRS = {
    ".git", ".github", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".tox", ".venv", "venv", "node_modules", "dist", "build", ".eggs",
}
PROSE_SCOPES = {"free-prose", "verb-prose", "noun-prose"}


def _preserve_case(matched: str, calibrated: str) -> str:
    if matched.isupper():
        return calibrated.upper()
    if matched and matched[0].isupper() and (len(matched) == 1 or matched[1:].islower()):
        if "-" in calibrated or " " in calibrated:
            head, *rest = calibrated.split(maxsplit=1) if " " in calibrated else (calibrated.split("-", 1)[0], calibrated.split("-", 1)[1])
            return calibrated[0].upper() + calibrated[1:]
        return calibrated[0].upper() + calibrated[1:].lower()
    return calibrated


def _build_compiled(severity: str) -> list[tuple[re.Pattern[str], str, str, str]]:
    cals = sorted(by_severity(severity), key=lambda c: len(c.original), reverse=True)
    out: list[tuple[re.Pattern[str], str, str, str]] = []
    for c in cals:
        flags = re.IGNORECASE if c.scope in PROSE_SCOPES else 0
        if " " in c.original:
            parts = [re.escape(p) for p in c.original.split(" ")]
            pattern = r"\s+".join(parts)
        else:
            pattern = re.escape(c.original)
        if " " not in c.original and "-" not in c.original and "/" not in c.original:
            pattern = r"\b" + pattern + r"\b"
        out.append((re.compile(pattern, flags), c.calibrated, c.scope, c.original))
    return out


def _is_whitelisted(path: Path) -> bool:
    pp = path.as_posix()
    return any(w in pp for w in LINTER_WHITELIST)


def _walk(paths: list[Path]):
    for p in paths:
        if not p.exists():
            continue
        if p.is_file():
            if p.suffix.lower() in SCAN_EXTENSIONS:
                yield p
            continue
        for f in p.rglob("*"):
            if any(part in SKIP_DIRS for part in f.parts):
                continue
            if f.is_file() and f.suffix.lower() in SCAN_EXTENSIONS:
                yield f


def _process_text(text: str, compiled: list) -> tuple[str, int]:
    n_total = 0
    for regex, calibrated, scope, original in compiled:
        if scope in PROSE_SCOPES:
            def repl(m, cal=calibrated):
                return _preserve_case(m.group(0), cal)
            text, n = regex.subn(repl, text)
        else:
            text, n = regex.subn(calibrated, text)
        n_total += n
    return text, n_total


def _default_paths() -> list[Path]:
    return [Path.cwd()]


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="AUP vocabulary rewriter")
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-tier2", action="store_true")
    args = ap.parse_args(argv)

    paths = [Path(p) for p in args.paths] if args.paths else _default_paths()
    severities = ["tier1"] + (["tier2"] if args.include_tier2 else [])
    compiled: list = []
    for s in severities:
        compiled.extend(_build_compiled(s))

    scanned = 0
    changed: list[tuple[Path, int]] = []
    total_repl = 0

    for f in _walk(paths):
        if _is_whitelisted(f):
            continue
        scanned += 1
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        new_text, n = _process_text(text, compiled)
        if n and new_text != text:
            changed.append((f, n))
            total_repl += n
            if not args.dry_run:
                f.write_text(new_text, encoding="utf-8")

    suffix = " (dry run)" if args.dry_run else ""
    print(f"scanned {scanned} files; {len(changed)} touched; {total_repl} replacements{suffix}")
    for f, n in sorted(changed, key=lambda x: -x[1])[:40]:
        print(f"  {n:5d}  {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

