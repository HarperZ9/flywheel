"""What the canon-context MCP server hands to a model, and what it will not do.

A purge over MCP returns a plan. Applying it needs the owner to start the
server with `CANON_CONTEXT_MCP_PURGE=apply`, since an agent holding the tool
could otherwise send back the digest it was just given. Query excerpts and
get results pass through the secret scrubber. Health reports whether the
database file is shared with other accounts, where canon can check.
"""
from __future__ import annotations

import json
import os
import secrets
import stat as stat_module
from types import SimpleNamespace

import pytest

from canon.context_access import file_access
from canon.context_mcp import ENV_CONTEXT_DB, ENV_MCP_PURGE, handle
from canon.context_store import ContextStore

from ._context_fixtures import PROJECT, WORKSPACE, counts, prompt_payload


def _call(name, arguments):
    reply = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": name, "arguments": arguments}})["result"]
    return reply["isError"], reply["content"][0]["text"]


@pytest.fixture()
def stored(tmp_path, monkeypatch):
    db = tmp_path / "context.sqlite"
    monkeypatch.setenv(ENV_CONTEXT_DB, str(db))
    monkeypatch.delenv(ENV_MCP_PURGE, raising=False)
    fake = "sk-FAKE" + secrets.token_hex(20)
    store = ContextStore(db)
    record = store.ingest(prompt_payload("turn-1", f"The harbor token is {fake} today"))
    return db, record["event_record_id"], fake


def _purge(arguments):
    return _call("canon.context.purge", {"workspace_id": WORKSPACE, "project_id": PROJECT,
                                          **arguments})


def test_an_mcp_purge_is_plan_only_unless_the_owner_started_the_server_to_apply(
        stored, monkeypatch) -> None:
    db, prompt, _ = stored
    plan = json.loads(_purge({"event_id": prompt})[1])
    before = counts(db)

    is_error, text = _purge({"event_id": prompt, "confirm_plan_sha256": plan["plan_sha256"]})

    assert is_error is True and ENV_MCP_PURGE in text
    assert counts(db) == before
    assert plan["presence"] == "none"

    monkeypatch.setenv(ENV_MCP_PURGE, "apply")
    is_error, text = _purge({"event_id": prompt, "confirm_plan_sha256": plan["plan_sha256"]})
    assert is_error is False and json.loads(text)["records_purged"] == 3


def test_query_excerpts_and_get_results_are_scrubbed(stored) -> None:
    _, prompt, fake = stored

    _, query = _call("canon.context.query", {"workspace_id": WORKSPACE, "project_id": PROJECT,
                                              "query": "harbor token"})
    _, got = _call("canon.context.get", {"workspace_id": WORKSPACE, "project_id": PROJECT,
                                          "record_id": prompt})

    assert json.loads(query)["hits"]
    for text in (query, got):
        assert fake not in text and "[REDACTED:" in text


def test_health_reports_file_access(stored) -> None:
    _, text = _call("canon.context.health", {})

    health = json.loads(text)
    expected = "not_checked" if os.name == "nt" else health["file_access"]
    assert health["file_access"] == expected
    assert health["file_access"] in ("owner_only", "shared", "not_checked")


def _fake_stat(modes):
    return lambda path: SimpleNamespace(st_mode=modes[str(path)])


@pytest.mark.parametrize("file_mode, dir_mode, expected", [
    (0o600, 0o700, "owner_only"),
    (0o644, 0o700, "shared"),
    (0o600, 0o777, "shared"),
    (0o600, 0o755, "owner_only"),
])
def test_file_access_reads_the_mode_bits_on_posix(tmp_path, file_mode, dir_mode,
                                                   expected) -> None:
    db = tmp_path / "context.sqlite"
    modes = {str(db): stat_module.S_IFREG | file_mode,
             str(db.parent): stat_module.S_IFDIR | dir_mode}

    assert file_access(db, platform="posix", stat=_fake_stat(modes)) == expected
    assert file_access(db, platform="nt", stat=_fake_stat(modes)) == "not_checked"
