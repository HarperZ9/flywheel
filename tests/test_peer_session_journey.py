"""Journey v2 emission: the chain reduces, claims stay UNVERIFIABLE, no text leaks."""
from __future__ import annotations

import json
import os
import re

import pytest

from harness.evidence_json import canonical_sha256
from harness.journey_projection import reduce_events
from harness.peer_session_journey import ACTOR_ID, registry_to_events
from harness.peer_session_io import text_digest
from harness.peer_session_registry import build_registry, default_roots, discover
from harness.peer_session_types import DOES_NOT_PROVE, FAILURE_DOES_NOT_PROVE
from tests.peer_session_fixtures import (CLAUDE_SESSION, CODEX_THREAD, assert_no_canary,
                                         write_claude, write_codex)

NOW = "2026-09-10T12:00:00Z"
SHA_REF = re.compile(r"sha256:[0-9a-f]{64}\Z")
CODEX_BASE = f"peer-1-codex-{CODEX_THREAD[:12]}"
CLAUDE_BASE = f"peer-2-claude_code-{CLAUDE_SESSION[:12]}"


def _registry(tmp_path, *, with_failure: bool = False) -> dict:
    a = write_claude(tmp_path)
    c = write_codex(tmp_path)
    os.utime(a, (1_800_000_000, 1_800_000_000))
    os.utime(c, (1_800_000_001, 1_800_000_001))
    entries = discover(default_roots(tmp_path))
    if with_failure:
        entries.append({"path": str(tmp_path / "ghost.jsonl"), "harness": "codex",
                        "size_bytes": 0, "mtime_utc": "2030-01-01T00:00:00Z",
                        "subagent_path": False})
    return build_registry(entries, observed_at=NOW)


def test_events_chain_and_reduce_with_unverifiable_claims(tmp_path):
    registry = _registry(tmp_path)
    result = registry_to_events(registry, occurred_at=NOW)
    events = result["events"]
    assert result["event_count"] == len(events) == 3
    assert re.fullmatch(r"jrn_[0-9a-f]{32}", result["journey_ref"])
    assert events[0]["event_type"] == "intake" and events[0]["sequence"] == 0
    assert registry["registry_sha256"] in json.dumps(events[0])
    for index, event in enumerate(events):
        assert event["sequence"] == index
        assert event["journey_ref"] == result["journey_ref"]
        assert event["actor_id"] == ACTOR_ID and event["occurred_at"] == NOW
        if index:
            assert event["prior_event_sha256"] == events[index - 1]["event_sha256"]
            assert event["event_type"] == "record_fact"
            assert event["request_sha256"] == canonical_sha256(event["payload"])
    projection = reduce_events(events)
    assert projection["stage"] == "intake"
    assert projection["fact_ids"] == sorted([CODEX_BASE, CLAUDE_BASE])
    assert projection["claim_ids"] == sorted([f"{CODEX_BASE}-alive", f"{CODEX_BASE}-model",
                                              f"{CLAUDE_BASE}-alive", f"{CLAUDE_BASE}-model"])
    assert set(projection["verdicts"].values()) == {"UNVERIFIABLE"}
    assert projection["missing_evidence"] == []
    assert_no_canary(events)
    assert '"_bytes"' not in json.dumps(events)


def test_fact_receipt_refs_are_the_window_hashes(tmp_path):
    registry = _registry(tmp_path)
    events = registry_to_events(registry, occurred_at=NOW)["events"]
    for session, event in zip(registry["sessions"], events[1:]):
        fact = event["payload"]["facts"][0]
        expected = sorted({f"sha256:{w['sha256']}" for w in session["windows"].values()})
        assert fact["receipt_refs"] == expected and len(expected) >= 1
        assert all(SHA_REF.match(ref) for ref in fact["receipt_refs"])
        assert fact["receipt_state"] == "present_unchecked"
        assert fact["session_ref"] in (CODEX_THREAD, CLAUDE_SESSION)
        assert fact["source_path"] == session["source"]["path"]
        assert set(fact["windows"]) == {"head", "tail"}
        assert set(fact["windows"]["head"]) == {"offset", "length", "sha256"}
        assert "does not prove" in fact["does_not_prove"].lower()
        for claim in event["payload"]["claims"]:
            assert claim["verdict"] == "UNVERIFIABLE" and claim["review_required"] is True
            assert claim["depends_on"] == [fact["fact_id"]]
            assert claim["receipt_refs"] == fact["receipt_refs"]
            assert claim["does_not_prove"]


