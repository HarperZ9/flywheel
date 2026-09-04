"""Tests for sealing a byte witness: what it takes, and what it refuses."""
from __future__ import annotations

import hashlib
import json

import pytest

from harness.byte_witness import (
    GENESIS,
    WITNESS_SCHEMA,
    Span,
    WitnessError,
    append,
    cite,
    does_not_prove,
    records,
    witness_bytes,
    witness_file,
)
from harness.evidence_json import canonical_bytes

SAMPLE = b"theorem two_plus_two : 2 + 2 = 4 := by norm_num\n"


def test_witness_records_the_digest_the_count_and_nothing_else():
    witness = witness_bytes(SAMPLE, label="lean-source")
    record = witness.record()
    assert record["schema"] == WITNESS_SCHEMA
    assert record["length"] == len(SAMPLE)
    assert record["prev"] == GENESIS
    assert record["sha256"] == hashlib.sha256(SAMPLE).hexdigest()
    # The bytes themselves never appear anywhere in the record.
    assert SAMPLE.decode() not in json.dumps(record)


def test_empty_bytes_are_a_legitimate_witness():
    witness = witness_bytes(b"", label="empty-stdout")
    assert witness.length == 0
    assert witness.sha256 == hashlib.sha256(b"").hexdigest()


def test_text_is_refused_because_it_has_no_bytes_yet():
    with pytest.raises(WitnessError) as caught:
        witness_bytes("2 + 2 = 4", label="statement")
    assert "encode it" in str(caught.value)


@pytest.mark.parametrize("bad", [None, 42, ["not", "bytes"], {"a": 1}])
def test_non_bytes_are_refused(bad):
    with pytest.raises(WitnessError):
        witness_bytes(bad, label="whatever")


def test_a_witness_needs_a_label():
    with pytest.raises(WitnessError):
        witness_bytes(SAMPLE, label="")


def test_a_malformed_prev_is_refused_at_sealing_time():
    with pytest.raises(WitnessError):
        witness_bytes(SAMPLE, label="lean-source", prev="not-a-digest")


def test_observed_at_may_be_empty_and_no_clock_fills_it_in():
    witness = witness_bytes(SAMPLE, label="lean-source")
    assert witness.observed_at == ""
    stamped = witness_bytes(SAMPLE, label="lean-source", observed_at="2026-09-04T00:00:00Z")
    assert stamped.observed_at == "2026-09-04T00:00:00Z"
    assert stamped.link() != witness.link()


def test_a_context_outside_the_json_data_model_is_named_not_swallowed():
    with pytest.raises(WitnessError) as caught:
        witness_bytes(SAMPLE, label="lean-source", context={"f": float("nan")})
    assert "canonicalize" in str(caught.value)


def test_a_context_that_is_not_an_object_is_refused():
    with pytest.raises(WitnessError):
        witness_bytes(SAMPLE, label="lean-source", context=["a", "b"])


def test_sealing_is_deterministic_across_runs():
    first = witness_bytes(SAMPLE, label="lean-source", context={"b": 1, "a": 2})
    second = witness_bytes(SAMPLE, label="lean-source", context={"a": 2, "b": 1})
    assert first.link() == second.link()


def test_the_record_canonicalizes_with_sorted_keys():
    witness = witness_bytes(SAMPLE, label="lean-source")
    raw = canonical_bytes(witness.record()).decode()
    assert raw.index('"context"') < raw.index('"label"') < raw.index('"length"')


def test_cite_seals_a_range_and_the_span_travels_with_the_record():
    span = cite(SAMPLE, 0, 7, note="the keyword")
    witness = witness_bytes(SAMPLE, label="lean-source", spans=[span])
    assert witness.record()["spans"] == [
        {"start": 0, "end": 7, "sha256": span.sha256, "note": "the keyword"}]


@pytest.mark.parametrize("start,end", [(0, 0), (5, 3), (-1, 4), (0, len(SAMPLE) + 1)])
def test_cite_refuses_a_range_that_is_not_inside_the_bytes(start, end):
    with pytest.raises(WitnessError):
        cite(SAMPLE, start, end)


def test_cite_refuses_a_boolean_bound():
    with pytest.raises(WitnessError):
        cite(SAMPLE, True, 4)


def test_a_span_cited_over_other_bytes_is_refused_at_sealing_time():
    foreign = cite(b"some entirely other bytes", 0, 4)
    with pytest.raises(WitnessError) as caught:
        witness_bytes(SAMPLE, label="lean-source", spans=[foreign])
    assert "other bytes" in str(caught.value)


def test_a_span_past_the_end_of_these_bytes_is_refused():
    with pytest.raises(WitnessError):
        witness_bytes(b"short", label="x",
                      spans=[Span(start=0, end=99, sha256="0" * 64)])


def test_a_raw_dict_is_not_a_span():
    with pytest.raises(WitnessError):
        witness_bytes(SAMPLE, label="x", spans=[{"start": 0, "end": 4}])


def test_a_chain_link_folds_in_prev_so_a_replay_is_not_a_continuation():
    chain = []
    first = append(chain, SAMPLE, label="step-1")
    second = append(chain, SAMPLE, label="step-1")
    assert first.sha256 == second.sha256  # the same bytes
    assert first.link() != second.link()  # and not the same link
    assert second.prev == first.link()


def test_append_refuses_anything_that_is_not_a_chain_of_witnesses():
    with pytest.raises(WitnessError):
        append(["not a witness"], SAMPLE, label="step-1")


def test_records_travels_in_order():
    chain = []
    append(chain, b"one", label="a")
    append(chain, b"two", label="b")
    assert [r["label"] for r in records(chain)] == ["a", "b"]


def test_witness_file_agrees_with_witness_bytes(tmp_path):
    path = tmp_path / "proof.lean"
    path.write_bytes(SAMPLE)
    from_disk = witness_file(path, label="lean-source")
    in_memory = witness_bytes(SAMPLE, label="lean-source")
    assert from_disk.record() == in_memory.record()


def test_witness_file_streams_a_payload_larger_than_one_chunk(tmp_path):
    path = tmp_path / "frames.bin"
    payload = bytes(range(256)) * 8192  # 2 MiB, past the 1 MiB read chunk
    path.write_bytes(payload)
    assert witness_file(path, label="frames").sha256 == (
        witness_bytes(payload, label="frames").sha256)


def test_a_file_that_cannot_be_read_is_a_named_refusal(tmp_path):
    with pytest.raises(WitnessError) as caught:
        witness_file(tmp_path / "absent.lean", label="lean-source")
    assert "could not be read" in str(caught.value)


def test_does_not_prove_is_never_empty_and_says_what_is_unsigned():
    unsigned = does_not_prove()
    assert unsigned and any("nothing is signed" in line for line in unsigned)
    signed = does_not_prove(signed=True, anchored=True)
    assert signed and not any("nothing is signed" in line for line in signed)
    assert len(signed) == len(unsigned)
