"""canon.context.purge over MCP: a call returns a plan, and only a second call
that carries the plan's digest deletes, on a server the owner started with
CANON_CONTEXT_MCP_PURGE=apply (test_context_mcp_egress.py covers the refusal).

An MCP result enters a model context and so reaches its provider, so neither
the plan nor the report carries record text or a file path: ids, roles, counts
and digests only.
"""
from __future__ import annotations

import json

import pytest

from canon.context_mcp import ENV_CONTEXT_DB, ENV_MCP_PURGE, handle
from canon.context_store import ContextStore

from ._context_fixtures import PROJECT, WORKSPACE, answer_payload, counts, prompt_payload, short_canary


def _call(name, arguments):
    reply = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": name, "arguments": arguments}})["result"]
    return reply["isError"], reply["content"][0]["text"]


def _purge(arguments):
    return _call("canon.context.purge", {"workspace_id": WORKSPACE, "project_id": PROJECT,
                                          **arguments})


@pytest.fixture()
def stored(tmp_path, monkeypatch):
    db = tmp_path / "context.sqlite"
    monkeypatch.setenv(ENV_CONTEXT_DB, str(db))
    monkeypatch.setenv(ENV_MCP_PURGE, "apply")
    canary = short_canary()
    payload = prompt_payload("turn-1", f"Prompt {canary}")
    payload["event"]["sources"].append({"source_id": "transcript_path",
                                        "source_kind": "transcript_locator",
                                        "locator": str(tmp_path / "private-project" / "t.jsonl"),
                                        "extraction_status": "locator_only_not_read"})
    store = ContextStore(db)
    prompt = store.ingest(payload)["event_record_id"]
    store.ingest(answer_payload(prompt, "turn-1", f"Answer {canary}"))
    return db, store, prompt, canary


def test_a_purge_call_without_a_digest_returns_a_plan_and_deletes_nothing(stored) -> None:
    db, _, prompt, _ = stored
    before = counts(db)

    is_error, text = _purge({"event_id": prompt})

    plan = json.loads(text)
    assert is_error is False
    assert plan["schema"] == "canon.context-purge-plan/v1"
    assert plan["counts"] == {"events": 1, "responses": 1, "derived": 2, "records": 4}
    assert plan["plan_sha256"].startswith("sha256:")
    assert counts(db) == before


def test_confirm_plan_sha256_applies_that_plan(stored) -> None:
    db, store, prompt, canary = stored
    plan = json.loads(_purge({"event_id": prompt})[1])

    is_error, text = _purge({"event_id": prompt, "confirm_plan_sha256": plan["plan_sha256"]})

    report = json.loads(text)
    assert is_error is False
    assert report["schema"] == "canon.context-purge-report/v1"
    assert report["records_purged"] == 4
    assert store.query(WORKSPACE, PROJECT, canary)["hits"] == []


def test_a_stale_digest_is_refused_over_mcp(stored) -> None:
    db, store, prompt, _ = stored
    plan = json.loads(_purge({"all": True})[1])
    store.ingest(prompt_payload("turn-2", "Captured between the plan and the confirmation"))
    before = counts(db)

    is_error, text = _purge({"all": True, "confirm_plan_sha256": plan["plan_sha256"]})

    assert is_error is True
    assert text == "context purge plan is stale; ask for a new plan"
    assert counts(db) == before


def test_the_plan_and_the_report_carry_no_text_or_paths(stored, tmp_path) -> None:
    _, _, prompt, canary = stored
    plan_text = _purge({"event_id": prompt})[1]
    digest = json.loads(plan_text)["plan_sha256"]
    report_text = _purge({"event_id": prompt, "confirm_plan_sha256": digest})[1]

    for text in (plan_text, report_text):
        assert canary not in text
        assert "private-project" not in text
        assert str(tmp_path) not in text and str(tmp_path).replace("\\", "\\\\") not in text


_ONE_SELECTOR = "choose exactly one of event_id, before_ord or all"


@pytest.mark.parametrize("arguments, message", [
    ({}, _ONE_SELECTOR),
    ({"event_id": "context-event-x", "all": True}, _ONE_SELECTOR),
    ({"all": False}, _ONE_SELECTOR),
    ({"before_ord": 0}, "before_ord must be a whole number of 1 or more"),
    ({"before_ord": True}, "before_ord must be a whole number of 1 or more"),
    ({"all": True, "keep_responses": "yes"}, "keep_responses must be true or false"),
])
def test_purge_arguments_need_exactly_one_selector(stored, arguments, message) -> None:
    db, _, _, _ = stored
    before = counts(db)

    is_error, text = _purge(arguments)

    assert (is_error, text) == (True, message)
    assert counts(db) == before


def test_an_unknown_event_is_reported_without_deleting(stored) -> None:
    db, _, _, _ = stored
    before = counts(db)

    is_error, text = _purge({"event_id": "context-event-" + "0" * 64})

    assert is_error is True
    assert text == "event_id is not a captured event in this workspace and project"
    assert counts(db) == before
