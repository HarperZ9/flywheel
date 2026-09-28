"""Read-only receipt inclusion operation shared by MCP-facing surfaces."""
from __future__ import annotations

from typing import Callable

from .agent_tools import dispatch
from .receipt_proof import LeafNotFound, build_receipt_proof
from .transparency_log import merkle_root, verify_inclusion

SCHEMA = "flywheel.receipt-operations/v1"
TOOL_NAME = "receipt.verify_inclusion"
VERIFY_METHOD = "harness.transparency_log.verify_inclusion"
DOES_NOT_PROVE = (
    "receipt-log membership/hash proof does not prove semantic correctness",
    "receipt-log membership/hash proof does not prove evidence completeness",
)


class ReceiptOperationError(ValueError):
    """A typed transport error for read-only receipt operations."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def mcp_tool_descriptors() -> list[dict]:
    return [{
        "name": TOOL_NAME,
        "description": (
            "Verify that a 64-hex receipt envelope digest is a member of "
            "the ordered receipts Merkle log. Returns replayable proof data; "
            "it does not approve, mutate, or judge receipt semantics."),
        "inputSchema": {
            "type": "object",
            "required": ["leaf"],
            "additionalProperties": False,
            "properties": {
                "leaf": {
                    "type": "string",
                    "description": "lowercase 64-hex sha256 envelope digest",
                },
            },
            "x-flywheel-operation-schema": SCHEMA,
        },
        "outputSchema": _output_schema(),
        "x-flywheel-operation-schema": SCHEMA,
        "x-flywheel-transport-availability": {
            "mcp": {"available": True, "custody": "local-stdio",
                    "payload": "json-object"},
            "http": {"available": True, "custody": "gateway-configured",
                     "auth_policy": (
                         "gateway handler auth applies when configured; "
                         "route is not private-custody"),
                     "payload": "query-string",
                     "path": "/api/receipts/proof?leaf=<sha256>"},
        },
    }]


def verify_receipt_inclusion(args: object, *,
                             ledger: Callable[[], dict]) -> dict:
    leaf = _leaf_from_args(args)
    try:
        ledger_snapshot = ledger()
        leaves = [e["sha256"] for e in ledger_snapshot.get("envelopes", [])]
        result = dispatch("verify_receipt_inclusion", {"leaf": leaf},
                          ledger=lambda **_: ledger_snapshot)
    except Exception as exc:
        raise ReceiptOperationError(
            "RECEIPTS_LEDGER_UNAVAILABLE",
            "the receipts ledger could not be read") from exc
    if type(result) is not dict:
        raise ReceiptOperationError(
            "RECEIPTS_LEDGER_UNAVAILABLE",
            "the receipts ledger could not be read")
    if "error" in result:
        if "64-hex" in result["error"]:
            raise ReceiptOperationError(
                "INVALID_LEAF", "leaf must be a 64-hex sha256 digest")
        raise ReceiptOperationError(
            "RECEIPTS_LEDGER_UNAVAILABLE",
            "the receipts ledger could not be read")
    if result.get("included") is True:
        return _included(leaf, leaves, result.get("proof", {}))
    if result.get("included") is False:
        return _missing(leaf, leaves, result.get("proof", {}))
    raise ReceiptOperationError(
        "RECEIPTS_LEDGER_UNAVAILABLE",
        "the receipts ledger could not be read")


def _leaf_from_args(args: object) -> str:
    if type(args) is not dict:
        raise ReceiptOperationError(
            "INVALID_ARGUMENTS", "arguments must be an object")
    extra = set(args) - {"leaf"}
    if extra:
        raise ReceiptOperationError(
            "UNKNOWN_FIELD", "request contains unsupported fields")
    if "leaf" not in args:
        raise ReceiptOperationError(
            "MISSING_FIELD", "request is missing required fields")
    leaf = args["leaf"]
    if (type(leaf) is not str or len(leaf) != 64
            or any(c not in "0123456789abcdef" for c in leaf)):
        raise ReceiptOperationError(
            "INVALID_LEAF", "leaf must be a 64-hex sha256 digest")
    return leaf


def _included(requested_leaf: str, leaves: list, proof: object) -> dict:
    if type(proof) is not dict:
        return _not_included("proof_corrupt", {}, "proof did not replay",
                             replayed=False)
    try:
        expected = build_receipt_proof(requested_leaf, leaves)
    except LeafNotFound:
        return _not_included("proof_corrupt", proof,
                             "proof object does not match ledger",
                             replayed=False)
    if proof.get("leaf") != requested_leaf:
        try:
            foreign = build_receipt_proof(proof.get("leaf"), leaves)
        except Exception:
            return _not_included(
                "proof_corrupt", proof,
                "proof object does not match ledger", replayed=False)
        if proof != foreign:
            return _not_included(
                "proof_corrupt", proof,
                "proof object does not match ledger", replayed=False)
        return _not_included(
            "proof_leaf_mismatch", proof,
            "proof leaf does not match requested leaf", replayed=True)
    replayed = verify_inclusion(
        requested_leaf, proof.get("audit_path"), proof.get("merkle_root"))
    if not replayed:
        return _not_included(
            "proof_corrupt", proof, "proof did not replay", replayed=True)
    if proof != expected:
        return _not_included(
            "proof_corrupt", proof, "proof object does not match ledger",
            replayed=True)
    return {
        "included": True,
        "status": "included",
        "proof": expected,
        "verification": {
            "method": VERIFY_METHOD,
            "replayed": True,
            "included": bool(replayed),
        },
        "does_not_prove": list(DOES_NOT_PROVE),
    }


def _missing(leaf: str, leaves: list, proof: dict) -> dict:
    proof = proof if type(proof) is dict else {}
    expected_root = merkle_root(leaves) if leaves else ""
    expected = {"leaf": leaf, "merkle_root": expected_root}
    if proof != expected:
        return _not_included(
            "proof_corrupt", proof,
            "provider returned failed proof material", replayed=False)
    return {
        "included": False,
        "status": "missing",
        "proof": expected,
        "reason": "leaf not in the receipts log",
        "verification": {
            "method": VERIFY_METHOD,
            "replayed": False,
            "included": False,
        },
        "does_not_prove": list(DOES_NOT_PROVE),
    }


def _not_included(status: str, proof: dict, reason: str, *,
                  replayed: bool) -> dict:
    return {
        "included": False,
        "status": status,
        "proof": proof,
        "reason": reason,
        "verification": {
            "method": VERIFY_METHOD,
            "replayed": replayed,
            "included": False,
        },
        "does_not_prove": list(DOES_NOT_PROVE),
    }


def _output_schema() -> dict:
    proof_v2 = {
        "type": "object",
        "required": [
            "schema", "leaf", "index", "tree_size",
            "merkle_root", "audit_path"],
        "additionalProperties": False,
        "properties": {
            "schema": {"const": "flywheel.receipts-proof/v2"},
            "leaf": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "index": {"type": "integer", "minimum": 0},
            "tree_size": {"type": "integer", "minimum": 1},
            "merkle_root": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "audit_path": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["hash", "side"],
                    "additionalProperties": False,
                    "properties": {
                        "hash": {
                            "type": "string",
                            "pattern": "^[0-9a-f]{64}$"},
                        "side": {"type": "string",
                                 "enum": ["left", "right"]},
                    },
                },
            },
        },
    }
    missing_proof = {
        "type": "object",
        "required": ["leaf", "merkle_root"],
        "additionalProperties": False,
        "properties": {
            "leaf": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "merkle_root": {"type": "string",
                            "pattern": "^(|[0-9a-f]{64})$"},
        },
    }
    verification = {
        "type": "object",
        "required": ["method", "replayed", "included"],
        "additionalProperties": False,
        "properties": {
            "method": {"const": VERIFY_METHOD},
            "replayed": {"type": "boolean"},
            "included": {"type": "boolean"},
        },
    }
    base_props = {
        "does_not_prove": {
            "type": "array",
            "items": {"type": "string"},
        },
        "verification": verification,
    }
    included_case = {
        "type": "object",
        "required": [
            "included", "status", "proof",
            "verification", "does_not_prove"],
        "additionalProperties": False,
        "properties": {
            "included": {"const": True},
            "status": {"const": "included"},
            "proof": proof_v2,
            **base_props,
        },
    }
    def not_included_case(status: str, proof_schema: dict) -> dict:
        return {
            "type": "object",
            "required": [
                "included", "status", "proof", "reason",
                "verification", "does_not_prove"],
            "additionalProperties": False,
            "properties": {
                "included": {"const": False},
                "status": {"const": status},
                "proof": proof_schema,
                "reason": {"type": "string"},
                **base_props,
            },
        }

    return {
        "type": "object",
        "required": [
            "included", "status", "proof", "verification", "does_not_prove"],
        "oneOf": [
            included_case,
            not_included_case("missing", missing_proof),
            not_included_case("proof_corrupt", {"type": "object"}),
            not_included_case("proof_leaf_mismatch", proof_v2),
        ],
        "x-flywheel-operation-schema": SCHEMA,
    }
