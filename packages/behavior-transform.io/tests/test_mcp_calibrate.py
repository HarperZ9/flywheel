import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import os
import pytest
from unittest.mock import patch
from collections import Counter

from mcp_calibrate import (
    calibrate,
    calibrate_with_counts,
    calibrate_response,
    calibrate_batch,
    calibrate_jsonrpc_request,
    calibrate_jsonrpc_response,
    TEXT_KEYS,
    _apply,
    _build_subs,
)


def test_calibrate_empty_string():
    with patch("mcp_calibrate.transforms_enabled", return_value=True):
        result = calibrate("")
    assert result == ""


def test_calibrate_disabled():
    with patch("mcp_calibrate.transforms_enabled", return_value=False):
        result = calibrate("any text at all")
    assert result == "any text at all"


def test_calibrate_with_counts_disabled():
    with patch("mcp_calibrate.transforms_enabled", return_value=False):
        text, counts = calibrate_with_counts("text")
    assert text == "text"
    assert isinstance(counts, Counter)
    assert len(counts) == 0


def test_calibrate_response_disabled():
    with patch("mcp_calibrate.transforms_enabled", return_value=False):
        result = calibrate_response({"text": "hello"})
    assert result == {"text": "hello"}


def test_calibrate_response_string():
    with patch("mcp_calibrate.transforms_enabled", return_value=True):
        with patch("mcp_calibrate.calibrate", return_value="calibrated"):
            result = calibrate_response("raw text")
    assert result == "calibrated"


def test_calibrate_response_dict():
    with patch("mcp_calibrate.transforms_enabled", return_value=True):
        with patch("mcp_calibrate.calibrate", side_effect=lambda t: t.upper()):
            result = calibrate_response({"text": "hello", "id": 123})
    assert result["text"] == "HELLO"
    assert result["id"] == 123


def test_calibrate_batch_disabled():
    with patch("mcp_calibrate.transforms_enabled", return_value=False):
        result = calibrate_batch(["a", "b", "c"])
    assert result == ["a", "b", "c"]


def test_text_keys_contains_expected():
    assert "content" in TEXT_KEYS
    assert "text" in TEXT_KEYS
    assert "output" in TEXT_KEYS
    assert "result" in TEXT_KEYS
    assert "message" in TEXT_KEYS
    assert "description" in TEXT_KEYS


def test_build_subs_empty():
    result = _build_subs({})
    assert result == []


def test_apply_no_subs():
    text, counter = _apply("hello world", [])
    assert text == "hello world"
    assert len(counter) == 0


def test_calibrate_jsonrpc_request_disabled():
    with patch("mcp_calibrate.transforms_enabled", return_value=False):
        req = {"method": "tools/call", "params": {"arguments": {"text": "hi"}}}
        result = calibrate_jsonrpc_request(req)
    assert result == req


def test_calibrate_jsonrpc_response_disabled():
    with patch("mcp_calibrate.transforms_enabled", return_value=False):
        resp = {"result": {"content": [{"type": "text", "text": "hi"}]}}
        result = calibrate_jsonrpc_response(resp)
    assert result == resp


def test_calibrate_jsonrpc_response_text_content():
    with patch("mcp_calibrate.transforms_enabled", return_value=True):
        with patch("mcp_calibrate.calibrate", side_effect=lambda t: t.upper()):
            resp = {"result": {"content": [{"type": "text", "text": "hello"}]}}
            result = calibrate_jsonrpc_response(resp)
    assert result["result"]["content"][0]["text"] == "HELLO"


def test_calibrate_jsonrpc_response_non_text_preserved():
    with patch("mcp_calibrate.transforms_enabled", return_value=True):
        with patch("mcp_calibrate.calibrate", side_effect=lambda t: t.upper()):
            resp = {"result": {"content": [{"type": "image", "data": "base64..."}]}}
            result = calibrate_jsonrpc_response(resp)
    assert result["result"]["content"][0]["data"] == "base64..."
