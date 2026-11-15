#!/usr/bin/env python3
"""install_precommit - install the AUP-lint pre-commit hook into a git repo.

Copies tools/pre-commit-aup.sh into the target repository's
.git/hooks/pre-commit, sets it executable, and verifies that pressure_scan.py
is reachable from the hook's PATH-relative location.

Usage:
    python tools/install_precommit.py [REPO_PATH]   # default: cwd
    python tools/install_precommit.py --uninstall   # remove the hook
    python tools/install_precommit.py --check       # dry-run check

The installed hook runs `pressure_scan.py --fail-tier2` against staged files
only. It blocks commits containing Tier-1 drift (always) and Tier-2
drift (when configured). It does not modify files — use
`pressure_scan.py --fix` separately to auto-rewrite.
"""
from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
from pathlib import Path


_HOOK_NAME = "pre-commit"


def _resolve_source(tool_root: Path) -> Path:
    candidate = tool_root / "pre-commit-aup.sh"
    if not candidate.is_file():
        raise FileNotFoundError(
            f"pre-commit-aup.sh not found alongside install_precommit.py "
            f"(expected at {candidate})"
        )
    return candidate


def _resolve_target(repo_path: Path) -> Path:
    git_dir = repo_path / ".git"
    if git_dir.is_file():
        # Submodule worktree: .git is a file containing gitdir: <path>
        content = git_dir.read_text(encoding="utf-8").strip()
        if content.startswith("gitdir:"):
            git_dir = (repo_path / content.split(":", 1)[1].strip()).resolve()
    if not git_dir.is_dir():
        raise FileNotFoundError(
            f"not a git repository (no .git/ at {repo_path})"
        )
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    return hooks_dir / _HOOK_NAME


def install(repo_path: Path, *, check: bool = False) -> int:
    tool_root = Path(__file__).resolve().parent
    try:
        source = _resolve_source(tool_root)
        target = _resolve_target(repo_path)
    except FileNotFoundError as e:
        sys.stderr.write(f"install_precommit: {e}\n")
        return 2

    if check:
        existing = target.exists()
        sys.stdout.write(
            f"install_precommit: source={source} target={target} "
            f"existing={existing}\n"
        )
        return 0

    # Back up any pre-existing hook so we never destroy user customizations.
    if target.exists():
        backup = target.with_suffix(target.suffix + ".bak")
        if not backup.exists():
            shutil.copy2(target, backup)
            sys.stderr.write(f"install_precommit: backed up existing hook to {backup}\n")

    shutil.copy2(source, target)
    # chmod +x on POSIX; no-op on Windows (git looks at file extension).
    try:
        st = os.stat(target)
        os.chmod(target, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass
    sys.stdout.write(f"install_precommit: installed {source} -> {target}\n")
    return 0


def uninstall(repo_path: Path) -> int:
    try:
        target = _resolve_target(repo_path)
    except FileNotFoundError as e:
        sys.stderr.write(f"install_precommit: {e}\n")
        return 2
    if not target.exists():
        sys.stdout.write(f"install_precommit: no hook at {target}\n")
        return 0
    backup = target.with_suffix(target.suffix + ".bak")
    if backup.exists():
        shutil.copy2(backup, target)
        backup.unlink()
        sys.stdout.write(f"install_precommit: restored backup {backup} -> {target}\n")
    else:
        target.unlink()
        sys.stdout.write(f"install_precommit: removed {target}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install or remove the AUP pre-commit hook.",
    )
    parser.add_argument("repo_path", nargs="?", type=Path, default=Path.cwd(),
                        help="Target repository (default: cwd).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--uninstall", action="store_true",
                      help="Remove the installed hook (restoring any backup).")
    mode.add_argument("--check", action="store_true",
                      help="Dry-run: report source/target paths without writing.")
    args = parser.parse_args(argv)

    if args.uninstall:
        return uninstall(args.repo_path)
    return install(args.repo_path, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
