"""Egress findings from the review of the purge and capture branch.

Whatever reaches the store through `canon.context.ingest` is redacted before
it is stored, as the capture hook's events are. Query excerpts are scrubbed
whole and then cut, so a secret that straddles the cut is still recognised.
Pending references and related-event sources are scrubbed on the way out. A
purge names the content digests earlier results carried as out of reach.
"""
from __future__ import annotations

import json
import random
import secrets
import string

import pytest

from canon.context_mcp import ENV_CONTEXT_DB, ENV_MCP_PURGE, handle
from canon.context_store import ContextStore

from ._context_fixtures import PROJECT, WORKSPACE, citing_payload, prompt_payload

_CUT = 2000
_JWT_HEADER = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"


def _call(name, arguments):
    reply = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": name, "arguments": arguments}})["result"]
    return reply["isError"], reply["content"][0]["text"]


def _scope(**more):
    return {"workspace_id": WORKSPACE, "project_id": PROJECT, **more}


def _random(length: int, alphabet: str = string.ascii_letters + string.digits) -> str:
    rng = random.Random(secrets.randbits(64))
    return "".join(rng.choice(alphabet) for _ in range(length))


def _runs(value: str, width: int = 5) -> list[str]:
    """Runs long enough that a chance match in the ids and digests of the
    output is negligible; the leaks the review reproduced were 6 or more."""
    return [value[i:i + width] for i in range(len(value) - width + 1)]


@pytest.fixture()
def mcp_db(tmp_path, monkeypatch):
    db = tmp_path / "context.sqlite"
    monkeypatch.setenv(ENV_CONTEXT_DB, str(db))
    monkeypatch.delenv(ENV_MCP_PURGE, raising=False)
    return db


@pytest.fixture()
def raw_store(monkeypatch):
    """Store events as a 0.3.0 store or an unredacted writer left them."""
    monkeypatch.setattr("canon.context_store.redact_payload", lambda value: value)


def test_mcp_ingest_redacts_before_storing(mcp_db) -> None:
    fake = "sk-FAKE" + secrets.token_hex(20)
    payload = prompt_payload("turn-1", f"The harbor key is OPENAI_API_KEY={fake} today")
    payload["event"]["attachments"] = [{"ref": f"https://x.example/f?api_key={fake}",
                                        "extraction_status": "pending_extraction"}]

    is_error, text = _call("canon.context.ingest", payload)

    assert is_error is False, text
    assert fake.encode() not in mcp_db.read_bytes()
    record = ContextStore(mcp_db).get(WORKSPACE, PROJECT, json.loads(text)["event_record_id"])
    assert sum(record["record"]["data"]["coverage"]["redactions"].values()) >= 2


def test_a_hook_event_already_redacted_is_stored_unchanged(mcp_db) -> None:
    payload = prompt_payload("turn-1", "Nothing secret about the harbor ledger")
    before = json.dumps(payload, sort_keys=True)

    ContextStore(mcp_db).ingest(payload)
    again = ContextStore(mcp_db).ingest(payload)

    assert again["status"] == "already_present"
    assert json.dumps(payload, sort_keys=True) == before


def test_a_secret_across_the_excerpt_cut_is_still_redacted(mcp_db, raw_store) -> None:
    password = _random(26)
    url = f"postgres://admin:{password}@db.internal/harbor"
    payload_segment = _random(60, string.ascii_letters + string.digits + "-_")
    jwt = f"{_JWT_HEADER}.eyJ{payload_segment}.{_random(43)}"
    lead = "harbor ledger "
    for index, secret in enumerate((url, jwt)):
        filler = "~" * (_CUT - len(lead) - len(secret) // 2)
        ContextStore(mcp_db).ingest(prompt_payload(f"turn-{index}", lead + filler + secret))

    _, text = _call("canon.context.query", _scope(query="harbor ledger", top_k=5))

    assert len(json.loads(text)["hits"]) >= 2
    assert not [run for run in _runs(password) if run in text]
    assert _JWT_HEADER not in text
    assert not [run for run in _runs(payload_segment) if run in text]


def test_pending_refs_and_related_sources_are_scrubbed_over_mcp(mcp_db, raw_store) -> None:
    fake_ref, fake_locator = "ghp_" + secrets.token_hex(18), secrets.token_hex(12)
    first = prompt_payload("turn-1", "The harbor ledger lists the tide tables")
    first["event"]["attachments"] = [{"ref": f"https://x.example/f?api_key={fake_ref}",
                                      "extraction_status": "pending_extraction"}]
    cited = ContextStore(mcp_db).ingest(first)["event_record_id"]
    later = citing_payload("turn-2", cited, "Following up on the harbor ledger")
    later["event"]["sources"][-1]["locator"] = f"https://svc:{fake_locator}@x.example/a"
    ContextStore(mcp_db).ingest(later)

    _, text = _call("canon.context.query", _scope(query="harbor ledger",
                                                  include_related=True))

    result = json.loads(text)
    assert result["pending_extraction"] and result["related_events"]
    assert fake_ref not in text and fake_locator not in text


def test_a_purge_names_the_content_digests_earlier_results_carried(mcp_db) -> None:
    store = ContextStore(mcp_db)
    prompt = store.ingest(prompt_payload("turn-1", "The harbor ledger"))["event_record_id"]

    _, text = _call("canon.context.purge", _scope(event_id=prompt))

    classes = {row["class"] for row in json.loads(text)["out_of_reach"]}
    assert "returned_content_digests" in classes
