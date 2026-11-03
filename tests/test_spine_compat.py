"""Backward compatibility: nothing written before the spine breaks.

Three kinds of old record. A spine record with no cause block (every receipt
written before cause fields existed). The chain families already on
harness.hash_chain, whose seals must not move now that the byte form is a
parameter. Tool receipts in their older shapes (a gather digest row with no
availability rung, a crucible assessment with no recheck descriptor).
"""
import json
from pathlib import Path

from harness.evidence_json import canonical_sha256
from harness.hash_chain import chain_intact, seal
from harness.spine import SCHEMA, SCHEMA_VERSION, from_native, verify_record
from harness.spine import natives
from harness.spine.record import make_record, seal as spine_seal
from harness.verdict import Verdict

FIXTURES = Path(__file__).parent / "fixtures" / "spine"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_a_record_with_no_cause_block_verifies_and_carries_no_cause_checks():
    record = from_native(natives.EMET, _load("emet-receipt-match.json"))
    assert "cause" not in record
    result = verify_record(record)
    assert result.verdict is Verdict.PASS
    assert not [n for n, _, _ in result.checks if n.startswith("cause")]


def test_existing_hash_chain_families_seal_exactly_as_before():
    record = {"schema": "test.chain/v1", "prev_sha256": "", "note": "kept"}
    sealed = seal(record, digest_key="record_sha256")
    assert sealed["record_sha256"] == canonical_sha256(record)
    assert chain_intact([sealed], schema="test.chain/v1", digest_key="record_sha256")


def test_the_spine_byte_form_differs_from_the_default_only_where_floats_differ():
    """canonical-record/1 writes 30.0 as 30; the older form writes 30.0. The
    spine names its form in every record so a reader picks the right one."""
    from harness.spine.record import digest
    assert digest({"n": 1}) == canonical_sha256({"n": 1})
    assert digest({"x": 30.0}) != canonical_sha256({"x": 30.0})


def test_a_gather_row_without_the_newer_optional_rungs_still_rechecks():
    digest = _load("gather-digest.json")
    assert all("availability" not in r and "storage" not in r for r in digest["receipts"])
    assert natives.check_gather(digest)[:2] == (True, "MATCH")


def test_a_crucible_assessment_without_recheck_descriptors_still_rechecks():
    a = _load("crucible-assessment-warn.json")
    assert all("recheck" not in m for m in a["measurements"])
    assert natives.check_crucible(a)[:2] == (True, "warn")


def test_a_newer_schema_version_is_refused_by_name_not_guessed_at():
    record = from_native(natives.GATHER, _load("gather-digest.json"))
    body = {k: v for k, v in record.items() if k != "record_sha256"}
    body["schema_version"] = SCHEMA_VERSION + 1
    result = verify_record(spine_seal(body))
    assert result.verdict is Verdict.UNVERIFIABLE
    assert "newer" in result.checks[0][2]


def test_a_record_of_another_schema_is_not_read_as_a_spine_record():
    assert verify_record({"schema": "flywheel.receipt/v5"}).verdict is Verdict.UNVERIFIABLE


def test_an_unknown_tool_schema_keeps_its_digest_check_and_is_unverifiable():
    """A tool with no native checker yet: the spine still checks the seal,
    the vocabulary and the payload digest, and says plainly what it could not."""
    record = make_record(tool="index", source_schema="index.verification/1",
                         source_vocabulary="integrity", source_verdict="MATCH",
                         payload={"verdict": "MATCH"}, scope="test scope")
    assert record["schema"] == SCHEMA
    result = verify_record(record)
    passed = {n for n, v, _ in result.checks if v is Verdict.PASS}
    assert {"seal", "vocabulary", "payload"} <= passed
    assert result.verdict is Verdict.UNVERIFIABLE
