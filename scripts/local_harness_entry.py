"""Entry-point wrapper for the full local harness executable."""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def _candidate_roots() -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get("LOCAL_HARNESS_REPO", "").strip()
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(Path.cwd())
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        candidates.extend([exe.parent, exe.parent.parent, exe.parent.parent.parent])
    candidates.append(Path(__file__).resolve().parent.parent)
    return candidates


def _find_repo_root() -> Path:
    seen: set[Path] = set()
    for candidate in _candidate_roots():
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        for root in [resolved, *resolved.parents]:
            if root in seen:
                continue
            seen.add(root)
            if (root / "scripts" / "run_harness_cli.py").exists() and (root / "harness").is_dir():
                return root
    raise FileNotFoundError(
        "could not locate local-model repo root; set LOCAL_HARNESS_REPO to the checkout containing scripts/run_harness_cli.py"
    )


def main(argv: list[str] | None = None) -> int:
    repo_root = _find_repo_root()
    script = repo_root / "scripts" / "run_harness_cli.py"
    os.chdir(repo_root)
    sys.argv = [str(script), *(argv if argv is not None else sys.argv[1:])]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
