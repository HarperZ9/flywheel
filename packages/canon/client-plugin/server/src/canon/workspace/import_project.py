"""import_project.py -- does a session belong to this project, and which of its
files are this project's.

The source names its repository (Codex `git.repository_url`) or its working
directories (`cwd`). A repository URL is compared with this project's key,
except that a URL naming this checkout's own remote, under a `--remote`
override that names another repository, defers to the working directory:
Codex records the checkout's own origin, not the override. A working
directory is first resolved to the checkout it sits in: the nearest
directory with a `.git` entry, or this project's root when the directory is
inside a project folder that has no `.git` at all. A checkout of this
project's own repository (its root, or a sibling worktree that shares its git
directory) is this project, and that holds under a `--remote` override too,
because the override names that repository. Any other checkout is compared by
identity, derived without the override and without writing anything, so a
nested repository or a submodule sits inside the root but is its own project,
and a nested repository with no remote gets no nonce from an import. A working
directory that no longer exists falls back to containment, and a `.git` entry
between it and the root makes it another project.
"""
from __future__ import annotations

import os
from pathlib import Path

from canon.workspace.gitconfig import GitConfigError, common_git_dir, read_remote_url
from canon.workspace.identity import (
    METHOD_REMOTE,
    ProjectIdentity,
    ProjectIdentityError,
    derive_identity,
    find_repo_root,
    normalize_remote,
)


def _norm(path: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("\\/") + os.sep)


def _nested_repo_between(path: str, root: str) -> bool:
    """True when a directory strictly between `path` and `root` (or `path`
    itself) holds a `.git` entry, so the path belongs to another repository."""
    current = Path(path)
    root_path = Path(root)
    while _norm(current) != _norm(root_path) and current.parent != current:
        if (current / ".git").exists():
            return True
        current = current.parent
    return False


def _checkout_root(directory: Path, identity: ProjectIdentity) -> Path:
    """The root of the checkout `directory` sits in: the nearest directory with
    a `.git` entry, else this project's root when `directory` is inside a
    project folder with no `.git`, else `directory` itself."""
    found = find_repo_root(directory)
    if found is not None:
        return found
    root = Path(identity.root)
    if not (root / ".git").exists() and _inside(_norm(directory), _norm(root)):
        return root
    return directory


def _same_repository(checkout: Path, root: Path) -> bool:
    """True for this project's root, and for a sibling worktree that shares
    its git directory."""
    if _norm(checkout) == _norm(root):
        return True
    mine, theirs = common_git_dir(root), common_git_dir(checkout)
    return mine is not None and theirs is not None and _norm(mine) == _norm(theirs)


def _cwd_status(cwd: str, identity: ProjectIdentity) -> str:
    if os.path.isdir(cwd):
        checkout = _checkout_root(Path(cwd).resolve(), identity)
        if _same_repository(checkout, Path(identity.root)):
            return "match"
        try:
            other = derive_identity(checkout, write_nonce=False)
        except ProjectIdentityError:
            return "mismatch"
        return "match" if other.project_id == identity.project_id else "mismatch"
    root = _norm(identity.root)
    target = _norm(cwd)
    if _inside(target, root) and not _nested_repo_between(target, root):
        return "match"
    return "mismatch"


def _own_remote_key(identity: ProjectIdentity) -> str | None:
    """The normalized remote this checkout's own git config names, which is
    what Codex records even when `--remote` names another repository."""
    try:
        url = read_remote_url(Path(identity.root))
        return normalize_remote(url) if url else None
    except (GitConfigError, ProjectIdentityError):
        return None


def project_check(identity: ProjectIdentity, extraction) -> dict:
    """Whether the source says it belongs to this project. The report names
    the check and never a local path. A repository URL that names this
    checkout's own remote, under a `--remote` override that names another,
    defers to the working directory check."""
    url = extraction.repository_url
    if url and identity.method == METHOD_REMOTE:
        try:
            key = normalize_remote(url)
        except ProjectIdentityError:
            key = None
        own = bool(key and key != identity.key and extraction.cwds
                   and key == _own_remote_key(identity))
        if key and not key.startswith("local:") and not own:
            status = "match" if key == identity.key else "mismatch"
            return {"status": status, "by": "repository_url", "source_key": key}
    if extraction.cwds:
        statuses = {_cwd_status(c, identity) for c in extraction.cwds}
        status = "mismatch" if "mismatch" in statuses else "match"
        return {"status": status, "by": "working_directory"}
    return {"status": "unverified", "by": "none"}


def relative_area(path: str, identity: ProjectIdentity) -> str | None:
    """A file path as a path inside the project, or None when it is outside
    the root or inside a nested repository under it."""
    root = _norm(identity.root)
    target = os.path.normpath(path if os.path.isabs(path) else os.path.join(root, path))
    normal = os.path.normcase(target)
    if not _inside(normal, root) or normal == root:
        return None
    if _nested_repo_between(os.path.dirname(normal), root):
        return None
    return os.path.relpath(target, str(identity.root)).replace("\\", "/")
