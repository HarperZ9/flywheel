"""Paged read_file behavior for the local ToolExecutor."""
from __future__ import annotations

import json
import os

import pytest

from harness.local_tools import ToolExecutor


def _meta(output: str) -> tuple[dict, str]:
    first, _, body = output.partition("\n")
    assert first.startswith("READ_FILE_META "), output
    return json.loads(first.removeprefix("READ_FILE_META ")), body


def _stat_with_size(st, size):
    class StaleStat:
        st_mode = st.st_mode
        st_ino = st.st_ino
        st_dev = st.st_dev
        st_size = size
        st_mtime_ns = st.st_mtime_ns

    return StaleStat()


def test_small_read_file_keeps_plain_text_output(tmp_path):
    (tmp_path / "small.txt").write_text("hello\nworld\n", encoding="utf-8")

    result = ToolExecutor(root=str(tmp_path)).execute(
        "read_file", {"path": "small.txt"})

    assert result.ok
    assert result.output == "hello\nworld\n"


def test_large_read_file_returns_metadata_that_survives_truncation(tmp_path):
    (tmp_path / "big.txt").write_bytes(("HEAD\n" + "x" * 5000).encode())

    result = ToolExecutor(root=str(tmp_path), max_output=512).execute(
        "read_file", {"path": "big.txt"})

    meta, body = _meta(result.output)
    assert result.ok
    assert len(result.output) <= 512
    assert body.startswith("HEAD\n")
    assert meta["truncated"] is True
    assert meta["offset"] == 0
    assert isinstance(meta["next_offset"], int) and meta["next_offset"] > 0
    assert meta["identity"]["size"] == 5005
    assert "mtime_ns" in meta["identity"]


def test_later_page_is_retrievable_without_repeating_head(tmp_path):
    text = "HEAD\n" + "x" * 5000 + "\nTAIL_MARKER\n"
    (tmp_path / "big.txt").write_bytes(text.encode())

    result = ToolExecutor(root=str(tmp_path), max_output=512).execute(
        "read_file", {"path": "big.txt", "offset": 5005, "max_bytes": 80})

    meta, body = _meta(result.output)
    assert result.ok
    assert "TAIL_MARKER" in body
    assert "HEAD" not in body
    assert meta["offset"] == 5005


def test_if_identity_detects_source_drift_between_pages(tmp_path):
    path = tmp_path / "big.txt"
    path.write_bytes(("HEAD\n" + "x" * 5000).encode())
    first = ToolExecutor(root=str(tmp_path), max_output=512).execute(
        "read_file", {"path": "big.txt"})
    identity = _meta(first.output)[0]["identity"]
    path.write_bytes(("changed\n" + "x" * 5000).encode())

    second = ToolExecutor(root=str(tmp_path), max_output=512).execute(
        "read_file", {"path": "big.txt", "offset": 10, "if_identity": identity})

    assert not second.ok
    assert second.output == "[error] read_file_source_drift"


def test_offset_at_eof_returns_empty_final_page(tmp_path):
    (tmp_path / "short.txt").write_bytes(b"abc")

    result = ToolExecutor(root=str(tmp_path), max_output=256).execute(
        "read_file", {"path": "short.txt", "offset": 3})

    meta, body = _meta(result.output)
    assert result.ok
    assert body == ""
    assert meta["bytes"] == 0
    assert meta["truncated"] is False
    assert meta["next_offset"] is None


def test_large_read_uses_bounded_byte_read(tmp_path, monkeypatch):
    from harness import local_read_file

    (tmp_path / "big.txt").write_bytes(b"x" * 100_000)
    seen_limits = []
    real_read = local_read_file._read_bytes

    def tracked_read(target, offset, limit):
        seen_limits.append(limit)
        return real_read(target, offset, limit)

    monkeypatch.setattr(local_read_file, "_read_bytes", tracked_read)
    result = ToolExecutor(root=str(tmp_path), max_output=256).execute(
        "read_file", {"path": "big.txt"})

    assert result.ok
    assert seen_limits and max(seen_limits) <= 256
    assert len(result.output) <= 256


def test_read_file_reconfines_target_returned_by_safe_path(tmp_path):
    from harness.local_read_file import read_file_tool

    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside-private-token.txt"
    outside.write_text("OUTSIDE", encoding="utf-8")

    result = read_file_tool(
        str(root), {"path": "victim.txt", "offset": 0}, 512,
        lambda root_arg, rel: str(outside))

    assert not result[0]
    assert result[1] == "[error] read_file_path_escaped (escapes root)"
    assert "OUTSIDE" not in result[1]


def test_stale_small_stat_does_not_exceed_output_budget(tmp_path, monkeypatch):
    from harness import local_read_file

    path = tmp_path / "race.txt"
    path.write_bytes(b"A" * 200)
    real_stat = local_read_file.os.stat

    def stale_stat(target, *args, **kwargs):
        if os.path.realpath(os.fspath(target)) == os.path.realpath(str(path)):
            return _stat_with_size(real_stat(target, *args, **kwargs), 64)
        return real_stat(target, *args, **kwargs)

    monkeypatch.setattr(local_read_file.os, "stat", stale_stat)
    result = ToolExecutor(root=str(tmp_path), max_output=64).execute(
        "read_file", {"path": "race.txt"})

    assert not result.ok
    assert result.output == "[error] read_file_source_drift"


