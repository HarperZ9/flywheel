"""Shared helpers for the MCP door tests.

The door has two test modules: the protocol and read surface in
test_local_mcp.py, and the aggregate check in test_mcp_check.py. Both build
records and call tools the same way, so the construction lives here rather than
twice.

`_clean_env` is autouse. Import it into a module that needs it; the import looks
unused and is not, because pytest collects a fixture from the module namespace
it is bound in.
"""
from __future__ import annotations

import json

import pytest

from canon import local_mcp
from canon.blocks import ENV_BLOCKS_DIR
from canon.local_mcp import ENV_HOME, ENV_WORKSPACE
from canon.schema import (
    KIND_EPISODIC_MEMORY,
    KIND_PERSONALITY_BLOCK,
    Provenance,
    Record,
    Temporal,
)

TOOL_NAMES = ["canon.status", "canon.doctor", "canon.blocks", "canon.render",
              "canon.validate", "canon.check"]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """No test reads the developer's own canon configuration."""
    for name in (ENV_BLOCKS_DIR, ENV_HOME, ENV_WORKSPACE):
        monkeypatch.delenv(name, raising=False)


def _block(id_: str, *, scope: str = "global", ord_: int = 1) -> Record:
    return Record(
        kind=KIND_PERSONALITY_BLOCK, id=id_, scope=scope,
        data={"title": id_.title(), "body": "body text"},
        provenance=Provenance(harness="author", source_hash="a" * 64, create_ord=ord_),
        temporal=Temporal(valid_until=None, supersedes=None))


def _memory(id_: str) -> Record:
    return Record(
        kind=KIND_EPISODIC_MEMORY, id=id_, scope="global",
        data={"layer": "L0", "text": "t", "source_ids": []},
        provenance=Provenance(harness="mneme", source_hash="b" * 64, create_ord=9),
        temporal=Temporal(valid_until=None, supersedes=None))


def _seed(tmp_path, *records, name_prefix="rec"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    for i, rec in enumerate(records):
        path = tmp_path / f"{name_prefix}{i}.json"
        path.write_text(json.dumps(rec.to_dict()), encoding="utf-8")
    return tmp_path


def _call(name: str, args: dict | None = None) -> dict:
    return local_mcp._call({"name": name, "arguments": args or {}})


def _payload(result: dict):
    return json.loads(result["content"][0]["text"])


def _tool(name: str, args: dict | None = None):
    return _payload(_call(name, args))
