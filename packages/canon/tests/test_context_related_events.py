from __future__ import annotations

import json

from canon.context_mcp import ENV_CONTEXT_DB, handle
from canon.context_store import ContextStore

WORKSPACE = "cdev"
PROJECT = "canon"


def _event(event_id: str, text: str, *, workspace: str = WORKSPACE,
           project: str = PROJECT, sources: list[dict] | None = None,
           extractions: list[dict] | None = None) -> dict:
    return {
        "workspace_id": workspace,
        "project_id": project,
        "event": {
            "event_id": event_id,
            "source_app": "codex",
            "native_id": event_id,
            "session_id": "related-events-fixture",
            "message_text": text,
            "sources": sources or [{
                "source_id": "message",
                "source_kind": "prompt",
                "locator": f"turn:{event_id}",
                "extraction_status": "completed",
            }],
            "extractions": extractions or [],
        },
    }


def _source_ref(anchor: str, *, source_id: str = "prior") -> dict:
    return {
        "source_id": source_id,
        "source_kind": "canon_event_ref",
        "ref": anchor,
        "extraction_status": "completed",
    }


def _store(tmp_path) -> ContextStore:
    return ContextStore(tmp_path / "context.sqlite")


def _ingest(store: ContextStore, event_id: str, text: str, **kwargs) -> str:
    return store.ingest(_event(event_id, text, **kwargs))["event_record_id"]


def _related_ids(result: dict) -> list[str]:
    return [row["event_record_id"] for row in result["related_events"]]


def test_related_events_are_opt_in_and_do_not_reorder_primary_hits(tmp_path) -> None:
    store = _store(tmp_path)
    old = _ingest(store, "saved-policy-v1", "saved-policy-v1 exact identifier old version")
    final = _ingest(store, "final-review", "final review corrects saved policy", sources=[_source_ref(old)])
    _ingest(store, "unrelated-newest-final", "newest final policy document without a source edge")

    default = store.query(WORKSPACE, PROJECT, "saved-policy-v1", top_k=4, include_pending=False)
    expanded = store.query(WORKSPACE, PROJECT, "saved-policy-v1", top_k=4, include_pending=False,
                           include_related=True)

    assert "related_events" not in default
    assert expanded["hits"] == default["hits"]
    assert _related_ids(expanded) == [final]
    assert expanded["related_events"][0]["direction"] == "incoming_source_ref"
    assert expanded["related_events"][0]["anchor_event_record_id"] == old
    assert expanded["related_events"][0]["source"]["source_kind"] == "canon_event_ref"
    assert expanded["coverage"]["related_events_returned"] == 1
    assert expanded["coverage"]["related_event_currentness"] == "not_inferred"
    assert expanded["coverage"]["related_event_truth"] == "not_inferred"


def test_related_events_preserve_contradictory_history_without_status_claims(tmp_path) -> None:
    store = _store(tmp_path)
    anchor = _ingest(store, "routing-plan", "routing-plan-v1 accepted scorecard baseline")
    go = _ingest(store, "later-go-review", "later GO review for routing-plan-v1", sources=[_source_ref(anchor)])
    hold = _ingest(store, "later-hold-review", "later HOLD contradictory review for routing-plan-v1",
                   sources=[_source_ref(anchor, source_id="contradicts")])

    result = store.query(WORKSPACE, PROJECT, "accepted scorecard baseline", top_k=1, include_pending=False,
                         include_related=True, related_limit=5)

    assert set(_related_ids(result)) == {go, hold}
    assert {row["direction"] for row in result["related_events"]} == {"incoming_source_ref"}
    assert all("current" not in row for row in result["related_events"])
    assert all("supersedes" not in row for row in result["related_events"])
    assert "related source references do not prove truth, currentness, or supersession" in result["does_not_prove"]


def test_outgoing_related_event_uses_only_explicit_canon_event_refs(tmp_path) -> None:
    store = _store(tmp_path)
    source = _ingest(store, "primary-source", "primary-source-1 source receipt")
    other = _ingest(store, "related-target", "related-target-1 independent receipt")
    referrer = _ingest(store, "mentions-outgoing", "outgoing-check token mentions source receipt",
                       sources=[_source_ref(other, source_id="supports")])
    _ingest(store, "plain-text-injection", "outgoing-check token embeds an id as plain text", sources=[{
        "source_id": "not-a-canon-ref",
        "source_kind": "transcript_locator",
        "ref": source,
        "extraction_status": "completed",
    }])

    result = store.query(WORKSPACE, PROJECT, "outgoing-check", top_k=1, include_pending=False,
                         include_related=True, related_limit=5)

    assert result["hits"][0]["citation"]["event_record_id"] == referrer
    assert _related_ids(result) == [other]
    assert result["related_events"][0]["direction"] == "outgoing_source_ref"


