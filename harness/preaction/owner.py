"""owner.py -- the owner's configuration for the monitor, loaded on every attach point.

One JSON file the owner writes, outside the agent's workspace:
`<FLYWHEEL_HOME>/preaction/owner.json` by default (FLYWHEEL_HOME defaults to
~/.flywheel, which rule monitor-tamper/001 already covers). It sets the hosts
the owner allows for any call, the hosts the owner owns, the documentation
hosts a read-only fetch may reach without a hold, canaries, extra protected
paths, the monitor settings, an optional expected rule-pack digest, and the
witness directory where chain heads are exported.

With no file, a shipped list of documentation hosts applies to read-only
fetches only (fetch.py), so reading docs is not held by default. Uploads,
shell pipelines, long query strings and every other host still hold under
egress/002. A file that exists but does not parse, names an unknown field, or
lists a wildcard host is an error: the hook fails closed on it.

The effective config has one digest. When the owner file exists, the digest
joins the monitor config digest, so a pinned monitor blocks every call after
an unpinned edit of the owner file.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from .config import MonitorConfig
from .contract import RunContext, canonical_json, sha256_hex

SCHEMA = "flywheel.preaction-owner/v1"
DEFAULT_FETCH_HOSTS = (
    "docs.python.org", "peps.python.org", "packaging.python.org", "pypi.org",
    "docs.pytest.org", "developer.mozilla.org", "nodejs.org", "docs.npmjs.com",
    "www.npmjs.com", "doc.rust-lang.org", "docs.rs", "crates.io", "go.dev", "pkg.go.dev",
    "learn.microsoft.com", "docs.github.com", "git-scm.com", "man7.org",
    "en.cppreference.com", "docs.docker.com", "kubernetes.io", "www.postgresql.org",
    "www.sqlite.org", "www.typescriptlang.org", "react.dev", "stackoverflow.com",
)
_KEYS = {"schema", "allow_hosts", "owned_hosts", "fetch_hosts", "use_default_fetch_hosts",
         "canaries", "protected_paths", "monitor", "expected_rules_digest", "witness_dir",
         "head_export_every"}
_HOST = re.compile(r"^[a-z0-9.-]+$|^\[[0-9a-f:]+\]$|^[0-9a-f:]+$")


class OwnerConfigError(ValueError):
    """The owner file exists but cannot be used; the monitor fails closed."""


def default_path(environ=None) -> Path:
    env = os.environ if environ is None else environ
    root = env.get("FLYWHEEL_HOME") or str(Path.home() / ".flywheel")
    return Path(os.path.expanduser(root)) / "preaction" / "owner.json"


def _hosts(raw, key: str) -> tuple:
    if not isinstance(raw, list):
        raise OwnerConfigError(f"{key} must be a list of host names")
    out = []
    for h in raw:
        h = str(h).strip().lower()
        if not h or "*" in h or "/" in h or not _HOST.match(h):
            raise OwnerConfigError(f"{key}: {h!r} is not an exact host name")
        out.append(h)
    return tuple(sorted(set(out)))


def _strings(raw, key: str) -> tuple:
    if not isinstance(raw, list) or not all(isinstance(x, str) and x for x in raw):
        raise OwnerConfigError(f"{key} must be a list of non-empty strings")
    return tuple(raw)


@dataclass
class OwnerConfig:
    allow_hosts: tuple = ()
    owned_hosts: tuple = ()
    fetch_hosts: tuple = DEFAULT_FETCH_HOSTS
    canaries: tuple = ()
    protected_paths: tuple = ()
    monitor: dict = field(default_factory=dict)
    expected_rules_digest: str = ""
    witness_dir: str = ""
    head_export_every: int = 25
    source: str = "default"          # "default" (no file) or "file"
    path: str = ""

    def effective(self) -> dict:
        return {"schema": SCHEMA, "allow_hosts": list(self.allow_hosts),
                "owned_hosts": list(self.owned_hosts), "fetch_hosts": list(self.fetch_hosts),
                "canaries": list(self.canaries), "protected_paths": list(self.protected_paths),
                "monitor": self.monitor, "expected_rules_digest": self.expected_rules_digest,
                "witness_dir": self.witness_dir, "head_export_every": self.head_export_every}

    def digest(self) -> str:
        return sha256_hex(canonical_json(self.effective()))

    def monitor_config(self) -> MonitorConfig:
        cfg = MonitorConfig.from_dict(self.monitor or {})
        if self.source == "file":
            cfg.owner_sha256 = self.digest()
        return cfg

    def apply(self, ctx: RunContext) -> RunContext:
        """The run context with the owner's hosts, canaries and protected paths."""
        return replace(
            ctx, allow_hosts=tuple(sorted(set(ctx.allow_hosts) | set(self.allow_hosts))),
            owned_hosts=tuple(sorted(set(ctx.owned_hosts) | set(self.owned_hosts))),
            fetch_hosts=tuple(sorted(set(ctx.fetch_hosts) | set(self.fetch_hosts))),
            canaries=tuple(ctx.canaries) + tuple(c for c in self.canaries if c not in ctx.canaries),
            protected_paths=tuple(ctx.protected_paths) + tuple(
                p for p in self.protected_paths if p not in ctx.protected_paths))


def from_dict(d: dict, *, path: str = "") -> OwnerConfig:
    if not isinstance(d, dict):
        raise OwnerConfigError("owner config must be a JSON object")
    unknown = set(d) - _KEYS
    if unknown:
        raise OwnerConfigError(f"unknown owner config fields: {sorted(unknown)}")
    if d.get("schema", SCHEMA) != SCHEMA:
        raise OwnerConfigError(f"schema must be {SCHEMA}")
    fetch = _hosts(d.get("fetch_hosts", []), "fetch_hosts")
    if d.get("use_default_fetch_hosts", True):
        fetch = tuple(sorted(set(fetch) | set(DEFAULT_FETCH_HOSTS)))
    monitor = d.get("monitor", {})
    if not isinstance(monitor, dict):
        raise OwnerConfigError("monitor must be an object")
    MonitorConfig.from_dict(monitor)      # validate early; raises on bad fields
    every = int(d.get("head_export_every", 25))
    if every < 1:
        raise OwnerConfigError("head_export_every must be at least 1")
    return OwnerConfig(
        allow_hosts=_hosts(d.get("allow_hosts", []), "allow_hosts"),
        owned_hosts=_hosts(d.get("owned_hosts", []), "owned_hosts"),
        fetch_hosts=fetch, canaries=_strings(d.get("canaries", []), "canaries"),
        protected_paths=_strings(d.get("protected_paths", []), "protected_paths"),
        monitor=monitor, expected_rules_digest=str(d.get("expected_rules_digest", "")),
        witness_dir=str(d.get("witness_dir", "")), head_export_every=every,
        source="file", path=path)


def load(path=None, environ=None) -> OwnerConfig:
    """The owner config at `path` (default: default_path()). Missing file:
    the shipped defaults. Present but unusable: OwnerConfigError."""
    p = Path(path) if path else default_path(environ)
    if not p.exists():
        return OwnerConfig(path=str(p))
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise OwnerConfigError(f"owner config {p} unreadable: {type(exc).__name__}") from exc
    try:
        return from_dict(data, path=str(p))
    except (TypeError, ValueError) as exc:
        if isinstance(exc, OwnerConfigError):
            raise
        raise OwnerConfigError(f"owner config {p}: {exc}") from exc
