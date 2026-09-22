"""Codex app-server envelope parsing and builders.

These frames are JSON objects over newline-delimited streams, but the installed
Codex app-server schemas omit the JSON-RPC ``jsonrpc`` member. Keep this parser
private to Codex sessions so generic ACP/LSP JSON-RPC validation remains strict.
"""
from __future__ import annotations

import json
import math
from typing import Any

from .codex_session_types import MISSING


def classify(message: Any) -> str:
    if not isinstance(message, dict):
        raise ValueError("frame must be an object")
    if "method" in message:
        if "result" in message or "error" in message:
            raise ValueError("method frame cannot be response")
        if not isinstance(message["method"], str) or not message["method"]:
            raise ValueError("invalid method")
        if "id" in message:
            if not valid_id(message["id"]):
                raise ValueError("invalid id")
            return "request"
        return "notification"
    if "id" not in message or not valid_id(message["id"]):
        raise ValueError("response id required")
    has_result = "result" in message
    has_error = "error" in message
    if has_result == has_error:
        raise ValueError("response must contain exactly one payload")
    if has_error:
        error = message["error"]
        if not isinstance(error, dict) or type(error.get("code")) is not int:
            raise ValueError("invalid error")
        return "failure"
    return "response"


def valid_id(value: Any) -> bool:
    return isinstance(value, (int, str)) and not isinstance(value, bool)


def request(request_id: int | str, method: str, params: Any = None) -> dict:
    message = {"id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def notification(method: str, params: Any = None) -> dict:
    message = {"method": method}
    if params is not None:
        message["params"] = params
    return message


def success(request_id: int | str, result: Any) -> dict:
    return {"id": request_id, "result": result}


def failure(request_id: int | str, code: int, message: str,
            data: Any = MISSING) -> dict:
    error = {"code": code, "message": message}
    if data is not MISSING and data is not None:
        error["data"] = data
    return {"id": request_id, "error": error}



def loads(text: str) -> dict:
    return json.loads(text, parse_constant=_reject_constant,
                      parse_float=_finite_float, object_pairs_hook=_unique_object)


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite number")
    return number


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def encode(message: dict) -> bytes:
    raw = json.dumps(message, separators=(",", ":"), allow_nan=False)
    return (raw + "\n").encode("utf-8")


def readline_bounded(source, max_frame_bytes: int):
    limit = max_frame_bytes + 1
    readline = source.readline
    try:
        return readline(limit)
    except TypeError:
        read = getattr(source, "read", None)
        if read is None:
            return readline()
    chunks, total = [], 0
    while total <= max_frame_bytes:
        chunk = read(min(4096, limit - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if chunk.endswith(b"\n") if isinstance(chunk, bytes) else chunk.endswith("\n"):
            break
    if not chunks:
        return b""
    return b"".join(chunks) if isinstance(chunks[0], bytes) else "".join(chunks)


def _reject_constant(value: str):
    raise ValueError("non-finite JSON")
