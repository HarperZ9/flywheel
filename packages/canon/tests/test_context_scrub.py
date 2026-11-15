"""The byte-level half of a purge: what the residual scan counts, how long it
takes, and how the scrub reports a VACUUM that did not run.

A kept record may quote the text a purge removed, most often a kept answer
that restates its prompt. The scan counts each window of a purged value in the
files and in the rows the purge kept, and reports only what the kept rows do
not account for. That count must stay linear in the bytes read however much a
kept record quotes, or a purge could run for hours on an ordinary store.
"""
from __future__ import annotations

import json
import sqlite3
import time

import pytest

import canon.context_scrub as context_scrub
from canon.context_purge import select
from canon.context_scrub import residual_scan, scrub_database
from canon.context_store import ContextStore

from ._context_fixtures import PROJECT, WORKSPACE, answer_payload, long_canary, prompt_payload


def _stored(value: str) -> bytes:
    return json.dumps(value)[1:-1].encode("ascii")


def _scan(tmp_path, value: str, file_bytes: bytes, live: list[bytes]) -> dict:
    db = tmp_path / "scan.sqlite"
    db.write_bytes(file_bytes)
    return residual_scan(db, [value], live, 0)


@pytest.mark.parametrize("length", [40, 4000])
def test_the_scan_counts_only_what_the_kept_rows_do_not_hold(tmp_path, length) -> None:
    value = long_canary(length)[:length]
    quoted = b'{"text":"The answer quotes ' + _stored(value) + b' in full."}'
    windows = len(_stored(value)) - 15

    clean = _scan(tmp_path, value, b"header" + quoted + b"trailer", [quoted])
    residue = _scan(tmp_path, value, b"header" + quoted + b"junk" + _stored(value), [quoted])

    assert (clean["hits"], clean["kept_record_matches"]) == (0, windows)
    assert (residue["hits"], residue["kept_record_matches"]) == (windows, windows)