def test_stale_paged_stat_does_not_emit_zero_progress(tmp_path, monkeypatch):
    from harness import local_read_file

    path = tmp_path / "race.txt"
    path.write_bytes(b"")
    real_stat = local_read_file.os.stat

    def stale_stat(target, *args, **kwargs):
        if os.path.realpath(os.fspath(target)) == os.path.realpath(str(path)):
            return _stat_with_size(real_stat(target, *args, **kwargs), 1000)
        return real_stat(target, *args, **kwargs)

    monkeypatch.setattr(local_read_file.os, "stat", stale_stat)
    result = ToolExecutor(root=str(tmp_path), max_output=256).execute(
        "read_file", {"path": "race.txt", "offset": 0})

    assert not result.ok
    assert result.output == "[error] read_file_source_drift"


@pytest.mark.parametrize("args", [
    "not an object",
    {},
    {"path": 7},
    {"path": "x", "offset": -1},
    {"path": "x", "offset": True},
    {"path": "x", "max_bytes": 0},
    {"path": "x", "max_bytes": 1_048_577},
    {"path": "x", "unexpected_arg": 1},
    {"path": "x", "if_identity": {"size": "1", "mtime_ns": 1}},
])
def test_read_file_rejects_malformed_arguments_with_typed_errors(tmp_path, args):
    (tmp_path / "x").write_text("abc", encoding="utf-8")

    result = ToolExecutor(root=str(tmp_path)).execute("read_file", args)

    assert not result.ok
    assert result.output.startswith("[error] read_file_")


def test_read_file_rejects_unknown_identity_keys(tmp_path):
    path = tmp_path / "x"
    path.write_text("abc", encoding="utf-8")
    st = path.stat()

    result = ToolExecutor(root=str(tmp_path)).execute("read_file", {
        "path": "x",
        "if_identity": {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "extra": 1},
    })

    assert not result.ok
    assert result.output == "[error] read_file_identity_invalid"


def test_read_file_errors_do_not_leak_paths_or_secretish_names(tmp_path):
    root = tmp_path / "private-root-token"
    root.mkdir()
    outside = tmp_path / "outside-private-token.txt"
    outside.write_text("secret", encoding="utf-8")
    executor = ToolExecutor(root=str(root))

    escape = executor.execute("read_file", {"path": "../outside-private-token.txt"})
    missing = executor.execute("read_file", {"path": "missing-private-token.txt"})

    assert not escape.ok
    assert escape.output == "[error] read_file_path_escaped (escapes root)"
    assert not missing.ok and missing.output == "[error] read_file_open_failed"
    assert "private-token" not in escape.output + missing.output


def test_read_file_preserves_utf8_boundaries(tmp_path):
    (tmp_path / "utf8.txt").write_bytes("a🙂b".encode())
    executor = ToolExecutor(root=str(tmp_path), max_output=256)

    first = executor.execute("read_file", {
        "path": "utf8.txt", "offset": 0, "max_bytes": 2})
    middle = executor.execute("read_file", {"path": "utf8.txt", "offset": 2})

    meta, body = _meta(first.output)
    assert first.ok
    assert body == "a"
    assert meta["next_offset"] == 1
    assert not middle.ok
    assert middle.output == "[error] read_file_offset_not_utf8_boundary"


def test_tiny_max_output_returns_typed_budget_error(tmp_path):
    (tmp_path / "big.txt").write_text("x" * 1000, encoding="utf-8")

    result = ToolExecutor(root=str(tmp_path), max_output=24).execute(
        "read_file", {"path": "big.txt"})

    assert not result.ok
    assert result.output == "[error] read_file_budget"


def test_tools_system_explains_read_file_paging_to_model():
    from harness.local_tools import TOOLS_SYSTEM

    assert "READ_FILE_META" in TOOLS_SYSTEM
    assert "next_offset" in TOOLS_SYSTEM
    assert "if_identity" in TOOLS_SYSTEM
    assert "truncated" in TOOLS_SYSTEM
    assert "read_file_source_drift" in TOOLS_SYSTEM


def test_continuation_metadata_reconstructs_complete_utf8_file(tmp_path):
    content = ("first🙂middle\n" * 80) + "TAIL"
    (tmp_path / "pages").write_bytes(content.encode("utf-8"))
    executor = ToolExecutor(root=str(tmp_path), max_output=512)
    args = {"path": "pages"}
    pages = []
    for _ in range(100):
        result = executor.execute("read_file", args)
        assert result.ok, result.output
        metadata, body = _meta(result.output)
        pages.append(body)
        if not metadata["truncated"]:
            break
        assert metadata["next_offset"] > metadata["offset"]
        args = {"path": "pages", "offset": metadata["next_offset"],
                "if_identity": metadata["identity"]}
    else:
        pytest.fail("read_file continuation never completed")
    assert len(pages) > 1
    assert "".join(pages) == content
