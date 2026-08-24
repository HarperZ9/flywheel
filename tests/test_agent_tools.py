"""agent_tools -- the harness's verification economy as callable tools.

Any connected model can call these through a provider's native tools
field: prove a receipt's inclusion in the Merkle log, summarize the
receipts ledger, read the world root hash. Tools that carry receipts
are the surface no other coding harness ships. Dispatchers are strict:
unknown names, non-dict arguments, and malformed leaves return typed
errors, never guesses.
"""
import pytest

from harness.agent_tools import dispatch, tool_definitions

_FAKE_LEDGER = {
    "catalog": [],
    "catalog_present": 0,
    "envelopes": [
        {"name": "a.json", "verdict": "PASS", "task_id": "t1",
         "sha256": "1" * 64},
        {"name": "b.json", "verdict": "PASS", "task_id": "t2",
         "sha256": "2" * 64},
    ],
    "envelope_count": 2,
    "pass_count": 2,
}


def _inject(**_):
    return _FAKE_LEDGER


def test_definitions_are_wellformed_and_unique():
    defs = tool_definitions()
    names = [d["function"]["name"] for d in defs]
    assert len(names) == len(set(names)) and len(names) >= 3
    for d in defs:
        assert d["type"] == "function"
        assert d["function"]["description"]
        params = d["function"]["parameters"]
        assert params.get("type") == "object"
        assert isinstance(params.get("properties"), dict)


def test_verify_receipt_inclusion_matches_and_refuses_strangers():
    out = dispatch("verify_receipt_inclusion", {"leaf": "1" * 64},
                   ledger=_inject)
    assert out["included"] is True
    assert out["proof"]["schema"] == "flywheel.receipts-proof/v2"

    stranger = "f" * 64
    out2 = dispatch("verify_receipt_inclusion", {"leaf": stranger},
                    ledger=_inject)
    assert out2["included"] is False
    assert out2["proof"]["leaf"] == stranger


def test_verify_rejects_malformed_leaf_with_fixed_error():
    out = dispatch("verify_receipt_inclusion", {"leaf": "zz"},
                   ledger=_inject)
    assert "error" in out and "64-hex" in out["error"]


def test_ledger_summary_counts():
    out = dispatch("receipts_ledger_summary", {}, ledger=_inject)
    assert out == {"envelopes": 2, "pass": 2, "catalog_present": 0,
                   "catalog_total": 0}


def test_world_root_hash_is_a_64hex_string():
    out = dispatch("world_root_hash", {}, world_root="a" * 64)
    assert out == {"root_hash": "a" * 64}


def test_unknown_tool_and_bad_arguments_are_typed():
    assert "error" in dispatch("no_such_tool", {})
    assert "error" in dispatch("receipts_ledger_summary", {"x": 1},
                               ledger=_inject)
    assert "error" in dispatch("verify_receipt_inclusion", "not a dict",
                               ledger=_inject)


def test_dispatcher_never_leaks_internal_tracebacks():
    def boom(**_):
        raise RuntimeError("secret internal detail")
    out = dispatch("receipts_ledger_summary", {}, ledger=boom)
    assert out == {"error": "the receipts ledger could not be read"}
    assert "secret" not in str(out)
