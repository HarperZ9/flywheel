"""Synthetic private custody and original ledger retention controls."""
import json
import base64
import hashlib
from dataclasses import asdict
from pathlib import Path

import pytest

from harness.evidence_json import canonical_sha256
from harness.gateway_agent_trace import AgentTrace, TraceError, TraceLedger

OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "b" * 32
OP = "op_" + "c" * 32
MARKER = "PRIVATE_SOURCE_FIXTURE_7d912"


def trace(tmp_path):
    return AgentTrace(tmp_path, OWNER, JOURNEY, OP)


def test_original_ledger_survives_reopen_and_public_projection_is_separate(tmp_path):
    writer = trace(tmp_path)
    ledger = TraceLedger(writer)
    ledger.append("user", MARKER)
    ledger.append("tool_result", "first\n" + "x" * 9000 + "\nLAST-LINE")
    projection = writer.projection("running")
    reopened = trace(tmp_path)
    records = reopened.read()
    assert [r["payload"] for r in records] == [asdict(e) for e in ledger.entries]
    assert records[-1]["payload"]["content"].endswith("LAST-LINE")
    assert MARKER not in json.dumps(projection)
    digest = projection.pop("projection_sha256")
    assert digest == canonical_sha256(projection)
    assert digest != projection["trace_head_sha256"]
    assert reopened.projection("cancelled")["record_count"] == 2


@pytest.mark.parametrize("binding", ["../escape", "owner_" + "d" * 32])
def test_wrong_owner_cannot_read_trace(tmp_path, binding):
    writer = trace(tmp_path)
    writer.append("request", {"goal": MARKER})
    with pytest.raises(TraceError):
        AgentTrace(tmp_path, binding, JOURNEY, OP).read_reference(writer.ref)


@pytest.mark.parametrize("payload", [{"api_key": "synthetic"},
    {"text": "Bearer synthetic-fixture"}, {"text": "APPROVED_FIXTURE_SECRET"},
    {"opaque-fixture-739ab": "innocuous value"}])
def test_credentials_never_enter_private_records(tmp_path, payload):
    writer = AgentTrace(tmp_path, OWNER, JOURNEY, OP,
                        secrets=("APPROVED_FIXTURE_SECRET", "opaque-fixture-739ab"))
    with pytest.raises(TraceError):
        writer.append("progress", payload)
    assert writer.read() == []
    assert not list(tmp_path.rglob("*.json"))


def test_exact_router_environment_is_private_but_arbitrary_environment_is_rejected(tmp_path):
    writer = trace(tmp_path)
    writer.append("result", {"environment": {
        "python": "3.12.1", "platform": "Windows-11", "machine": "AMD64"}})
    with pytest.raises(TraceError):
        writer.append("result", {"environment": {"PATH": MARKER}})
    assert writer.read()[0]["payload"]["environment"]["platform"] == "Windows-11"


def test_size_limit_rejects_without_publishing_a_shortened_record(tmp_path, monkeypatch):
    import harness.gateway_agent_trace as module
    monkeypatch.setattr(module, "MAX_RECORD_BYTES", 2048)
    writer = trace(tmp_path)
    writer.append("request", {"goal": "accepted"})
    with pytest.raises(TraceError):
        writer.append("progress", {"text": "x" * 4096})
    assert len(writer.read()) == 1


def test_tampered_record_does_not_become_a_verified_prefix(tmp_path):
    writer = trace(tmp_path)
    writer.append("request", {"goal": MARKER})
    path = next(tmp_path.rglob("00000000.json"))
    path.write_text(path.read_text().replace(MARKER, "TAMPERED"))
    with pytest.raises(TraceError):
        trace(tmp_path).read()


@pytest.mark.parametrize("sequence", [0, 1, 2])
def test_deleted_record_cannot_be_resealed_as_a_shorter_prefix(tmp_path, sequence):
    from harness.gateway_agent_execution import recovered_projection
    writer = trace(tmp_path)
    for index in range(3): writer.append("progress", {"index": index})
    next(tmp_path.rglob(f"{sequence:08d}.json")).unlink()
    with pytest.raises(TraceError):
        recovered_projection(tmp_path, OWNER, JOURNEY, OP, "failed", "OPERATION_INTERRUPTED")


def test_shared_native_detail_fixture_hashes_match_its_projection():
    fixtures = Path(__file__).parent / "fixtures" / "native_agent_trace"
    detail = json.loads((fixtures / "detail.json").read_text(encoding="utf-8"))
    projected = json.loads((fixtures / "detail_projection.json").read_text())
    raw = base64.b64decode(detail["record_canonical_base64"], validate=True)
    record = detail["record"]
    assert hashlib.sha256(raw).hexdigest() == record["record_sha256"]
    assert json.loads(raw) == {k: v for k, v in record.items() if k != "record_sha256"}
    assert record["record_sha256"] == projected["trace_head_sha256"]
    assert projected["trace_ref"] == detail["trace_ref"]
    digest = projected.pop("projection_sha256")
    assert canonical_sha256(projected) == digest
