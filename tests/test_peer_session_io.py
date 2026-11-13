"""Bounded window reads: offsets, hashes, partial-line handling and refusals."""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from harness import peer_session_io as io

LINE = b'{"type":"x","n":%d}\n'


def _file(tmp_path, n: int, name: str = "t.jsonl"):
    data = b"".join(LINE % i for i in range(n))
    path = tmp_path / name
    path.write_bytes(data)
    return path, data


def test_small_file_is_read_whole_and_windows_overlap(tmp_path):
    path, data = _file(tmp_path, 5)
    win = io.read_windows(path, head_bytes=4096, tail_bytes=4096)
    assert win["source"]["whole_file_read"] is True
    assert win["source"]["windows_overlap"] is True
    assert win["source"]["size_bytes"] == len(data)
    assert win["head"]["offset"] == 0 and win["head"]["length"] == len(data)
    assert win["head"]["sha256"] == hashlib.sha256(data).hexdigest()
    assert win["tail"]["sha256"] == win["head"]["sha256"]
    assert win["source"]["mtime_utc"].endswith("Z")


def test_large_file_tail_drops_partial_first_line_and_hashes_bytes_read(tmp_path):
    path, data = _file(tmp_path, 400)
    tail_bytes = 100
    win = io.read_windows(path, head_bytes=64, tail_bytes=tail_bytes)
    assert win["source"]["whole_file_read"] is False
    assert win["source"]["windows_overlap"] is False
    assert win["head"]["offset"] == 0 and win["head"]["length"] == 64
    assert win["head"]["sha256"] == hashlib.sha256(data[:64]).hexdigest()
    tail = win["tail"]
    raw_offset = len(data) - tail_bytes
    assert tail["dropped_partial_prefix_bytes"] > 0
    assert tail["offset"] == raw_offset + tail["dropped_partial_prefix_bytes"]
    assert data[tail["offset"] - 1:tail["offset"]] == b"\n"
    assert tail["sha256"] == hashlib.sha256(data[tail["offset"]:]).hexdigest()
    assert tail["length"] == len(data) - tail["offset"]
    assert tail["_bytes"] == data[tail["offset"]:]


def test_window_that_starts_on_a_line_boundary_drops_nothing(tmp_path):
    path, data = _file(tmp_path, 10)
    line = len(LINE % 0)
    win = io.read_windows(path, head_bytes=line, tail_bytes=line * 2)
    assert win["tail"]["dropped_partial_prefix_bytes"] == 0
    assert win["tail"]["offset"] == len(data) - line * 2


def test_public_window_strips_bytes(tmp_path):
    path, _ = _file(tmp_path, 3)
    win = io.read_windows(path)
    public = io.public_window(win["head"])
    assert "_bytes" not in public and "sha256" in public


@pytest.mark.parametrize("head,tail", [(0, 10), (10, 0), (-1, 10), (io.MAX_WINDOW_BYTES + 1, 10),
                                       ("10", 10), (10, 2.5)])
def test_invalid_window_sizes_are_rejected(tmp_path, head, tail):
    path, _ = _file(tmp_path, 3)
    with pytest.raises(ValueError):
        io.read_windows(path, head_bytes=head, tail_bytes=tail)


def test_directory_is_refused(tmp_path):
    with pytest.raises(io.SourceRejected):
        io.read_windows(tmp_path)


def test_missing_file_is_refused(tmp_path):
    with pytest.raises((io.SourceRejected, OSError)):
        io.read_windows(tmp_path / "absent.jsonl")


