"""Tests for checking a byte witness: three verdicts, and never a raise."""
from __future__ import annotations

import json

import pytest

from harness.byte_witness import append, cite, records, witness_bytes
from harness.byte_witness_verify import (
    BYTES_UNAVAILABLE,
    CHAIN_SCHEMA,
    DIGEST_MISMATCH,
    LENGTH_MISMATCH,
    LINK_BROKEN,
    MALFORMED,
    NO_SIGNER,
    SPAN_MISMATCH,
    SPAN_OUT_OF_RANGE,
    VERIFY_SCHEMA,
    verify_chain,
    verify_signature,
    verify_witness,
)
from harness.tool_call_receipt import MATCH, TAMPERED, UNVERIFIABLE

SAMPLE = b"theorem two_plus_two : 2 + 2 = 4 := by norm_num\n"


def _roundtrip(record):
    """What a stranger actually receives: the record after a trip through JSON."""
    return json.loads(json.dumps(record))


def test_a_record_and_its_bytes_reproduce():
    record = _roundtrip(witness_bytes(SAMPLE, label="lean-source").record())
    result = verify_witness(record, SAMPLE)
    assert result["schema"] == VERIFY_SCHEMA
    assert result["verdict"] == MATCH
    assert result["failure_class"] is None


def test_without_bytes_the_answer_is_unverifiable_not_match():
    record = witness_bytes(SAMPLE, label="lean-source").record()
    result = verify_witness(record)
    assert result["verdict"] == UNVERIFIABLE
    assert result["failure_class"] == BYTES_UNAVAILABLE
    assert "well formed" in result["detail"]


def test_changed_bytes_of_the_same_length_are_tampered():
    record = witness_bytes(SAMPLE, label="lean-source").record()
    altered = SAMPLE.replace(b"= 4", b"= 5")
    assert len(altered) == len(SAMPLE)
    result = verify_witness(record, altered)
    assert (result["verdict"], result["failure_class"]) == (TAMPERED, DIGEST_MISMATCH)


def test_a_different_number_of_bytes_is_named_as_a_length_mismatch():
    record = witness_bytes(SAMPLE, label="lean-source").record()
    result = verify_witness(record, SAMPLE + b"\n")
    assert (result["verdict"], result["failure_class"]) == (TAMPERED, LENGTH_MISMATCH)


def test_a_matching_file_with_a_swapped_span_is_tampered():
    span = cite(SAMPLE, 0, 7)
    record = witness_bytes(SAMPLE, label="lean-source", spans=[span]).record()
    record["spans"][0]["sha256"] = "0" * 64
    result = verify_witness(_roundtrip(record), SAMPLE)
    assert (result["verdict"], result["failure_class"]) == (TAMPERED, SPAN_MISMATCH)


def test_a_span_past_the_recorded_length_is_refuted_without_any_bytes():
    record = witness_bytes(SAMPLE, label="lean-source",
                           spans=[cite(SAMPLE, 0, 7)]).record()
    record["spans"][0]["end"] = record["length"] + 1
    result = verify_witness(_roundtrip(record))
    assert (result["verdict"], result["failure_class"]) == (TAMPERED, SPAN_OUT_OF_RANGE)


def test_text_handed_in_as_bytes_is_unverifiable_not_a_guess():
    record = witness_bytes(SAMPLE, label="lean-source").record()
    result = verify_witness(record, SAMPLE.decode())
    assert (result["verdict"], result["failure_class"]) == (UNVERIFIABLE, BYTES_UNAVAILABLE)
    assert "encoding" in result["detail"]


@pytest.mark.parametrize("hostile", [
    None, "a string", 42, [], {"schema": "flywheel.byte-witness/v1"},
    {"schema": "something/v1", "label": "x", "sha256": "a" * 64, "length": 0,
     "observed_at": "", "prev": "", "spans": [], "context": {}},
])
def test_hostile_input_is_a_verdict_and_never_a_raise(hostile):
    result = verify_witness(hostile, SAMPLE)
    assert (result["verdict"], result["failure_class"]) == (UNVERIFIABLE, MALFORMED)


