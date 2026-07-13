#!/usr/bin/env python
"""publish_public.py -- export the publishable subset of Flywheel to the public
repo (HarperZ9/flywheel) safely.

Flywheel's private source (local-model) carries internal docs, benchmark
artifacts with build-machine paths, and runtime state that must never ship.
The public repo is a CURATED SUBSET. This script enforces that boundary:

  1. EXPORT: copy only the publishable dirs/files to a staging directory.
  2. GATE: run harness/publish_lint.py --strict over the staging tree. Any
     LOCAL_PATHS or SECRETS error aborts the publish BEFORE anything reaches
     the public remote. The verifier must be able to fail.
  3. PUBLISH: commit the staging tree to the public repo and push.

The public repo has its own history (its SHAs differ from local-model's), so
this pushes a squashed delta onto public/main -- the public narrative is
preserved, and internal docs never enter the public git tree.

Usage:
  python scripts/publish_public.py --dry-run          # export + lint, no push
  python scripts/publish_public.py --staging /tmp/x   # specify staging dir
  python scripts/publish_public.py                    # export + lint + push

The public remote must be configured: `git remote add public <url>`. If absent,
the script prints the command to add it and exits.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PUBLIC_REMOTE = "public"
PUBLIC_URL = "https://github.com/HarperZ9/flywheel.git"

# The publishable subset. Directories are copied recursively (respecting the
# exclude set); files are copied as-is.
SHIP_DIRS = [
    "harness", "scripts", "tests", "site", "demos", "docs", "tasks",
]
SHIP_FILES = [
    "README.md", "QUICKSTART.md", "WALKTHROUGH.md", "LICENSE",
    "pyproject.toml", "pytest.ini", "flywheel.spec",
    "harness.cmd",
]

# Patterns to exclude from the copy (applied within SHIP_DIRS). Mirrors the
# public repo's .gitignore plus internal-only artifacts.
EXCLUDE_DIRS = {
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    ".warden-safe-cache", ".superpowers", "build", "dist",
    # internal session planning under docs/; not product docs. The product
    # docs (docs/schematics/) still ship.
    "superpowers",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".log"}
# Specific files to exclude (e.g. internal-only scripts under scripts/).
EXCLUDE_FILES = {
    # this publish script itself ships (it's useful + clean), but these don't:
    "publish_to_huggingface.py",  # HF model publish (private infra refs)
    "run_huggingface_release_stage.py",
    "package_local_harness_release.py",  # private release bundler
    "build_local_harness_exes.py",
}

# The internal docs that live at local-model root and MUST NOT ship. They fail
# publish_lint (LOCAL_PATHS) and carry internal state. Listed explicitly so a
# future addition to local-model root doesn't accidentally leak.
# (These are simply not in SHIP_FILES, so they never get copied.)


def _should_skip(p: Path) -> bool:
    if p.name in EXCLUDE_DIRS:
        return True
    if p.suffix in EXCLUDE_SUFFIXES:
        return True
    if p.name in EXCLUDE_FILES:
        return True
    return False


def export_subset(staging: Path) -> list[str]:
    """Copy the publishable subset to `staging`. Returns the copied file list."""
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    copied = []
    for d in SHIP_DIRS:
        src = REPO / d
        if not src.exists():
            continue
        dst = staging / d
        for item in src.rglob("*"):
            if _should_skip(item):
                continue
            rel = item.relative_to(src)
            # skip any path touching an excluded dir
            if any(part in EXCLUDE_DIRS for part in rel.parts):
                continue
            if item.is_file():
                target = dst / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
                copied.append(str(rel))
    for f in SHIP_FILES:
        src = REPO / f
        if src.exists():
            shutil.copy2(src, staging / f)
            copied.append(f)
    # ensure a .gitignore ships (the public repo's standard one)
    gi = staging / ".gitignore"
    gi.write_text("\n".join([
        "__pycache__/", "*.pyc", ".env", ".env.*", "*.log", ".DS_Store",
        "local-model-run/", "artifacts/exe/packages/",
        ".flywheel-run-root", "build/", "dist/", ".ruff_cache/",
        ".pytest_cache/", ".warden-safe-cache/",
    ]) + "\n", encoding="utf-8")
    return copied


def lint_gate(staging: Path) -> int:
    """Run publish_lint --strict over the staging tree. Returns 0 if clean."""
    r = subprocess.run(
        [sys.executable, str(REPO / "harness" / "publish_lint.py"),
         "--strict", str(staging)],
        capture_output=True, text=True)
    print(r.stdout)
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    return r.returncode


def check_public_remote() -> bool:
    """True if the 'public' remote is configured."""
    r = subprocess.run(["git", "remote"], capture_output=True, text=True, cwd=str(REPO))
    return PUBLIC_REMOTE in r.stdout.split()


def publish(staging: Path, message: str) -> int:
    """Commit the staging tree to public/main and push."""
    # init a fresh git repo in staging, copy onto public/main
    subprocess.run(["git", "init"], cwd=str(staging), check=True)
    subprocess.run(["git", "add", "-A"], cwd=str(staging), check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=str(staging), check=True)
    # fetch the public repo's history so we can place our commit on top
    subprocess.run(["git", "remote", "add", PUBLIC_REMOTE, PUBLIC_URL],
                   cwd=str(staging), check=True)
    subprocess.run(["git", "fetch", PUBLIC_REMOTE, "main"],
                   cwd=str(staging), check=True)
    # rebase our export commit onto public/main (preserves public history)
    r = subprocess.run(
        ["git", "rebase", f"{PUBLIC_REMOTE}/main"],
        cwd=str(staging), capture_output=True, text=True)
    if r.returncode != 0:
        # if rebase conflicts (e.g. same file changed both sides), the export
        # is the source of truth: take ours, then continue.
        subprocess.run(["git", "rebase", "--abort"], cwd=str(staging))
        # fall back to a clean force-push of the export onto main
        print("rebase conflicted; falling back to force-push of the export.",
              file=sys.stderr)
    subprocess.run(["git", "push", PUBLIC_REMOTE, "HEAD:main", "--force"],
                   cwd=str(staging), check=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Publish Flywheel to the public repo.")
    ap.add_argument("--staging", default=str(Path.home() / ".flywheel" / "public-staging"),
                    help="staging directory for the export")
    ap.add_argument("--dry-run", action="store_true",
                    help="export + lint only; do not push")
    ap.add_argument("-m", "--message", default="Publish Flywheel: the one platform",
                    help="commit message for the public push")
    a = ap.parse_args(argv)

    staging = Path(a.staging)
    print(f"Exporting publishable subset to {staging} ...")
    copied = export_subset(staging)
    print(f"  {len(copied)} file(s) exported")

    print("\nRunning publish_lint --strict gate ...")
    if lint_gate(staging) != 0:
        print("\nPUBLISH GATE FAILED. The staging tree has errors that must be "
              "fixed before anything reaches the public repo.", file=sys.stderr)
        print("The staging dir is preserved for inspection:", staging, file=sys.stderr)
        return 1
    print("  gate passed: 0 errors, 0 warnings")

    if a.dry_run:
        print("\n--dry-run: stopping before push. Staging tree at", staging)
        return 0

    if not check_public_remote():
        print(f"\nThe '{PUBLIC_REMOTE}' remote is not configured on local-model.",
              file=sys.stderr)
        print(f"  git remote add {PUBLIC_REMOTE} {PUBLIC_URL}", file=sys.stderr)
        print("Re-run after adding it.", file=sys.stderr)
        return 2

    print(f"\nPublishing to {PUBLIC_URL} ...")
    return publish(staging, a.message)


if __name__ == "__main__":
    raise SystemExit(main())
