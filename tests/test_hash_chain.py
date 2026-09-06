"""The shared append-only chain, and the four ways to break one.

This walk used to be about to exist twice, once for schedule fires and
once for code scans. A rule with two implementations gets repaired in one
of them and the other keeps returning True, so the walk was extracted and
these are the tests that hold it. `test_scheduler.py` still exercises the
same code through its own wrapper, which is the evidence the extraction
kept the older behaviour rather than replacing it.
"""
import json

import pytest

from harness.hash_chain import (append_sealed, chain_intact, head_digest,
                                load_chain, seal)

SCHEMA = "test.chain/v1"
KEY = "record_sha256"


def _sealed(prev, **fields):
    return seal(dict({"schema": SCHEMA, "prev_sha256": prev}, **fields),
                digest_key=KEY)


def _chain(count):
    records, prev = [], ""
    for i in range(count):
        record = _sealed(prev, note=f"record {i}")
        records.append(record)
        prev = record[KEY]
    return records


def _intact(records):
    return chain_intact(records, schema=SCHEMA, digest_key=KEY)


def test_a_seal_covers_every_field_except_itself():
    record = _sealed("", note="one")
    # Sealing an already-sealed record reproduces the same digest. If the
    # digest were inside its own input this would drift on every pass,
    # and the only way to satisfy that is to stop checking.
    assert seal(record, digest_key=KEY)[KEY] == record[KEY]
    assert seal(dict(record, note="two"), digest_key=KEY)[KEY] != record[KEY]


def test_an_untouched_chain_verifies():
    assert _intact(_chain(4)) is True
    assert _intact([]) is True


def test_rewriting_a_record_breaks_its_own_digest():
    records = _chain(3)
    records[1] = dict(records[1], note="edited after the fact")
    assert _intact(records) is False


def test_deleting_a_record_breaks_the_citation_after_it():
    records = _chain(4)
    del records[1]
    assert _intact(records) is False


def test_reordering_two_records_breaks_the_chain():
    records = _chain(4)
    records[1], records[2] = records[2], records[1]
    assert _intact(records) is False


def test_a_foreign_record_fails_the_whole_chain_not_just_its_suffix():
    """A file holding a mix of families is not a chain of either one.

    Answering True for the prefix would let an appended foreign record
    ride behind a verdict that was really about its neighbours.
    """
    records = _chain(2)
    records.append(seal({"schema": "other.family/v1",
                         "prev_sha256": records[-1][KEY]}, digest_key=KEY))
    assert _intact(records) is False


def test_a_record_citing_the_wrong_predecessor_is_refused():
    records = _chain(3)
    records[2] = seal(dict(records[2], prev_sha256=records[0][KEY]),
                      digest_key=KEY)
    # The record is internally well sealed. It is the citation that is
    # wrong, which is the failure a per-record digest alone cannot see.
    assert seal(records[2], digest_key=KEY)[KEY] == records[2][KEY]
    assert _intact(records) is False


def test_a_missing_or_unreadable_file_reads_as_no_records(tmp_path):
    assert load_chain(tmp_path / "absent.json") == []
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert load_chain(broken) == []
    not_a_list = tmp_path / "object.json"
    not_a_list.write_text('{"schema": "x"}', encoding="utf-8")
    assert load_chain(not_a_list) == []


def test_head_digest_is_what_the_next_record_must_cite():
    records = _chain(3)
    assert head_digest([], digest_key=KEY) == ""
    assert head_digest(records, digest_key=KEY) == records[-1][KEY]


def test_appending_writes_the_file_and_returns_the_whole_chain(tmp_path):
    path = tmp_path / "nested" / "history.json"
    first = _sealed("", note="one")
    records = append_sealed(first, path=path, schema=SCHEMA, digest_key=KEY)
    assert len(records) == 1 and path.is_file()
    second = _sealed(first[KEY], note="two")
    records = append_sealed(second, path=path, schema=SCHEMA, digest_key=KEY)
    assert len(records) == 2
    assert _intact(json.loads(path.read_text(encoding="utf-8")))


def test_an_append_that_would_break_the_chain_leaves_the_file_alone(tmp_path):
    path = tmp_path / "history.json"
    first = _sealed("", note="one")
    append_sealed(first, path=path, schema=SCHEMA, digest_key=KEY)
    before = path.read_text(encoding="utf-8")
    stray = _sealed("a digest no record here has", note="two")
    with pytest.raises(ValueError):
        append_sealed(stray, path=path, schema=SCHEMA, digest_key=KEY)
    assert path.read_text(encoding="utf-8") == before


def test_appending_onto_an_already_broken_history_is_refused(tmp_path):
    """The refusal is about the file, not about the record being added.

    A well-formed record appended to a tampered history would sit on top
    of the break, which is where a reader is least likely to look.
    """
    path = tmp_path / "history.json"
    records = _chain(3)
    records[1] = dict(records[1], note="edited")
    path.write_text(json.dumps(records), encoding="utf-8")
    with pytest.raises(ValueError):
        append_sealed(_sealed(records[-1][KEY], note="after"), path=path,
                      schema=SCHEMA, digest_key=KEY)