@pytest.mark.parametrize("field,value", [
    ("label", ""), ("sha256", "not-a-digest"), ("length", -1), ("length", 4.0),
    ("length", True), ("observed_at", 1234), ("prev", "short"), ("spans", {}),
    ("context", "not an object"),
])
def test_each_malformed_field_is_named(field, value):
    record = witness_bytes(SAMPLE, label="lean-source").record()
    record[field] = value
    result = verify_witness(record, SAMPLE)
    assert (result["verdict"], result["failure_class"]) == (UNVERIFIABLE, MALFORMED)
    assert result["detail"]


@pytest.mark.parametrize("span", [
    "not an object", {"start": "0", "end": 4, "sha256": "a" * 64},
    {"start": 0, "end": 4, "sha256": "short"},
    {"start": 0, "end": 4, "sha256": "a" * 64, "note": 7},
])
def test_a_malformed_span_is_malformed_not_tampered(span):
    record = witness_bytes(SAMPLE, label="lean-source").record()
    record["spans"] = [span]
    result = verify_witness(record, SAMPLE)
    assert (result["verdict"], result["failure_class"]) == (UNVERIFIABLE, MALFORMED)


FRAMES = [b"the raw instrument frame", b"the derived measurement", b"the verdict"]


def _chain_of_three():
    chain = []
    for payload, label in zip(FRAMES, ["frame", "measurement", "verdict"]):
        append(chain, payload, label=label)
    return _roundtrip(records(chain))


def test_a_whole_chain_with_a_resolver_reproduces():
    store = {witness_bytes(b, label="x").sha256: b for b in FRAMES}
    result = verify_chain(_chain_of_three(), resolve=store.__getitem__)
    assert result["schema"] == CHAIN_SCHEMA
    assert result["verdict"] == MATCH
    assert result["checked"] == 3
    assert result["head"]


def test_a_chain_without_a_resolver_is_unverifiable_but_still_linked():
    result = verify_chain(_chain_of_three())
    assert (result["verdict"], result["failure_class"]) == (UNVERIFIABLE, BYTES_UNAVAILABLE)
    assert "link into one chain" in result["detail"]
    assert result["head"]


def test_a_removed_middle_record_breaks_the_link():
    chain = _chain_of_three()
    result = verify_chain([chain[0], chain[2]])
    assert (result["verdict"], result["failure_class"]) == (TAMPERED, LINK_BROKEN)
    assert result["broken_at"] == 1


def test_an_edited_record_breaks_every_link_after_it():
    chain = _chain_of_three()
    chain[0]["label"] = "frame (relabelled)"
    result = verify_chain(chain)
    assert (result["verdict"], result["failure_class"]) == (TAMPERED, LINK_BROKEN)
    assert result["broken_at"] == 1


def test_an_added_field_is_a_modification_the_chain_catches():
    chain = _chain_of_three()
    chain[0]["note"] = "slipped in later"
    assert verify_chain(chain)["verdict"] == TAMPERED


def test_a_segment_without_its_earlier_head_is_unverifiable_not_match():
    chain = _chain_of_three()
    lifted = verify_chain(chain[1:])
    assert (lifted["verdict"], lifted["failure_class"]) == (TAMPERED, LINK_BROKEN)
    told = verify_chain(chain[1:], start=chain[1]["prev"])
    assert told["verdict"] == UNVERIFIABLE
    assert told["failure_class"] == BYTES_UNAVAILABLE


@pytest.mark.parametrize("empty", [[], None, "not a chain"])
def test_an_empty_chain_is_unverifiable(empty):
    result = verify_chain(empty)
    assert (result["verdict"], result["failure_class"]) == (UNVERIFIABLE, MALFORMED)


@pytest.mark.parametrize("element", [None, "a record", 42, True, [], 3.5])
def test_a_chain_holding_any_json_value_is_a_verdict_and_never_a_raise(element):
    # A stranger runs this over attacker JSON, so every element is whatever
    # json.loads produced. The whole class is closed here rather than one
    # element type at a time.
    result = verify_chain([element])
    assert (result["verdict"], result["failure_class"]) == (UNVERIFIABLE, MALFORMED)
    inside = verify_chain(_chain_of_three()[:1] + [element])
    assert inside["verdict"] == UNVERIFIABLE


