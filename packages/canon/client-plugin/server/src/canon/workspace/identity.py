"""identity.py -- a stable identity for the project a record belongs to.

A developer who moves one repository between Claude Code, Codex, Cursor and a
local model wants every tool to see that repository's records and no other
repository's. The store keys everything on a project id, so the id has to be
stable across the things that do not change the project (a second clone, a new
working directory, a different tool) and different across the things that do.

Derivation, in order:

  1. The repository root is the nearest directory at or above the workspace that
     holds a `.git` entry (a directory, or the file a worktree or submodule
     carries). A workspace with no `.git` above it is its own root.
  2. A `canon.project` name in the repository's git config names the project
     explicitly and wins over the remote. It splits two checkouts that share a
     remote but are different projects (two apps cloned from one starter).
  3. With a remote, the id is derived from the normalized remote URL alone:
     scheme, credentials, query and a trailing `.git` are dropped, the host is
     lowercased, and a port is dropped only when it is the scheme's default.
     Two clones of one repository share an id wherever they sit on disk. The
     remote is `origin` when present, else the first remote by name, so the
     choice does not depend on file order.
  4. With no remote, a repository is keyed on a random nonce canon writes once
     into its shared git directory, so moving it keeps its id and a new `git
     init` at a reused path is a new project. A directory with no git directory,
     or one canon cannot write, is keyed on its resolved path.

A merge the rules cannot see (two apps started from one starter repository keep
its remote) is announced rather than silent: the store records a digest of each
checkout root that used the project, and a command run from a new one says so.

The path of a case-sensitive repository host is kept as written. Two remotes
that differ only by path case therefore get two ids. That split is deliberate:
when in doubt the derivation separates two projects rather than merging them,
because a merge shows one project's records to another and a split only hides
records until they are adopted explicitly.

The id is a digest, so nothing in it names a local path, a user name or a
credential. `label` is the human name shown in a brief: the normalized remote,
or the root directory's name for the path method.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from canon.versions import PIN_PROJECT_ID
from canon.workspace.gitconfig import (  # noqa: F401  (parse_remotes re-exported)
    GitConfigError,
    parse_remotes,
    project_nonce,
    read_project_name,
    read_remote_url,
)

ID_SCHEMA = PIN_PROJECT_ID.kind_tag
METHOD_REMOTE = "remote"
METHOD_PATH = "path"
METHOD_CONFIG = "config"
_DEFAULT_PORTS = {"ssh": 22, "git+ssh": 22, "ssh+git": 22, "http": 80, "https": 443,
                  "git": 9418}
_ID_PREFIX = "prj_"
PROJECT_ID_RE = re.compile(r"^prj_[0-9a-f]{32}$")

_SCP_RE = re.compile(r"^(?:[^@/\s]+@)?([^:/\s]+):(?!//)(.+)$")


class ProjectIdentityError(ValueError):
    """The workspace cannot be given a project identity: it is not a
    directory, or its remote URL cannot be normalized."""


@dataclass(frozen=True, slots=True)
class ProjectIdentity:
    """One project. `project_id` is the storage key; `method` says how it was
    derived; `key` is the derivation input with no local path in it (the
    normalized remote, or `path-sha256:<digest>`); `label` is the display name.
    `root` is the local repository root and is never written to a receipt."""

    project_id: str
    method: str
    key: str
    label: str
    root: Path

    @property
    def checkout(self) -> str:
        """A path-clean digest of this checkout's root, so the store can tell a
        second checkout of the project from the first without naming a path."""
        return _sha256(os.path.normcase(str(self.root)))[:16]

    def to_public(self) -> dict:
        """The path-clean form a receipt or a brief may carry."""
        return {"project_id": self.project_id, "method": self.method,
                "key": self.key, "label": self.label, "schema": ID_SCHEMA}


def is_project_id(value: object) -> bool:
    return isinstance(value, str) and PROJECT_ID_RE.match(value) is not None


def _home() -> Path | None:
    """The resolved home directory, or None where the platform has none (a
    minimal container with no HOME and no password entry). Without a home
    there is no home ceiling; the filesystem-root ceiling still applies."""
    try:
        return Path.home().resolve()
    except (RuntimeError, KeyError, OSError):
        return None


def default_ceilings(start: Path | None = None) -> frozenset[Path]:
    """Directories whose `.git` never claims a workspace below them: the home
    directory (a dotfiles repository often lives there) and the filesystem root
    of both the home directory and the workspace."""
    ceilings: set[Path] = set()
    home = _home()
    if home is not None:
        ceilings.update({home, Path(home.anchor)})
    if start is not None and start.anchor:
        ceilings.add(Path(start.anchor))
    return frozenset(ceilings)


def find_repo_root(start: Path, *,
                   ceilings: frozenset[Path] | None = None) -> Path | None:
    """The nearest directory at or above `start` holding a `.git` entry.

    A `.git` in a ceiling directory (home, a drive root) counts only when
    `start` is that directory. Without this rule a dotfiles repository in the
    home directory would give every unversioned project below it one shared
    identity, which is the cross-project mixing this module exists to prevent.
    """
    stops = default_ceilings(start) if ceilings is None else ceilings
    current = start
    while True:
        if (current / ".git").exists():
            if current != start and current in stops:
                return None
            return current
        if current.parent == current:
            return None
        current = current.parent


def normalize_remote(url: str, *, root: Path | None = None) -> str:
    """The comparison form of a remote URL: `host/path` for a network remote,
    `local:<path>` for a path remote. Credentials never survive."""
    text = url.strip() if isinstance(url, str) else ""
    if not text:
        raise ProjectIdentityError("empty remote URL")
    if "://" in text:
        return _normalize_scheme_url(text)
    scp = _SCP_RE.match(text)
    if scp and len(scp.group(1)) > 1:
        return _join_host_path(scp.group(1), scp.group(2))
    return _normalize_local(text, root)


def _normalize_scheme_url(text: str) -> str:
    parts = urlsplit(text)
    if parts.scheme.lower() == "file":
        return _normalize_local(parts.path, None)
    host = parts.hostname
    if not host:
        raise ProjectIdentityError("remote URL has no host")
    try:
        port = parts.port
    except ValueError as exc:
        raise ProjectIdentityError("remote URL has an invalid port") from exc
    if port is not None and port != _DEFAULT_PORTS.get(parts.scheme.lower()):
        # Two servers on one host are two projects; a doubt splits.
        host = f"{host}:{port}"
    return _join_host_path(host, parts.path)


def _join_host_path(host: str, path: str) -> str:
    clean = re.sub(r"/+", "/", path.strip().strip("/"))
    if clean.endswith(".git"):
        clean = clean[: -len(".git")].rstrip("/")
    if not clean:
        raise ProjectIdentityError("remote URL has no repository path")
    return f"{host.lower()}/{clean}"


def _normalize_local(path: str, root: Path | None) -> str:
    candidate = Path(path)
    if not candidate.is_absolute() and root is not None:
        candidate = root / candidate
    resolved = os.path.normcase(os.path.normpath(str(candidate)))
    return "local:" + resolved.replace("\\", "/")


def _digest_id(method: str, key: str) -> str:
    payload = f"{ID_SCHEMA}\n{method}\n{key}".encode("utf-8")
    return _ID_PREFIX + hashlib.sha256(payload).hexdigest()[:32]


def derive_identity(workspace: str | Path, *, remote_url: str | None = None,
                    ceilings: frozenset[Path] | None = None,
                    write_nonce: bool = True) -> ProjectIdentity:
    """Derive the identity of the project containing `workspace`. Pass
    `remote_url` to override the remote read from the git config, and
    `write_nonce=False` to derive another repository's identity without
    writing its nonce (it then falls back to its path key)."""
    start = Path(workspace).resolve()
    if not start.is_dir():
        raise ProjectIdentityError("workspace is not a directory")
    root = find_repo_root(start, ceilings=ceilings) or start
    try:
        name = None if remote_url is not None else read_project_name(root)
        url = remote_url if remote_url is not None else read_remote_url(root)
    except GitConfigError as exc:
        raise ProjectIdentityError(str(exc)) from exc
    method, key, label = _derive_key(root, name, url, write_nonce)
    return ProjectIdentity(_digest_id(method, key), method, key, label, root)


def _derive_key(root: Path, name: str | None, url: str | None,
                write_nonce: bool) -> tuple[str, str, str]:
    if name:
        return METHOD_CONFIG, "project:" + name, name
    label = root.name or "project"
    if url:
        key = normalize_remote(url, root=root)
        if key.startswith("local:"):
            # A path remote names a local directory; keep the path out of the key.
            return METHOD_REMOTE, "local-sha256:" + _sha256(key), label
        return METHOD_REMOTE, key, key
    nonce = project_nonce(root, create=write_nonce)
    if nonce:
        return METHOD_PATH, "nonce-sha256:" + _sha256(nonce), label
    return METHOD_PATH, "path-sha256:" + _sha256(os.path.normcase(str(root))), label


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
