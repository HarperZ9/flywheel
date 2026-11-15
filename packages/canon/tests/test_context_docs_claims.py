"""The purge and capture docs claim no more than the code does.

Each forbidden phrase is a claim the review found the code did not back; each
required phrase is the limit the docs now state in its place. The check reads
the words, not their truth: the behaviour behind each limit has its own test.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from canon.context_mcp import tools

ROOT = Path(__file__).resolve().parents[1]
_FORBIDDEN = [
    ("README.md", "proven by a full test suite"),
    ("docs/shared-context.md", "Each record canon 0.4.0 writes"),
    ("docs/shared-context.md", "the owner started"),
    ("docs/shared-context.md", "take the access rules of their folder"),
    ("docs/client-capture.md", "take the access rules of the"),
    ("docs/shared-context.md", "SQLite rewrites the file without"),
]
_REQUIRED = [
    ("docs/shared-context.md", "leaves your machine"),
    ("docs/shared-context.md", "umask 077"),
    ("docs/client-capture.md", "umask 077"),
    ("docs/client-capture.md", "`last_assistant_message`"),
    ("docs/client-capture.md", "transcript paths are not listed"),
    ("docs/shared-context.md", "`canon.context.ingest` redacts"),
    ("README.md", "synthetic"),
]


def _text(name: str) -> str:
    return " ".join((ROOT / name).read_text(encoding="utf-8").split())


@pytest.mark.parametrize("name, phrase", _FORBIDDEN)
def test_a_claim_the_code_does_not_back_is_gone(name, phrase) -> None:
    assert phrase not in _text(name)


@pytest.mark.parametrize("name, phrase", _REQUIRED)
def test_the_stated_limit_is_present(name, phrase) -> None:
    assert phrase in _text(name)


def test_the_purge_tool_description_claims_no_owner_check() -> None:
    [purge] = [tool for tool in tools() if tool["name"] == "canon.context.purge"]

    assert "owner started" not in purge["description"]
    assert "CANON_CONTEXT_MCP_PURGE=apply" in purge["description"]


@pytest.mark.parametrize("client", ["claude-code", "codex"])
def test_the_stop_fragments_name_the_version_they_need(client) -> None:
    path = ROOT / "examples" / "shared-context-hooks" / f"{client}-stop.fragment.json"
    note = json.loads(path.read_text(encoding="utf-8"))["merge_note"]

    assert "canon 0.4.0" in note
