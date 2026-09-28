import copy

import pytest

from scripts.frozen_gateway_receipt_smoke import validate_receipt_parity
from harness.receipt_operations import mcp_tool_descriptors
from harness.receipt_proof import build_receipt_proof


LEAF = "1" * 64
PROOF = build_receipt_proof(LEAF, [LEAF, "2" * 64])
ROOT = PROOF["merkle_root"]


def result(payload, *, error=False):
    import json
    return {"structuredContent": payload,
            "content": [{"type": "text", "text": json.dumps(payload)}],
            "isError": error}


def responses():
    return {
        1: {"protocolVersion": "2025-06-18"},
        2: {"tools": mcp_tool_descriptors()},
        3: result({"included": True, "status": "included", "proof": PROOF,
                   "verification": {"replayed": True, "included": True}}),
        4: result({"included": False, "status": "missing",
                   "proof": {"leaf": "f" * 64, "merkle_root": ROOT}}),
        5: result({"error": {"code": "INVALID_LEAF"}}, error=True),
    }


def test_exact_http_mcp_proof_and_negative_results():
    summary = validate_receipt_parity(responses(), PROOF, ROOT, LEAF)
    assert summary["http_mcp_proof_equal"] is True
    assert summary["missing_leaf_status"] == "missing"
    assert summary["malformed_leaf_code"] == "INVALID_LEAF"


@pytest.mark.parametrize("mutation,code", [
    ("http", "RECEIPT_TRANSPORT_DRIFT"),
    ("structured", "RECEIPT_CONTENT_DRIFT"),
    ("missing", "RECEIPT_MISSING_PROMOTED"),
    ("malformed", "RECEIPT_MALFORMED_ACCEPTED"),
])
def test_false_success_controls(mutation, code):
    values, proof = responses(), copy.deepcopy(PROOF)
    if mutation == "http":
        proof["tree_size"] = 9
    elif mutation == "structured":
        values[3]["structuredContent"] = {"included": True}
    elif mutation == "missing":
        values[4] = result({"included": True, "status": "included"})
    else:
        values[5]["isError"] = False
    with pytest.raises(RuntimeError, match=code):
        validate_receipt_parity(values, proof, ROOT, LEAF)


def test_matching_transports_cannot_answer_a_different_leaf():
    with pytest.raises(RuntimeError, match="RECEIPT_REQUEST_LEAF_MISMATCH"):
        validate_receipt_parity(responses(), PROOF, ROOT, "a" * 64)


def test_name_only_tool_does_not_establish_packaged_schema():
    values = responses()
    values[2] = {"tools": [{"name": "receipt.verify_inclusion"}]}
    with pytest.raises(RuntimeError, match="RECEIPT_MCP_TOOL_SCHEMA"):
        validate_receipt_parity(values, PROOF, ROOT, LEAF)


def test_missing_root_cannot_be_shared_null():
    values = responses()
    values[4] = result({"included": False, "status": "missing",
                        "proof": {"leaf": "f" * 64, "merkle_root": None}})
    with pytest.raises(RuntimeError, match="RECEIPT_HTTP_MISSING_ROOT"):
        validate_receipt_parity(values, PROOF, None, LEAF)


def test_missing_and_included_proofs_must_describe_the_same_log():
    values = responses()
    values[4] = result({"included": False, "status": "missing",
                        "proof": {"leaf": "f" * 64, "merkle_root": "a" * 64}})
    with pytest.raises(RuntimeError, match="RECEIPT_LOG_ROOT_DRIFT"):
        validate_receipt_parity(values, PROOF, "a" * 64, LEAF)


@pytest.mark.parametrize("mutation", [None, "tree_size", "index", "sibling"])
def test_fixture_oracle_binds_metadata_and_other_leaf(tmp_path, mutation):
    import hashlib
    from scripts.frozen_gateway_receipt_smoke import (
        prepare_receipt_smoke_fixture, validate_fixture_proof)
    leaf = prepare_receipt_smoke_fixture(tmp_path)
    leaves = [hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted((tmp_path / "runs" / "envelopes").glob("*.json"))]
    if mutation == "sibling":
        leaves[0] = "a" * 64
    proof = build_receipt_proof(leaf, leaves)
    if mutation == "tree_size":
        proof["tree_size"] = 9
    if mutation == "index":
        proof["index"] = 0
    if mutation is None:
        validate_fixture_proof(proof, leaf)
    else:
        with pytest.raises(RuntimeError, match="RECEIPT_FIXTURE_PROOF_MISMATCH"):
            validate_fixture_proof(proof, leaf)


@pytest.mark.parametrize("item", [None, 1, "untrusted", []])
def test_malformed_content_item_is_a_typed_failure(item):
    values = responses()
    values[3]["content"] = [item]
    with pytest.raises(RuntimeError, match="RECEIPT_MCP_CONTENT_SHAPE"):
        validate_receipt_parity(values, PROOF, ROOT, LEAF)


@pytest.mark.parametrize("mutation,code", [
    ("tools", "RECEIPT_MCP_TOOL_SCHEMA"),
    ("verification", "RECEIPT_MCP_NOT_REPLAYED"),
    ("error", "RECEIPT_MALFORMED_ACCEPTED"),
    ("response", "RECEIPT_MCP_RESPONSE_SHAPE"),
])
def test_malformed_nested_values_fail_with_bounded_codes(mutation, code):
    values = responses()
    if mutation == "tools":
        values[2] = {"tools": None}
    elif mutation == "verification":
        values[3] = result({**values[3]["structuredContent"], "verification": None})
    elif mutation == "error":
        values[5] = result({"error": None}, error=True)
    else:
        values[1] = None
    with pytest.raises(RuntimeError, match=code):
        validate_receipt_parity(values, PROOF, ROOT, LEAF)
