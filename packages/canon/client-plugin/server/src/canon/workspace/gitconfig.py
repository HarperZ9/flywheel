"""gitconfig.py -- what the identity reads from a repository's git directory.

No git command runs. The reader follows a worktree's or submodule's `.git`
file to its git directory and a worktree's `commondir` to the shared
directory, then reads the remote URLs and the `canon.project` setting from the
config file there. `include` directives and `insteadOf` rewrites are not
followed (a declared limit).

A repository with no remote is told apart from another repository created
later at the same path by a random nonce canon writes once into the shared git
directory (`canon-project-nonce`). The nonce travels with `.git`, so moving the
repository keeps its identity and a fresh `git init` gets a new one.
"""
from __future__ import annotations

import re
import secrets
from pathlib import Path

NONCE_FILE = "canon-project-nonce"
_SECTION_RE = re.compile(r'^\[\s*remote\s+"((?:[^"\\]|\\.)*)"\s*\]$')
_ANY_SECTION_RE = re.compile(r"^\[.*\]$")
_CANON_SECTION_RE = re.compile(r"^\[\s*canon\s*\]$", re.IGNORECASE)
_URL_RE = re.compile(r"^url\s*=\s*(.*)$", re.IGNORECASE)
_PROJECT_RE = re.compile(r"^project\s*=\s*(.*)$", re.IGNORECASE)


class GitConfigError(ValueError):
    """The repository's `.git` entry cannot be followed."""


def _git_dir(root: Path) -> Path:
    """The git directory for `root`: `.git` itself, or the directory a
    worktree's or submodule's `.git` file points at."""
    dot_git = root / ".git"
    if dot_git.is_dir():
        return dot_git
    text = dot_git.read_text(encoding="utf-8").strip()
    if not text.startswith("gitdir:"):
        raise GitConfigError("a .git file without a gitdir line")
    target = Path(text[len("gitdir:"):].strip())
    return target if target.is_absolute() else (root / target)


def _config_path(root: Path) -> Path:
    """A worktree keeps its remotes in the common directory named by its
    `commondir` file; a submodule and a plain repository keep them in the git
    directory itself."""
    git_dir = _git_dir(root)
    common = git_dir / "commondir"
    if common.is_file():
        rel = Path(common.read_text(encoding="utf-8").strip())
        git_dir = rel if rel.is_absolute() else (git_dir / rel)
    return git_dir / "config"


def common_git_dir(root: Path) -> Path | None:
    """The git directory the repository at `root` shares with its worktrees
    (a worktree's common directory, else its own git directory), resolved.
    None when `root` has no `.git` entry or it cannot be followed. Two
    checkouts with the same common directory are one repository."""
    if not (root / ".git").exists():
        return None
    try:
        return _config_path(root).parent.resolve()
    except (OSError, GitConfigError):
        return None


def parse_remotes(config_text: str) -> dict[str, str]:
    """Remote name to URL from a git config file's text. The first `url` in a
    remote section wins. `include` directives and `insteadOf` rewrites are not
    followed (a declared limit)."""
    remotes: dict[str, str] = {}
    current: str | None = None
    for raw in config_text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        section = _SECTION_RE.match(line)
        if section:
            current = section.group(1)
            continue
        if _ANY_SECTION_RE.match(line):
            current = None
            continue
        match = _URL_RE.match(line)
        if current is not None and match and current not in remotes:
            remotes[current] = _unquote_value(match.group(1))
    return remotes


def _unquote_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    for marker in (" #", " ;", "\t#", "\t;"):
        if marker in value:
            value = value.split(marker, 1)[0]
    return value.strip()


def read_remote_url(root: Path) -> str | None:
    """The chosen remote's URL for the repository at `root`, or None."""
    text = _config_text(root)
    if text is None:
        return None
    remotes = parse_remotes(text)
    if not remotes:
        return None
    name = "origin" if "origin" in remotes else sorted(remotes)[0]
    return remotes[name]


def _config_text(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    config = _config_path(root)
    return config.read_text(encoding="utf-8") if config.is_file() else None


def read_project_name(root: Path) -> str | None:
    """The `canon.project` value from the repository config, or None. It names
    the project explicitly, so two checkouts that share a remote but are
    different projects (clones of one starter template) can be split."""
    text = _config_text(root)
    if text is None:
        return None
    in_canon, name = False, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if _ANY_SECTION_RE.match(line):
            in_canon = _CANON_SECTION_RE.match(line) is not None
            continue
        match = _PROJECT_RE.match(line)
        if in_canon and match and name is None:
            name = _unquote_value(match.group(1)) or None
    return name


def project_nonce(root: Path, *, create: bool = True) -> str | None:
    """The repository's canon nonce, written on first use into the shared git
    directory. None when there is no git directory, it cannot be written, or
    `create` is False and no nonce exists yet."""
    if not (root / ".git").exists():
        return None
    try:
        path = _config_path(root).parent / NONCE_FILE
        if not path.is_file():
            if not create:
                return None
            try:
                with open(path, "x", encoding="utf-8", newline="\n") as handle:
                    handle.write(secrets.token_hex(16) + "\n")
            except FileExistsError:
                pass
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, GitConfigError):
        return None
    return value or None