def test_failed_observation_becomes_a_missing_receipt(tmp_path):
    registry = _registry(tmp_path, with_failure=True)
    assert registry["observe_failures"] == 1
    events = registry_to_events(registry, occurred_at=NOW)["events"]
    assert len(events) == 4
    failure = events[1]["payload"]
    assert failure["claims"] == []
    fact = failure["facts"][0]
    assert fact["fact_id"] == "peer-1-codex-unknown"
    assert fact["receipt_state"] == "missing"
    assert fact["receipt_refs"] == ["observe-failure:peer-1-codex-unknown"]
    assert "OSError" in fact["statement"] or "SourceRejected" in fact["statement"]
    projection = reduce_events(events)
    assert projection["missing_evidence"] == [{"kind": "fact", "id": "peer-1-codex-unknown",
                                               "receipt_refs": fact["receipt_refs"]}]
    assert "peer-2-codex-" in projection["fact_ids"][1]


def test_emission_is_deterministic_for_a_given_journey_ref(tmp_path):
    registry = _registry(tmp_path)
    ref = "jrn_" + "a" * 32
    first = registry_to_events(registry, occurred_at=NOW, journey_ref=ref)
    second = registry_to_events(registry, occurred_at=NOW, journey_ref=ref)
    assert first == second and first["journey_ref"] == ref
    shifted = registry_to_events(registry, occurred_at="2026-09-10T12:00:01Z", journey_ref=ref)
    assert shifted["events"][0]["event_sha256"] != first["events"][0]["event_sha256"]


def test_invalid_journey_ref_is_rejected(tmp_path):
    registry = _registry(tmp_path)
    with pytest.raises(ValueError):
        registry_to_events(registry, occurred_at=NOW, journey_ref="not-a-ref")


def test_empty_registry_yields_only_genesis():
    registry = build_registry([], observed_at=NOW)
    result = registry_to_events(registry, occurred_at=NOW)
    assert result["event_count"] == 1
    projection = reduce_events(result["events"])
    assert projection["fact_ids"] == [] and projection["claim_ids"] == []


def test_session_without_model_gets_no_model_claim(tmp_path):
    """A session that named no model still carries a model_reported record, and that
    record is a dict. The gate has to read the value inside it, not its presence."""
    registry = _registry(tmp_path)
    for session in registry["sessions"]:
        session["model_reported"] = {"value": None, "basis": "not_emitted", "samples": 0}
        session["models_reported"] = []
    events = registry_to_events(registry, occurred_at=NOW)["events"]
    claim_ids = [c["claim_id"] for e in events[1:] for c in e["payload"]["claims"]]
    assert claim_ids == [f"{CODEX_BASE}-alive", f"{CLAUDE_BASE}-alive"]


def test_an_id_that_is_not_id_shaped_is_digested_never_copied(tmp_path):
    """A transcript is a file anything can write, and its id field reaches an event
    id and a fact field. An unshaped id leaves as a digest and nothing else."""
    registry = _registry(tmp_path)
    stated = "not an id, free text " + "x" * 40
    registry["sessions"][0]["thread_id"] = stated
    events = registry_to_events(registry, occurred_at=NOW)["events"]
    fact = events[1]["payload"]["facts"][0]
    assert fact["fact_id"] == "peer-1-codex-unknown"
    assert fact["session_ref"] is None
    assert fact["session_ref_unshaped"] == text_digest(stated)
    assert "session_ref_not_id_shaped" in fact["issues"]
    assert "free text" not in json.dumps(events)


def test_a_shaped_id_is_reported_whole_and_carries_no_unshaped_digest(tmp_path):
    """The gate has to pass a real id through. Without this the test above would
    still pass if every id were dropped."""
    registry = _registry(tmp_path)
    facts = [e["payload"]["facts"][0]
             for e in registry_to_events(registry, occurred_at=NOW)["events"][1:]]
    assert [f["session_ref"] for f in facts] == [CODEX_THREAD, CLAUDE_SESSION]
    assert all(f["session_ref_unshaped"] is None for f in facts)
    assert all("session_ref_not_id_shaped" not in f["issues"] for f in facts)


def test_a_failure_carries_the_failure_wording_not_the_observation_wording(tmp_path):
    """The two does-not-prove sentences answer different questions. A read that never
    happened must not inherit the sentence written for bytes that were read."""
    registry = _registry(tmp_path, with_failure=True)
    events = registry_to_events(registry, occurred_at=NOW)["events"]
    failed = events[1]["payload"]["facts"][0]
    observed = events[2]["payload"]["facts"][0]
    assert failed["does_not_prove"] == FAILURE_DOES_NOT_PROVE
    assert observed["does_not_prove"] == DOES_NOT_PROVE
    assert "does not prove the file is absent" in failed["does_not_prove"]
