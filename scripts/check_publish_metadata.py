#!/usr/bin/env python3
"""check_publish_metadata.py -- find personal metadata before a file is published.

A published file can carry its author in places nobody reads on screen: EXIF
and PNG text chunks, a PDF /Author or XMP packet, a docx core.xml creator, a
local path in a comment, the build machine's name, a personal address in a
fetch script's User-Agent, or the author email and timezone on the commits
that ship it. This check reads every published file for those.

Usage:
  check_publish_metadata.py PATH... [--mode report|fail|fix] [--json OUT]
                            [--git unpushed|all|none|<range>] [--deny-list FILE]
                            [--all-files] [--allow GLOB]

Modes:
  report  list findings, exit 0 (the default)
  fail    list findings, exit 1 when any file finding exists
  fix     strip image, PDF and Office metadata in place, then report what is
          left; exit 1 when a file finding remains. Text is never rewritten.

Git findings are warnings in every mode: they describe history, and history
is fixed by configuration (a noreply address, TZ=UTC), not by this check.

Files: inside a git checkout only tracked files are read, since those are what
publish; --all-files reads the whole tree. A `.publish-metadata-allow` file at
the root lists globs to skip, one per line, for fixtures that need a path.
Private patterns (addresses, the machine name) are gathered at run time and
from an untracked deny list; see publish_metadata_text.py. Stdlib only.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_metadata_binary as B  # noqa: E402
import publish_metadata_text as T  # noqa: E402

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "env", "__pycache__",
             "site-packages", ".tox", ".mypy_cache", ".pytest_cache", "dist-packages"}
ALLOW_FILE = ".publish-metadata-allow"
TEXT_LIMIT = 20 * 1024 * 1024


def tracked_files(root: Path):
    out = T._git(["ls-files", "-z"], cwd=root)
    if out is None:
        return None
    return [root / p for p in out.split("\0") if p]


def walk_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".venv")]
        for name in filenames:
            yield Path(dirpath) / name


def allow_globs(root: Path, extra):
    globs = list(extra or [])
    f = root / ALLOW_FILE
    if f.is_file():
        globs += [g.strip() for g in f.read_text(encoding="utf-8").splitlines()
                  if g.strip() and not g.startswith("#")]
    return globs


def select_files(root: Path, all_files: bool, extra_allow):
    if root.is_file():
        return [root], root.parent
    files = None if all_files else tracked_files(root)
    if files is None:
        files = list(walk_files(root))
    globs = allow_globs(root, extra_allow)
    keep = []
    for p in files:
        rel = p.relative_to(root).as_posix()
        if any(part in SKIP_DIRS for part in Path(rel).parts):
            continue
        if globs and any(fnmatch.fnmatch(rel, g) for g in globs):
            continue
        if p.is_file():
            keep.append(p)
    return keep, root


def scan_file(path: Path, patterns, fix: bool):
    """Return (findings, fixed). Findings are (line or 0, category, detail)."""
    suffix = path.suffix.lower()
    try:
        data = path.read_bytes()
    except OSError as exc:
        return [(0, "unreadable", str(exc))], False
    if suffix in B.BINARY_EXT:
        found = B.check_binary(suffix, data)
        fixed = False
        if found and fix:
            new = B.fix_binary(suffix, data)
            if new is not None and new != data:
                path.write_bytes(new)
                fixed = True
                found = B.check_binary(suffix, new)
        return [(0, c, d) for c, d in found], fixed
    if len(data) > TEXT_LIMIT or b"\0" in data[:8192]:
        return [], False
    text = data.decode("utf-8", errors="replace")
    return T.check_text(text, suffix, patterns), False


def run(paths, mode="report", git="unpushed", deny_list=None, all_files=False,
        allow=None, stream=sys.stdout):
    patterns = T.GENERIC + T.local_patterns(deny_list)
    results = {"roots": [], "mode": mode}
    file_findings = 0
    for raw in paths:
        files, root = select_files(Path(raw).resolve(), all_files, allow)
        cats, fixed, hit_files = Counter(), 0, set()
        for p in files:
            found, was_fixed = scan_file(p, patterns, mode == "fix")
            fixed += was_fixed
            rel = p.relative_to(root).as_posix()
            for line, cat, detail in found:
                cats[cat] += 1
                hit_files.add(rel)
                where = f"{rel}:{line}" if line else rel
                print(f"{where}: {cat}: {detail}", file=stream)
        git_found = [] if git == "none" else T.check_git(root, git)
        for cat, detail in git_found:
            print(f"(git): warning: {cat}: {detail}", file=stream)
        file_findings += sum(cats.values())
        summary = {"root": root.name, "files_scanned": len(files), "files_with_findings":
                   len(hit_files), "findings": dict(sorted(cats.items())), "fixed_files": fixed,
                   "git_warnings": [d for _c, d in git_found]}
        results["roots"].append(summary)
        print(f"== {root.name}: {len(files)} files, {len(hit_files)} with findings, "
              f"{sum(cats.values())} findings {dict(sorted(cats.items()))}, "
              f"{fixed} fixed, {len(git_found)} git warnings", file=stream)
    results["file_findings"] = file_findings
    code = 1 if (mode in ("fail", "fix") and file_findings) else 0
    return code, results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--mode", choices=("report", "fail", "fix"), default="report")
    ap.add_argument("--git", default="unpushed",
                    help="unpushed (default), all, none, or a git revision range")
    ap.add_argument("--deny-list", help="untracked file of private regexes, one per line")
    ap.add_argument("--all-files", action="store_true", help="read untracked files too")
    ap.add_argument("--allow", action="append", help="glob to skip (repeatable)")
    ap.add_argument("--json", help="write a JSON summary here (counts only, no values)")
    a = ap.parse_args(argv)
    code, results = run(a.paths, a.mode, a.git, a.deny_list, a.all_files, a.allow)
    if a.json:
        Path(a.json).write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
