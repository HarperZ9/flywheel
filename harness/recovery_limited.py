"""Sanitized filesystem helpers for startup recovery boundaries."""
from __future__ import annotations

from pathlib import Path


def state_ref(root: Path, path: Path) -> str:
    """Return a state-root-relative ref without leaking absolute paths."""
    try:
        return Path(path).relative_to(root).as_posix()
    except ValueError:
        return Path(path).name


def safe_exists(root: Path, path: Path) -> tuple[bool, str | None]:
    try:
        return Path(path).exists(), None
    except OSError:
        return False, state_ref(root, path)


def safe_dirs(root: Path, directory: Path,
              pattern: str | None = None) -> tuple[list[Path], str | None]:
    """List child directories or return the denied boundary ref."""
    try:
        if not Path(directory).exists():
            return [], None
        items = directory.glob(pattern) if pattern else directory.iterdir()
        return sorted(path for path in items if path.is_dir()), None
    except OSError:
        return [], state_ref(root, directory)


def safe_files(root: Path, directory: Path,
               pattern: str) -> tuple[list[Path], str | None]:
    """List matching files or return the denied boundary ref."""
    try:
        if not Path(directory).exists():
            return [], None
        return sorted(Path(directory).glob(pattern)), None
    except OSError:
        return [], state_ref(root, directory)