@pytest.mark.parametrize("record", [None, "a record", 42, True, [], {}, 3.5])
def test_verify_signature_survives_any_json_value_as_the_record(record):
    result = verify_signature(record, "ab" * 64, "cd" * 32)
    assert (result["verdict"], result["failure_class"]) == (UNVERIFIABLE, MALFORMED)


@pytest.mark.parametrize("signature,key", [
    ([1, 2], "cd" * 32), ({"sig": "x"}, "cd" * 32), (True, "cd" * 32),
    ("ab" * 64, [1, 2]), ("ab" * 64, {"key": "x"}), (3.5, 7.5),
])
def test_verify_signature_survives_a_hostile_signature_or_key(signature, key):
    record = witness_bytes(SAMPLE, label="lean-source").record()
    result = verify_signature(record, signature, key)
    assert result["verdict"] == UNVERIFIABLE


def test_a_malformed_start_is_refused_before_anything_is_read():
    result = verify_chain(_chain_of_three(), start="nope")
    assert (result["verdict"], result["failure_class"]) == (UNVERIFIABLE, MALFORMED)


def test_a_malformed_record_inside_a_chain_is_unverifiable_not_tampered():
    chain = _chain_of_three()
    chain[1] = {"schema": "flywheel.byte-witness/v1"}
    result = verify_chain(chain)
    assert (result["verdict"], result["failure_class"]) == (UNVERIFIABLE, MALFORMED)
    assert result["broken_at"] == 1


def test_a_resolver_that_raises_leaves_the_links_checked_and_the_bytes_not():
    def broken(_digest):
        raise OSError("the archive is offline")

    result = verify_chain(_chain_of_three(), resolve=broken)
    assert result["verdict"] == MATCH  # the links held; no bytes contradicted them
    assert result["checked"] == 3


def test_a_resolver_returning_the_wrong_bytes_is_tampered():
    result = verify_chain(_chain_of_three(), resolve=lambda _d: b"substituted")
    assert result["verdict"] == TAMPERED
    assert result["broken_at"] == 0


def test_a_chain_result_carries_what_it_does_not_prove():
    result = verify_chain(_chain_of_three())
    assert any("omitted step" in line for line in result["does_not_prove"])
    assert any("last record" in line for line in result["does_not_prove"])


def test_an_unsigned_record_is_bound_to_no_key():
    record = witness_bytes(SAMPLE, label="lean-source").record()
    result = verify_signature(record, "", "")
    assert (result["verdict"], result["failure_class"]) == (UNVERIFIABLE, NO_SIGNER)


@pytest.mark.parametrize("signature,key", [
    ("zz", "a" * 64), ("ab" * 64, "cd" * 16), ("ab" * 32, "cd" * 40),
])
def test_a_signature_that_is_not_shaped_like_one_is_malformed(signature, key):
    record = witness_bytes(SAMPLE, label="lean-source").record()
    result = verify_signature(record, signature, key)
    assert (result["verdict"], result["failure_class"]) == (UNVERIFIABLE, MALFORMED)


def test_a_wrong_signature_is_a_verdict_and_not_an_exception():
    record = witness_bytes(SAMPLE, label="lean-source").record()
    result = verify_signature(record, "ab" * 64, "cd" * 32)
    assert result["verdict"] in {TAMPERED, UNVERIFIABLE}
    assert result["detail"]


def test_a_real_signature_verifies_over_the_link():
    key = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    from cryptography.hazmat.primitives import serialization

    private = key.Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    witness = witness_bytes(SAMPLE, label="lean-source")
    signature = private.sign(witness.link().encode("ascii"))
    record = _roundtrip(witness.record())
    good = verify_signature(record, signature.hex(), public.hex())
    assert good["verdict"] == MATCH
    record["label"] = "relabelled after signing"
    assert verify_signature(record, signature.hex(), public.hex())["verdict"] == TAMPERED