def test_symlink_is_refused(tmp_path):
    path, _ = _file(tmp_path, 3)
    link = tmp_path / "link.jsonl"
    try:
        os.symlink(path, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted here")
    with pytest.raises(io.SourceRejected):
        io.read_windows(link)
    io.read_windows(path)


def test_iter_jsonl_counts_bad_lines_without_raising():
    data = (b'{"a":1}\n' + b"not json\n" + b"[1,2]\n" + b"\n" + b'{"b":2}\n'
            + b'{"trailing":true')
    records, report = io.iter_jsonl(data)
    assert [r for _, r in records] == [{"a": 1}, {"b": 2}]
    assert [o for o, _ in records] == [0, data.index(b'{"b"')]
    assert report == {"lines": 6, "objects": 2, "unparsed_lines": 4, "oversize_lines": 0,
                      "trailing_partial_line": True}
    assert report["objects"] + report["unparsed_lines"] + report["oversize_lines"] == report["lines"]


def test_iter_jsonl_oversize_line_is_counted_not_parsed():
    big = b'{"k":"' + b"x" * (io.MAX_LINE_BYTES + 1) + b'"}\n'
    records, report = io.iter_jsonl(big + b'{"ok":1}\n')
    assert [r for _, r in records] == [{"ok": 1}]
    assert report["oversize_lines"] == 1 and report["objects"] == 1
    assert report["trailing_partial_line"] is False


def test_iter_jsonl_empty_input():
    records, report = io.iter_jsonl(b"")
    assert records == []
    assert report["lines"] == 0 and report["objects"] == 0
    assert report["trailing_partial_line"] is False


def test_text_digest_is_hash_and_count_only():
    text = "secret words"
    digest = io.text_digest(text)
    assert digest == {"chars": len(text),
                      "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    assert "secret" not in json.dumps(digest)
    assert io.text_digest(None) is None and io.text_digest(12) is None
    assert io.text_digest("") == {"chars": 0, "sha256": hashlib.sha256(b"").hexdigest()}


def test_age_seconds_handles_z_suffix_and_garbage():
    assert io.age_seconds("2026-09-10T00:00:00Z", "2026-09-10T00:01:00Z") == 60.0
    assert io.age_seconds("2026-09-10T00:00:00+00:00", "2026-09-10T00:00:30Z") == 30.0
    assert io.age_seconds("nonsense", "2026-09-10T00:00:00Z") is None
    assert io.age_seconds("2026-09-10T00:00:00Z", "later") is None


def test_windows_that_genuinely_overlap_are_reported_as_overlapping(tmp_path):
    """A file larger than the head window but smaller than head plus tail is read
    twice across its middle. That is an overlap, and it is not one window."""
    path, data = _file(tmp_path, 10)
    win = io.read_windows(path, head_bytes=100, tail_bytes=150)
    assert win["source"]["size_bytes"] == len(data) > 100
    assert win["source"]["tail_window_is_head_window"] is False
    assert win["source"]["windows_overlap"] is True
    assert win["source"]["whole_file_read"] is True
    assert win["tail"]["offset"] < win["head"]["offset"] + win["head"]["length"]
    assert win["head"]["sha256"] != win["tail"]["sha256"]


def test_a_file_one_byte_past_the_head_window_is_covered_by_the_tail(tmp_path):
    """The tail starts at zero here, so the two windows do not overlap and the file
    is still read whole. Coverage and overlap are separate reasons."""
    path, data = _file(tmp_path, 10)
    win = io.read_windows(path, head_bytes=len(data) - 1, tail_bytes=io.DEFAULT_TAIL_BYTES)
    assert win["source"]["tail_window_is_head_window"] is False
    assert win["tail"]["offset"] == 0 and win["tail"]["length"] == len(data)
    assert win["tail"]["dropped_partial_prefix_bytes"] == 0
    assert win["source"]["whole_file_read"] is True
    assert win["tail"]["sha256"] == hashlib.sha256(data).hexdigest()


def test_a_file_exactly_the_head_window_wide_reports_one_window(tmp_path):
    path, data = _file(tmp_path, 10)
    win = io.read_windows(path, head_bytes=len(data), tail_bytes=32)
    assert win["source"]["tail_window_is_head_window"] is True
    assert win["tail"]["sha256"] == win["head"]["sha256"] == hashlib.sha256(data).hexdigest()
    assert win["source"]["whole_file_read"] is True