def test_related_events_deduplicate_derived_hits_for_same_anchor(tmp_path) -> None:
    store = _store(tmp_path)
    repeated = "duplicate-anchor term appears in event and extraction"
    anchor = _ingest(store, "duplicate-anchor", repeated, extractions=[{
        "source_id": "message",
        "text": repeated,
        "claim_state": "reported_by_source",
        "extraction_status": "completed",
    }])
    related = _ingest(store, "dedup-related", "dedup related review", sources=[_source_ref(anchor)])

    result = store.query(WORKSPACE, PROJECT, "duplicate-anchor term", top_k=2, include_pending=False,
                         include_related=True, related_limit=5)

    assert [hit["citation"]["event_record_id"] for hit in result["hits"]] == [anchor, anchor]
    assert _related_ids(result) == [related]
    assert result["coverage"]["related_anchor_events_considered"] == 1


def test_related_events_are_scope_isolated_before_expansion(tmp_path) -> None:
    store = _store(tmp_path)
    anchor = _ingest(store, "scoped-anchor", "scoped-anchor-1 scoped query")
    same_scope = _ingest(store, "same-scope", "same scope correction", sources=[_source_ref(anchor)])
    _ingest(store, "other-project", "other project correction", project="other", sources=[_source_ref(anchor)])
    _ingest(store, "other-workspace", "other workspace correction", workspace="other", sources=[_source_ref(anchor)])

    result = store.query(WORKSPACE, PROJECT, "scoped-anchor-1", top_k=1, include_pending=False,
                         include_related=True, related_limit=5)

    assert _related_ids(result) == [same_scope]
    assert {row["workspace_id"] for row in result["related_events"]} == {WORKSPACE}
    assert {row["project_id"] for row in result["related_events"]} == {PROJECT}


def test_related_events_are_bounded_and_non_recursive(tmp_path) -> None:
    store = _store(tmp_path)
    anchor = _ingest(store, "high-degree-anchor", "high-degree-anchor-1 query token")
    related = [
        _ingest(store, f"related-{index}", f"related {index}", sources=[_source_ref(anchor, source_id=f"edge-{index}")])
        for index in range(4)
    ]
    _ingest(store, "recursive-grandchild", "grandchild relation only", sources=[_source_ref(related[0])])

    result = store.query(WORKSPACE, PROJECT, "high-degree-anchor-1", top_k=1, include_pending=False,
                         include_related=True, related_limit=2)

    assert _related_ids(result) == related[:2]
    assert result["coverage"]["related_events_returned"] == 2
    assert result["coverage"]["related_events_omitted"] == 2
    assert result["coverage"]["related_limit"] == 2
    assert result["coverage"]["related_event_traversal"] == "one_hop_non_recursive"

def _mcp_payload(result: dict) -> dict:
    return json.loads(result["content"][0]["text"])


def _mcp_tool(name: str, arguments: dict | None = None) -> dict:
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments or {}}}
    return _mcp_payload(handle(request)["result"])


def test_mcp_query_schema_and_route_support_related_event_sidecar(monkeypatch, tmp_path) -> None:
    listed = handle({"id": 1, "method": "tools/list"})["result"]["tools"]
    query_schema = [tool for tool in listed if tool["name"] == "canon.context.query"][0]["inputSchema"]["properties"]
    assert query_schema["include_related"] == {"type": "boolean"}
    assert query_schema["related_limit"] == {"type": "integer", "minimum": 0, "maximum": 20}

    monkeypatch.setenv(ENV_CONTEXT_DB, str(tmp_path / "context.sqlite"))
    anchor = _mcp_tool("canon.context.ingest", _event("mcp-anchor", "mcp-anchor-1 primary text"))
    related = _mcp_tool("canon.context.ingest", _event(
        "mcp-related",
        "Related review through explicit source edge",
        sources=[_source_ref(anchor["event_record_id"])],
    ))

    default = _mcp_tool("canon.context.query", {
        "workspace_id": WORKSPACE,
        "project_id": PROJECT,
        "query": "mcp-anchor-1",
    })
    expanded = _mcp_tool("canon.context.query", {
        "workspace_id": WORKSPACE,
        "project_id": PROJECT,
        "query": "mcp-anchor-1",
        "include_related": True,
        "related_limit": 5,
    })

    assert "related_events" not in default
    assert expanded["hits"] == default["hits"]
    assert _related_ids(expanded) == [related["event_record_id"]]

