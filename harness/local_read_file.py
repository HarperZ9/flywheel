"""Bounded read_file paging for the local ToolExecutor."""
from __future__ import annotations

import json
import os
from typing import Callable

from .local_read_handle import open_confined_read_handle

META_PREFIX = "READ_FILE_META "
MAX_READ_BYTES = 1_048_576
MIN_PAGED_OUTPUT = 160
BUDGET_ERROR = "[error] read_file_budget"
READ_FILE_TOOL_GUIDANCE = (
    'TOOL read_file {"path": "<path>", "offset": 0, "max_bytes": 4000}\n'
    "READ_FILE_META gives next_offset and identity; while truncated is true, "
    "continue with offset=next_offset and if_identity=identity. "
    "On read_file_source_drift, discard partial content and start a fresh read.\n")
_ALLOWED_ARGS = {"path", "offset", "max_bytes", "if_identity"}
_IDENTITY_KEYS = {"size", "mtime_ns"}


def read_file_tool(root: str, args: dict, max_output: int,
                   safe_path: Callable[[str, str], str | None]) -> tuple[bool, str]:
    if not _positive_int(max_output):
        return False, BUDGET_ERROR
    parsed = _parse_args(args)
    if isinstance(parsed, str):
        return False, parsed
    rel, offset, requested, expected_identity = parsed
    target = safe_path(root, rel)
    if target is None:
        return False, "[error] read_file_path_escaped (escapes root)"
    opened = open_confined_read_handle(root, target)
    if isinstance(opened, str):
        return False, opened
    fd, st = opened.fd, opened.st
    try:
        identity = _public_identity(st)
        if expected_identity is not None and expected_identity != identity:
            return False, "[error] read_file_source_drift"
        if offset > st.st_size:
            return False, "[error] read_file_offset_past_eof"
        if offset and not _is_utf8_boundary(fd, offset, st.st_size):
            return False, "[error] read_file_offset_not_utf8_boundary"
        explicit = any(k in args for k in ("offset", "max_bytes", "if_identity"))
        if not explicit and st.st_size <= max_output:
            return _read_small(fd, int(st.st_size), max_output, identity)
        if max_output < MIN_PAGED_OUTPUT:
            return False, BUDGET_ERROR
        return _read_page(fd, offset, requested, identity, max_output)
    finally:
        os.close(fd)


def _parse_args(args: dict) -> tuple[str, int, int, dict | None] | str:
    if not isinstance(args, dict):
        return "[error] read_file_args_invalid"
    if set(args) - _ALLOWED_ARGS:
        return "[error] read_file_args_unknown"
    rel = args.get("path")
    if not isinstance(rel, str) or not rel:
        return "[error] read_file_path_invalid"
    offset = args.get("offset", 0)
    if not _nonnegative_int(offset):
        return "[error] read_file_offset_invalid"
    requested = args.get("max_bytes", MAX_READ_BYTES)
    if (not _positive_int(requested)) or requested > MAX_READ_BYTES:
        return "[error] read_file_max_bytes_invalid"
    expected = args.get("if_identity")
    if expected is None:
        return rel, offset, requested, None
    if not isinstance(expected, dict):
        return "[error] read_file_identity_invalid"
    if set(expected) != _IDENTITY_KEYS:
        return "[error] read_file_identity_invalid"
    if not _nonnegative_int(expected.get("size")):
        return "[error] read_file_identity_invalid"
    if not _nonnegative_int(expected.get("mtime_ns")):
        return "[error] read_file_identity_invalid"
    return rel, offset, requested, {
        "size": int(expected["size"]), "mtime_ns": int(expected["mtime_ns"])}


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _public_identity(st) -> dict:
    return {"size": int(st.st_size), "mtime_ns": int(st.st_mtime_ns)}


def _same_public_identity(fd: int, identity: dict) -> bool:
    try:
        return _public_identity(os.fstat(fd)) == identity
    except OSError:
        return False


def _read_small(fd: int, size: int, max_output: int, identity: dict) -> tuple[bool, str]:
    try:
        data = _read_bytes(fd, 0, min(size, max_output) + 1)
    except OSError:
        return False, "[error] read_file_open_failed"
    if len(data) > size or len(data) > max_output or not _same_public_identity(fd, identity):
        return False, "[error] read_file_source_drift"
    return True, data.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")


def _read_page(fd: int, offset: int, requested: int, identity: dict,
               max_output: int) -> tuple[bool, str]:
    size = identity["size"]
    available = max(0, size - offset)
    limit = min(requested, available, max_output)
    while limit >= 0:
        if limit == 0 and available > 0:
            return False, BUDGET_ERROR
        try:
            data = _read_bytes(fd, offset, limit)
        except OSError:
            return False, "[error] read_file_open_failed"
        if not _same_public_identity(fd, identity):
            return False, "[error] read_file_source_drift"
        if not data and available > 0:
            return False, "[error] read_file_source_drift"
        keep = _complete_utf8_prefix_len(data)
        if data and keep == 0:
            return False, "[error] read_file_utf8_range_too_small"
        body = data[:keep].decode("utf-8", "replace")
        output = META_PREFIX + json.dumps(
            _meta(offset, keep, size, identity), separators=(",", ":")) + "\n" + body
        if len(output) <= max_output:
            return True, output
        limit -= max(1, len(output) - max_output)
    return False, BUDGET_ERROR


def _read_bytes(fd: int, offset: int, limit: int) -> bytes:
    os.lseek(fd, offset, os.SEEK_SET)
    return os.read(fd, limit)


def _meta(offset: int, returned: int, size: int, identity: dict) -> dict:
    next_offset = offset + returned
    truncated = next_offset < size
    return {
        "schema": "flywheel.read_file/v1",
        "offset": offset,
        "bytes": returned,
        "size": size,
        "truncated": truncated,
        "next_offset": next_offset if truncated else None,
        "identity": identity,
        "identity_method": "stat.size+mtime_ns",
        "encoding": "utf-8",
    }


def _is_utf8_boundary(fd: int, offset: int, size: int) -> bool:
    if offset <= 0 or offset >= size:
        return True
    try:
        b = _read_bytes(fd, offset, 1)
    except OSError:
        return False
    return not (b and 0x80 <= b[0] <= 0xBF)


def _complete_utf8_prefix_len(data: bytes) -> int:
    if not data:
        return 0
    cut = len(data)
    trailing = 0
    i = cut - 1
    while i >= 0 and 0x80 <= data[i] <= 0xBF:
        trailing += 1
        i -= 1
    if trailing == 0:
        return cut - 1 if _utf8_width(data[-1]) > 1 else cut
    if i < 0:
        return 0
    width = _utf8_width(data[i])
    if width == 1:
        return cut
    return cut if trailing + 1 >= width else i


def _utf8_width(byte: int) -> int:
    if byte < 0x80:
        return 1
    if 0xC2 <= byte <= 0xDF:
        return 2
    if 0xE0 <= byte <= 0xEF:
        return 3
    if 0xF0 <= byte <= 0xF4:
        return 4
    return 1
