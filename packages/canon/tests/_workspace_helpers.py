"""Shared builders for the workspace-band tests: a fake repository on disk and
records built the way the CLI builds them."""
from __future__ import annotations

import hashlib
from pathlib import Path

from canon.schema import (
    KIND_ADR_DECISION,
    KIND_PERSONALITY_BLOCK,
    Provenance,
    Record,
)


def init_repo(path: Path, remote: str | None = None) -> Path:
    """A directory that looks like a git repository to the identity reader:
    a `.git` directory and, when `remote` is given, an origin in its config."""
    git = path / ".git"
    git.mkdir(parents=True)
    config = "[core]\n\trepositoryformatversion = 0\n"
    if remote is not None:
        config += f'[remote "origin"]\n\turl = {remote}\n'
    (git / "config").write_text(config, encoding="utf-8")
    return path


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def block(rid: str, body: str, ordinal: int = 1, scope: str = "workspace") -> Record:
    return Record(
        kind=KIND_PERSONALITY_BLOCK, id=rid, scope=scope,
        data={"title": rid.replace("-", " ").title(), "body": body},
        provenance=Provenance(harness="test", source_hash=_hash(body),
                              create_ord=ordinal))


def decision(rid: str, text: str, ordinal: int = 1, **extra) -> Record:
    data = {"title": f"Decision {rid}", "status": "accepted",
            "context": "Context for the test.", "decision": text, **extra}
    return Record(
        kind=KIND_ADR_DECISION, id=rid, scope="workspace", data=data,
        provenance=Provenance(harness="test", source_hash=_hash(text),
                              create_ord=ordinal))