@pytest.mark.parametrize("length", [40, 4000])
def test_both_ways_of_counting_agree(tmp_path, monkeypatch, length) -> None:
    value = long_canary(length)[:length]
    quoted = b"kept " + _stored(value) + b" row"
    data = b"header" + quoted + b"junk" + _stored(value)[: length // 2] + b"end"
    results = []
    for threshold in (0, 10**9):
        monkeypatch.setattr(context_scrub, "_DIRECT_WINDOWS", threshold)
        results.append(_scan(tmp_path, value, data, [quoted]))

    assert results[0] == results[1]
    assert results[0]["hits"] > 0 and results[0]["kept_record_matches"] > 0


def _both_ways(tmp_path, monkeypatch, value: str, data: bytes, live: list[bytes]) -> list[dict]:
    results = []
    for threshold in (0, 10**9):
        monkeypatch.setattr(context_scrub, "_DIRECT_WINDOWS", threshold)
        results.append(_scan(tmp_path, value, data, live))
    return results


# Seed 335 at length 4000 is the input on which the two ways were first seen
# to disagree: its text holds three e-acute and then A-ring, pinned below.
_SEEDS = (0, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 335, 377, 610)


@pytest.mark.parametrize("seed", _SEEDS)
def test_both_ways_of_counting_agree_on_fixed_seeds(tmp_path, monkeypatch, seed) -> None:
    length = 4000
    value = long_canary(length, seed=seed)[:length]
    quoted = b"kept " + _stored(value) + b" row"
    data = b"header" + quoted + b"junk" + _stored(value)[: length // 2] + b"end"

    by_pass, direct = _both_ways(tmp_path, monkeypatch, value, data, [quoted])

    assert by_pass == direct
    assert direct["hits"] > 0 and direct["kept_record_matches"] > 0


@pytest.mark.parametrize("value, windows, repeated", [
    # Three e-acute and one A-ring, stored as four six-byte escapes. The
    # window that covers the first two escapes and the first four bytes of the
    # third starts at offset 0 and again at offset 6, inside its first occurrence.
    ("éééÅ", 8, 1),
    # One window of sixteen letters, starting at offsets 0 and 1.
    ("a" * 17, 1, 1),
])
def test_a_window_that_overlaps_itself_is_counted_at_every_offset(
        tmp_path, monkeypatch, value, windows, repeated) -> None:
    stored = _stored(value)
    quoted = b"kept " + stored + b" row"
    occurrences = len(stored) - 15

    clean = _both_ways(tmp_path, monkeypatch, value, b"header" + quoted + b"end", [quoted])
    residue = _both_ways(tmp_path, monkeypatch, value,
                         b"header" + quoted + b"junk" + stored + b"end", [quoted])

    assert occurrences == windows + repeated
    for result in clean:
        assert (result["windows"], result["hits"], result["kept_record_matches"]) == (
            windows, 0, occurrences)
    for result in residue:
        assert (result["hits"], result["kept_record_matches"]) == (occurrences, occurrences)


def test_residue_that_extends_a_kept_run_is_reported(tmp_path, monkeypatch) -> None:
    """Fifteen leftover bytes directly after a kept row that ends in the same
    letter make fifteen more windows, and the kept text accounts for none."""
    value = "a" * 16
    kept = b"kept " + b"a" * 16

    results = _both_ways(tmp_path, monkeypatch, value, kept + b"a" * 15 + b"|end", [kept])

    for result in results:
        assert (result["hits"], result["kept_record_matches"]) == (15, 1)


@pytest.mark.parametrize("blob, window, expected", [
    (b"", b"aa", 0), (b"aaa", b"aa", 2), (b"abab", b"ab", 2), (b"ababa", b"aba", 2),
    (b"xaax", b"aa", 1), (b"aaaaaaaa", b"aaaa", 5),
])
def test_occurrences_counts_every_offset(blob, window, expected) -> None:
    assert context_scrub._occurrences(blob, window) == expected


def test_a_kept_answer_quoting_a_long_prompt_is_scanned_in_bounded_time(tmp_path) -> None:
    store = ContextStore(tmp_path / "context.sqlite")
    for n in range(12):
        store.ingest(prompt_payload(f"fill-{n}", long_canary(20_000)))
    text = long_canary(30_000)
    prompt = store.ingest(prompt_payload("turn-1", text))["event_record_id"]
    store.ingest(answer_payload(prompt, "turn-1", "Quoting the prompt: " + text))
    selection = select(event_id=prompt, keep_responses=True)
    plan = store.purge_plan(WORKSPACE, PROJECT, selection)

    started = time.perf_counter()
    report = store.purge(WORKSPACE, PROJECT, selection, confirm_plan_sha256=plan["plan_sha256"])
    elapsed = time.perf_counter() - started

    assert report["status"] == "purged"
    assert report["residual_scan"]["hits"] == 0
    assert report["residual_scan"]["kept_record_matches"] > 30_000
    assert elapsed < 15, f"the purge took {elapsed:.1f} s"


class _FakeConn:
    def __init__(self, error: str) -> None:
        self._error = error

    def execute(self, sql: str):
        if sql == "VACUUM":
            raise sqlite3.OperationalError(self._error)
        return self

    def fetchone(self):
        return ("delete",)


@pytest.mark.parametrize("error, label", [
    ("database is locked", "skipped_database_busy"),
    ("database table is locked", "skipped_database_busy"),
    ("disk I/O error", "failed"),
    ("database or disk is full", "failed"),
])
def test_a_vacuum_that_does_not_run_is_named_for_its_cause(error, label) -> None:
    result = scrub_database(_FakeConn(error), 0.0)

    assert result == {"journal_mode": "delete", "vacuum": label,
                      "wal_checkpoint_before": "not_needed", "wal_checkpoint": "not_needed"}
