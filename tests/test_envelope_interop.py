"""test_envelope_interop.py — receipts export to in-toto / DSSE, full-length hash.

Success criteria:
  - content_sha256 is a full 64-hex sha256, algorithm-tagged; content_hash (the
    legacy short id) is unchanged at 16 hex.
  - to_in_toto_statement has the right shape and binds the full content digest.
  - to_dsse_envelope base64-payload decodes back to exactly that Statement.
"""
import base64
import json

from harness.envelope import (
    DSSE_PAYLOAD_TYPE,
    IN_TOTO_STATEMENT_TYPE,
    PREDICATE_TYPE,
    ProofEnvelope,
)


def _env():
    return ProofEnvelope(
        task_id="task-42", candidate="def f():\n    return 1\n", oracle="pytest",
        oracle_cmd="python -m pytest -q", oracle_output_hash="abc123", verdict="PASS",
        model_ref="serve:14b", seed=0, prompt_hash="ph", budget_spent={"n": 4})


def test_full_hash_is_tagged_64hex_and_short_id_unchanged():
    e = _env()
    tag, hexd = e.content_sha256().split(":", 1)
    assert tag == "sha256" and len(hexd) == 64 and int(hexd, 16) >= 0   # valid hex
    assert len(e.content_hash()) == 16                                  # legacy short id kept
    assert hexd.startswith(e.content_hash())                            # short id is the prefix


def test_in_toto_statement_shape_and_digest_binding():
    e = _env()
    st = e.to_in_toto_statement()
    assert st["_type"] == IN_TOTO_STATEMENT_TYPE
    assert st["predicateType"] == PREDICATE_TYPE
    assert st["subject"][0]["name"] == "task-42"
    assert st["subject"][0]["digest"]["sha256"] == e.content_sha256().split(":", 1)[1]
    assert st["predicate"]["model_ref"] == "serve:14b"       # envelope carried unchanged


def test_dsse_payload_roundtrips_to_the_statement():
    e = _env()
    dsse = e.to_dsse_envelope()
    assert dsse["payloadType"] == DSSE_PAYLOAD_TYPE and dsse["signatures"] == []
    decoded = json.loads(base64.b64decode(dsse["payload"]))
    assert decoded == e.to_in_toto_statement()               # exact round-trip


def test_verdict_does_not_change_the_content_hash():
    # a receipt's content hash is over the request/answer, not the pass/fail, so a
    # verifier that re-derives a DIFFERENT verdict still matches the same subject.
    a = _env()
    b = _env()
    b.verdict = "FAIL"
    b.oracle_output_hash = "different"
    assert a.content_sha256() == b.content_sha256()
