"""Redaction boundary + leak scan: a proof packet is not a data lake.

Model-facing artifacts carry only digest-bound refs; raw payloads live in an
uncommitted temp store and are recoverable by digest for replay. A leak scanner
asserts that no raw payload appears in any model-facing artifact (leak_count == 0).
"""

from __future__ import annotations

from proof_surface.agent_action import redaction

_SECRET = "sk-" + "live-super-secret-token-value"


def test_redact_returns_a_digest_ref_and_hides_the_raw():
    entry = redaction.redact(_SECRET)
    assert entry["raw_payload_sha256"] == redaction.sha256_text(_SECRET)
    assert entry["ref"].startswith("redacted:sha256:")
    assert _SECRET not in entry["ref"]  # the raw never appears in the ref


def test_raw_store_roundtrips_by_digest_for_replay():
    store = redaction.RawStore()
    sha = store.put(_SECRET)
    assert store.get(sha) == _SECRET  # replay from digest only


def test_clean_artifact_has_zero_leaks():
    artifact = {
        "packet_id": "p",
        "sources": [{"ref": redaction.redact(_SECRET)["ref"]}],
    }
    assert redaction.scan_for_leaks(artifact, secrets=[_SECRET]) == []
    assert redaction.leak_count(artifact, secrets=[_SECRET]) == 0


def test_leaked_raw_payload_is_detected():
    leaky = {"packet_id": "p", "notes": f"the token was {_SECRET}"}
    findings = redaction.scan_for_leaks(leaky, secrets=[_SECRET])
    assert findings
    assert redaction.leak_count(leaky, secrets=[_SECRET]) == 1
