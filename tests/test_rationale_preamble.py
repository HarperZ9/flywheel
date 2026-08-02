"""Tests for parse_tool_calls with_preamble and execute rationale wiring."""
from __future__ import annotations

from harness.local_tools import ToolExecutor, parse_tool_calls
from harness.tool_call_receipt import verify_receipt


# --- parse_tool_calls with_preamble ---------------------------------------


def test_parse_without_preamble_is_backward_compatible():
    """The default return shape is (name, args) tuples, unchanged."""
    text = "Let me check.\nTOOL read_file {\"path\": \"/tmp/x\"}"
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    name, args = calls[0]
    assert name == "read_file"
    assert args == {"path": "/tmp/x"}


def test_parse_with_preamble_extracts_pre_call_text():
    """A TOOL line preceded by reasoning yields (name, args, preamble)."""
    text = "Let me check the config first.\nTOOL read_file {\"path\": \"/etc/config\"}"
    calls = parse_tool_calls(text, with_preamble=True)
    assert len(calls) == 1
    name, args, preamble = calls[0]
    assert name == "read_file"
    assert args == {"path": "/etc/config"}
    assert "Let me check the config" in preamble


def test_parse_with_preamble_empty_when_no_preceding_text():
    """A TOOL line with no preceding text yields an empty preamble."""
    text = 'TOOL read_file {"path": "/tmp/x"}'
    calls = parse_tool_calls(text, with_preamble=True)
    assert len(calls) == 1
    name, args, preamble = calls[0]
    assert preamble == ""


def test_parse_with_preamble_multi_call_preambles():
    """Each call gets the text between the previous TOOL line and itself."""
    text = (
        "First, I'll read.\n"
        'TOOL read_file {"path": "/a"}\n'
        "Now let me list.\n"
        'TOOL list_dir {"path": "/b"}'
    )
    calls = parse_tool_calls(text, with_preamble=True)
    assert len(calls) == 2
    assert "First" in calls[0][2]
    assert "Now let me list" in calls[1][2]


def test_parse_with_preamble_no_calls_returns_empty():
    text = "Just text, no tool calls."
    assert parse_tool_calls(text, with_preamble=True) == []


# --- execute with rationale -----------------------------------------------


def _executor_with_receipts(tmp_path) -> ToolExecutor:
    """A ToolExecutor with receipt emission enabled."""
    from harness.local_tools import ToolExecutor
    ex = ToolExecutor()
    ex.receipt_dir = str(tmp_path)
    ex._receipt_run_id = "test-run"
    ex._receipt_seq = 0
    ex._receipt_prev_sha256 = ""
    ex.init_receipt_chain("test-run")
    return ex


def test_execute_without_rationale_produces_receipt_without_rationale(tmp_path):
    """The default (no rationale) produces a receipt with no rationale key."""
    ex = _executor_with_receipts(tmp_path)
    ex.execute("read_file", {"path": "nonexistent_for_test"})
    # find the receipt file
    import json
    from pathlib import Path
    receipts = list(Path(ex.receipt_dir).glob("tool-receipt-*.json"))
    assert len(receipts) >= 1
    receipt = json.loads(receipts[0].read_text())
    assert "rationale" not in receipt
    v = verify_receipt(receipt)
    assert v["verdict"] == "MATCH"


def test_execute_with_rationale_seals_it(tmp_path):
    """Passing rationale produces a receipt with the rationale block."""
    ex = _executor_with_receipts(tmp_path)
    ex.execute("read_file", {"path": "nonexistent_for_test"}, rationale={
        "stated_intent": "checking the file exists",
        "options_considered": ["read", "skip"],
        "chosen_option": "read_file",
        "confidence": "moderate",
    })
    import json
    from pathlib import Path
    receipts = list(Path(ex.receipt_dir).glob("tool-receipt-*.json"))
    assert len(receipts) >= 1
    receipt = json.loads(receipts[0].read_text())
    assert receipt["rationale"]["stated_intent"] == "checking the file exists"
    assert receipt["rationale"]["chosen_option"] == "read_file"
    v = verify_receipt(receipt)
    assert v["verdict"] == "MATCH"
    assert v.get("has_rationale") is True


def test_execute_with_rationale_tampering_breaks_seal(tmp_path):
    """Tampering the rationale after execution breaks the seal."""
    ex = _executor_with_receipts(tmp_path)
    ex.execute("read_file", {"path": "x"}, rationale={
        "stated_intent": "original intent",
        "options_considered": [],
        "chosen_option": "read_file",
        "confidence": "high",
    })
    import json
    from pathlib import Path
    receipts = list(Path(ex.receipt_dir).glob("tool-receipt-*.json"))
    receipt = json.loads(receipts[0].read_text())
    receipt["rationale"]["stated_intent"] = "tampered"
    v = verify_receipt(receipt)
    assert v["verdict"] == "TAMPERED"


def test_execute_without_rationale_byte_identical_to_pre_change(tmp_path):
    """A receipt built without rationale has no rationale key (backward-compatible)."""
    ex = _executor_with_receipts(tmp_path)
    ex.execute("list_dir", {"path": "."})
    import json
    from pathlib import Path
    receipts = list(Path(ex.receipt_dir).glob("tool-receipt-*.json"))
    receipt = json.loads(receipts[0].read_text())
    # The field is absent, not null-padded
    assert "rationale" not in receipt
    # And the receipt still verifies
    assert verify_receipt(receipt)["verdict"] == "MATCH"
