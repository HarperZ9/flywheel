"""Compare actual frozen HTTP and stdio MCP receipt operations."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from harness.receipt_operations import mcp_tool_descriptors
from harness.transparency_log import verify_inclusion
from scripts.frozen_mcp_process import run_mcp_process

TOOL = "receipt.verify_inclusion"
MISSING_LEAF = "f" * 64


def _fixture_envelope(index: int) -> bytes:
    return json.dumps({"task_id": f"frozen-receipt-{index}",
                       "synthetic": True}, sort_keys=True).encode()


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def prepare_receipt_smoke_fixture(home: Path) -> str:
    directory = home / "runs" / "envelopes"
    directory.mkdir(parents=True, exist_ok=True)
    leaves = []
    for index in range(2):
        raw = _fixture_envelope(index)
        path = directory / f"frozen-receipt-{index}.json"
        require(not path.exists(), "RECEIPT_FIXTURE_COLLISION")
        path.write_bytes(raw)
        leaves.append(hashlib.sha256(raw).hexdigest())
    return leaves[1]


def _payload(result):
    require(isinstance(result, dict), "RECEIPT_MCP_RESULT_SHAPE")
    content = result.get("content")
    require(isinstance(content, list) and len(content) == 1
            and isinstance(content[0], dict)
            and content[0].get("type") == "text", "RECEIPT_MCP_CONTENT_SHAPE")
    try:
        value = json.loads(content[0]["text"])
    except (KeyError, TypeError, ValueError):
        raise RuntimeError("RECEIPT_MCP_CONTENT_SHAPE") from None
    require(isinstance(value, dict) and result.get("structuredContent") == value,
            "RECEIPT_CONTENT_DRIFT")
    return value


def validate_receipt_parity(responses: dict, http_proof: dict,
                            missing_root: str, requested_leaf: str) -> dict:
    require(set(responses) == {1, 2, 3, 4, 5}, "RECEIPT_MCP_RESPONSE_IDS")
    require(all(isinstance(value, dict) for value in responses.values()),
            "RECEIPT_MCP_RESPONSE_SHAPE")
    require(responses[1].get("protocolVersion") == "2025-06-18",
            "RECEIPT_MCP_PROTOCOL")
    tools = responses[2].get("tools")
    require(isinstance(tools, list), "RECEIPT_MCP_TOOL_SCHEMA")
    descriptors = [tool for tool in tools
                   if isinstance(tool, dict) and tool.get("name") == TOOL]
    require(len(descriptors) == 1, "RECEIPT_MCP_TOOL_MISSING")
    expected = mcp_tool_descriptors()[0]
    require(all(descriptors[0].get(key) == expected[key]
                for key in ("inputSchema", "outputSchema")), "RECEIPT_MCP_TOOL_SCHEMA")
    require(isinstance(missing_root, str)
            and re.fullmatch(r"[0-9a-f]{64}", missing_root), "RECEIPT_HTTP_MISSING_ROOT")
    require(isinstance(http_proof, dict) and http_proof.get("leaf") == requested_leaf,
            "RECEIPT_REQUEST_LEAF_MISMATCH")
    _validate_proof(http_proof)
    require(missing_root == http_proof["merkle_root"], "RECEIPT_LOG_ROOT_DRIFT")
    included = _payload(responses[3])
    require(responses[3].get("isError", False) is False
            and included.get("included") is True
            and included.get("status") == "included", "RECEIPT_MCP_NOT_INCLUDED")
    require(included.get("proof") == http_proof, "RECEIPT_TRANSPORT_DRIFT")
    verification = included.get("verification", {})
    require(isinstance(verification, dict) and verification.get("replayed") is True
            and verification.get("included") is True, "RECEIPT_MCP_NOT_REPLAYED")
    missing = _payload(responses[4])
    require(responses[4].get("isError", False) is False
            and missing.get("included") is False and missing.get("status") == "missing"
            and missing.get("proof") == {"leaf": MISSING_LEAF,
                                         "merkle_root": missing_root},
            "RECEIPT_MISSING_PROMOTED")
    malformed = _payload(responses[5])
    require(responses[5].get("isError") is True
            and isinstance(malformed.get("error"), dict)
            and malformed.get("error", {}).get("code") == "INVALID_LEAF",
            "RECEIPT_MALFORMED_ACCEPTED")
    return {"schema": "flywheel.frozen-receipt-parity/v1",
            "http_mcp_proof_equal": True,
            "missing_leaf_status": "missing", "malformed_leaf_code": "INVALID_LEAF",
            "proof_schema": http_proof.get("schema"),
            "tree_size": http_proof.get("tree_size"),
            "does_not_prove": ["semantic correctness", "evidence completeness",
                               "remote MCP interoperability"]}


def _validate_proof(proof):
    require(set(proof) == {"schema", "leaf", "index", "tree_size",
                           "merkle_root", "audit_path"}
            and proof.get("schema") == "flywheel.receipts-proof/v2",
            "RECEIPT_HTTP_PROOF_SHAPE")
    require(type(proof["index"]) is int and type(proof["tree_size"]) is int
            and 0 <= proof["index"] < proof["tree_size"], "RECEIPT_HTTP_PROOF_SHAPE")
    for value in (proof["leaf"], proof["merkle_root"]):
        require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value),
                "RECEIPT_HTTP_PROOF_SHAPE")
    require(isinstance(proof["audit_path"], list), "RECEIPT_HTTP_PROOF_SHAPE")
    for step in proof["audit_path"]:
        require(isinstance(step, dict) and set(step) == {"side", "hash"}
                and step["side"] in ("left", "right")
                and isinstance(step["hash"], str)
                and re.fullmatch(r"[0-9a-f]{64}", step["hash"]),
                "RECEIPT_HTTP_PROOF_SHAPE")
    require(verify_inclusion(proof["leaf"], proof["audit_path"], proof["merkle_root"]),
            "RECEIPT_HTTP_PROOF_INVALID")


def run_receipt_acceptance_smoke(executable: Path, home: Path, env: dict,
                                 base: str, token: str, leaf: str, request) -> dict:
    status, raw = request(base, "/api/receipts/proof?leaf=" + leaf, token)
    require(status == 200, "RECEIPT_HTTP_INCLUDED")
    http_proof = json.loads(raw)
    validate_fixture_proof(http_proof, leaf)
    status, raw = request(base, "/api/receipts/proof?leaf=" + MISSING_LEAF, token)
    require(status == 404, "RECEIPT_HTTP_MISSING")
    missing = json.loads(raw)
    require(missing.get("leaf") == MISSING_LEAF, "RECEIPT_HTTP_MISSING_SHAPE")
    status, _ = request(base, "/api/receipts/proof?leaf=short", token)
    require(status == 400, "RECEIPT_HTTP_MALFORMED")
    operations = [
        ("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "frozen-acceptance", "version": "1"}}),
        ("tools/list", {}),
        *[("tools/call", {"name": TOOL, "arguments": {"leaf": value}})
          for value in (leaf, MISSING_LEAF, "short")],
    ]
    wire = "".join(json.dumps({"jsonrpc": "2.0", "id": index,
                               "method": method, "params": params}) + "\n"
                   for index, (method, params) in enumerate(operations, 1))
    stdout = run_mcp_process(
        executable, ["--mcp", "--root", str(home),
                     "--run-root", str(home / "runs")], home, env, wire)
    require(token not in stdout, "RECEIPT_MCP_CREDENTIAL_ECHO")
    responses = {}
    for line in stdout.splitlines():
        try:
            item = json.loads(line)
            require(item.get("jsonrpc") == "2.0" and type(item.get("id")) is int
                    and item["id"] not in responses and isinstance(item.get("result"), dict),
                    "RECEIPT_MCP_RESPONSE_SHAPE")
            responses[item["id"]] = item["result"]
        except (ValueError, AttributeError) as exc:
            raise RuntimeError("RECEIPT_MCP_RESPONSE_SHAPE") from exc
    summary = validate_receipt_parity(
        responses, http_proof, missing.get("merkle_root"), leaf)
    summary["child_exit_code"] = 0
    summary["job_descendants_terminal"] = True
    return summary


def validate_fixture_proof(proof: dict, requested_leaf: str) -> None:
    # Independent two-leaf oracle: do not ask the server or its proof builder
    # what tree it was supposed to read. Bind size, ordering and sibling as well
    # as membership to the fixture prepared before launch.
    leaves = [hashlib.sha256(_fixture_envelope(index)).hexdigest()
              for index in range(2)]
    nodes = [hashlib.sha256(b"\x00" + bytes.fromhex(leaf)).digest()
             for leaf in leaves]
    expected = {"schema": "flywheel.receipts-proof/v2", "leaf": leaves[1],
                "index": 1, "tree_size": 2,
                "merkle_root": hashlib.sha256(b"\x01" + b"".join(nodes)).hexdigest(),
                "audit_path": [{"side": "left", "hash": nodes[0].hex()}]}
    require(requested_leaf == leaves[1] and proof == expected,
            "RECEIPT_FIXTURE_PROOF_MISMATCH")
