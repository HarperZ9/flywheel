"""tool_call_receipt.py -- sealed, content-addressed receipt per agent tool call.

Extends the model-boundary-receipt discipline to every tool invocation in the
agent loop. Each call through ToolExecutor.execute() emits one sealed JSON
receipt binding the tool name, the capability class (what the tool was allowed
to touch), the admission decision (ALLOWED / BLOCKED / ESCALATED), the args and
output as witnessed sha256 digests (never raw content), the outcome, and a
chain link to the prior receipt. A third party re-walks the whole action chain
offline, verifying each seal and the chain linkage.

This is the enforced AgentRiskBOM primitive: each receipt answers "what was the
system allowed to do?" (capability / admission), "what did it actually do?"
(witnessed args / output digests), and "can a stranger re-walk it?" (sealed,
chain-linked, offline-verifiable).

Cross-language contract (mirrors buildlang's model-boundary-receipt exactly so
buildc receipt verify can read it):
  - fixed schema field order (NOT sort_keys); Python insertion order == Rust struct order
  - no floats anywhere (booleans serialized as "true"/"false" strings)
  - compact separators (",", ":"); ensure_ascii=False
  - seal: blank seal.hex="", fix seal.algorithm="sha256", hash the canonical bytes
  - top-level schema + seal so chain pointers /schema and /seal/hex work unchanged

Capability vocabulary adapted from ORCA's CapabilityManifest / ResourceRequirement
(builtin-read, builtin-write, builtin-exec, external-mcp). Content-addressing
discipline adapted from EMET's witness_receipt (the identity/seal block is part
of the sealed body but blanked before hashing, so the seal binds the witnessed
facts without self-reference).

Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

SCHEMA = "flywheel.tool-call-receipt/v1"
SHIM_VERSION = "0.1.0"

# Admission outcomes (mirrors the ToolGate decision vocabulary).
COMPLETED = "COMPLETED"
BLOCKED = "BLOCKED"
ERROR = "ERROR"

# Capability classes (adapted from ORCA CapabilityManifest resource requirements).
CAPABILITY_CLASSES = frozenset(
    {"builtin-read", "builtin-write", "builtin-exec", "external-mcp", "unknown"}
)

_HEX64 = frozenset("0123456789abcdef")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_hex64(s: str) -> bool:
    return len(s) == 64 and all(c in _HE64 for c in s) if (s) else False

_HE64 = frozenset("0123456789abcdefABCDEF")


def _digest_well_formed(s: str) -> bool:
    return len(s) == 64 and all(c in _HE64 for c in s)


def _canonical_bytes(receipt: dict[str, Any]) -> bytes:
    """The canonical JSON byte form: compact, UTF-8, ensure_ascii=False, fixed order.

    Matches Rust serde_json::to_vec byte-for-byte when the dict is built in the
    schema's fixed field order and contains no floats.
    """
    return json.dumps(receipt, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _seal_receipt(receipt: dict[str, Any]) -> None:
    """Seal a receipt in place: blank seal.hex, fix algorithm, hash canonical bytes.

    Mutates seal.hex in place (not reassign) so the seal key's already-correct
    position in the fixed-order dict is preserved regardless of call order --
    same idiom as model_shim.py.
    """
    receipt["seal"]["algorithm"] = "sha256"
    receipt["seal"]["hex"] = ""
    canonical = _canonical_bytes(receipt)
    receipt["seal"]["hex"] = _sha256_hex(canonical)


# --- emission ---------------------------------------------------------------


def build_receipt(
    *,
    tool: str,
    capability: str,
    admission: str,
    args: Any,
    output: str,
    ok: bool,
    rc: int,
    run_id: str,
    seq: int,
    prev_receipt_sha256: str = "",
    outcome: str = COMPLETED,
    rationale: dict[str, Any] | None = None,
    session_token_ref: str | None = None,
    sandbox: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a sealed tool-call receipt dict from the witnessed call facts.

    ``args`` and ``output`` are hashed (sha256 + byte count); the receipt never
    carries raw content. The receipt is built in the fixed schema field order
    so the canonical form is stable across Python/Rust.

    ``rationale`` is optional and null by default (honest null). When present,
    it carries the typed decision-rationale block: ``{stated_intent,
    options_considered, chosen_option, confidence}``. The block is sealed into
    the receipt, so the rationale is re-verifiable, not asserted. A receipt
    without rationale is byte-identical to a receipt built before this field
    existed (backward-compatible: the field is absent, not null-padded).
    ``session_token_ref`` and ``sandbox`` follow the same honest-null pattern.
    """
    args_bytes = json.dumps(args, sort_keys=True, ensure_ascii=False).encode("utf-8") if args else b""
    output_bytes = (output or "").encode("utf-8")
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "source": f"tool:{run_id}:{seq}",
        "tool": tool,
        "capability": capability if capability in CAPABILITY_CLASSES else "unknown",
        "admission": admission,
        "args": {"sha256": _sha256_hex(args_bytes), "bytes": len(args_bytes)},
        "output": {"sha256": _sha256_hex(output_bytes), "bytes": len(output_bytes)},
        "ok": "true" if ok else "false",
        "rc": rc if isinstance(rc, int) else 0,
        "run_id": run_id,
        "seq": seq,
        "prev_receipt_sha256": prev_receipt_sha256,
        "outcome": outcome,
        "seal": {"algorithm": "sha256", "hex": ""},
    }
    # Rationale is optional. When present, it is inserted before the seal block
    # so it is part of the sealed body. Absent rationale keeps the receipt
    # byte-identical to the pre-rationale schema (backward-compatible).
    if rationale is not None:
        receipt["rationale"] = _normalize_rationale(rationale)
    if session_token_ref is not None:
        receipt["session_token_ref"] = str(session_token_ref)
    if sandbox is not None:
        receipt["sandbox"] = {"kind": str(sandbox.get("kind", "unknown")),
                               "integrity_level": str(sandbox.get("integrity_level", "unknown"))}
    _seal_receipt(receipt)
    return receipt


# The typed rationale block. Each field is a string (no floats in the schema).
_RATIONALE_FIELDS = ("stated_intent", "options_considered", "chosen_option", "confidence")


def _normalize_rationale(rationale: dict[str, Any]) -> dict[str, Any]:
    """Normalize a rationale dict to the fixed schema shape.

    options_considered is a list of strings. The rest are strings. Unknown
    fields are dropped (additionalProperties: false, same discipline as the
    organ-bundle spine).
    """
    if not isinstance(rationale, dict):
        raise ValueError("rationale must be a dict or None")
    normalized: dict[str, Any] = {}
    for field in _RATIONALE_FIELDS:
        val = rationale.get(field)
        if field == "options_considered":
            if isinstance(val, list):
                normalized[field] = [str(v) for v in val]
            elif val is None:
                normalized[field] = []
            else:
                normalized[field] = [str(val)]
        else:
            normalized[field] = str(val) if val is not None else ""
    return normalized


def emit_receipt(receipt: dict[str, Any], receipt_dir: Path, *, nonce: str = "") -> Path | None:
    """Write one sealed receipt to ``receipt_dir``. Never raises.

    Any failure (bad dir, permission) is logged to stderr and swallowed --
    emission must never block or break the tool-call path. Returns the path
    written, or None on failure. Same idiom as model_shim._emit_receipt.
    """
    try:
        receipt_dir.mkdir(parents=True, exist_ok=True)
        seq = receipt.get("seq", 0)
        tool = receipt.get("tool", "unknown")
        suffix = nonce or os.urandom(4).hex()
        filename = f"tool-receipt-{seq:04d}-{tool}-{suffix}.json"
        path = receipt_dir / filename
        path.write_text(
            json.dumps(receipt, separators=(",", ":"), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path
    except Exception as exc:  # noqa: BLE001 -- emission must never break the call path
        print(f"tool-call-receipt: emission failed (non-fatal): {exc}", file=sys.stderr)
        return None


# --- verification -----------------------------------------------------------

MATCH = "MATCH"
TAMPERED = "TAMPERED"
UNVERIFIABLE = "UNVERIFIABLE"


def verify_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Offline re-verification of one tool-call receipt.

    Returns ``{schema, verdict, failure_class, detail}``. Reuses the shared
    failure taxonomy (MALFORMED, SEAL_MISMATCH, DIGEST_MALFORMED,
    FIELD_CONTRACT_VIOLATION). The seal is checked FIRST, before any sealed
    field is interpreted.
    """
    if not isinstance(receipt, dict):
        return _fail("MALFORMED", "receipt is not a JSON object")

    if receipt.get("schema") != SCHEMA:
        return _fail("MALFORMED", f"schema is {receipt.get('schema')!r}, expected {SCHEMA}")

    seal = receipt.get("seal")
    if not isinstance(seal, dict) or seal.get("algorithm") != "sha256":
        return _fail("MALFORMED", "seal missing or algorithm is not sha256")
    stored_hex = seal.get("hex", "")
    if not _digest_well_formed(stored_hex):
        return _fail("DIGEST_MALFORMED", "seal.hex is not a 64-char hex digest")

    # Seal check FIRST (before interpreting any sealed field).
    probe = dict(receipt)
    probe["seal"] = {"algorithm": "sha256", "hex": ""}
    recomputed = _sha256_hex(_canonical_bytes(probe))
    if recomputed != stored_hex:
        return _fail(
            "SEAL_MISMATCH",
            f"seal sha256:{stored_hex[:12]}, recomputed sha256:{recomputed[:12]}",
        )

    # Digest well-formedness for witnessed fields.
    for field in ("args", "output"):
        block = receipt.get(field)
        if not isinstance(block, dict):
            return _fail("FIELD_CONTRACT_VIOLATION", f"{field} is not an object")
        sha = block.get("sha256", "")
        if not _digest_well_formed(sha):
            return _fail("DIGEST_MALFORMED", f"{field}.sha256 is not a 64-char hex digest")
        byte_count = block.get("bytes")
        if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 0:
            return _fail("FIELD_CONTRACT_VIOLATION", f"{field}.bytes is not a non-negative integer")

    prev = receipt.get("prev_receipt_sha256", "")
    if prev and not _digest_well_formed(prev):
        return _fail("DIGEST_MALFORMED", "prev_receipt_sha256 is not a 64-char hex digest")

    # Field coherence: outcome vs ok vs output.
    outcome = receipt.get("outcome", "")
    ok_str = receipt.get("ok", "")
    if outcome == COMPLETED and ok_str != "true":
        return _fail("FIELD_CONTRACT_VIOLATION", "outcome COMPLETED but ok is not true")
    if outcome == BLOCKED and ok_str != "false":
        return _fail("FIELD_CONTRACT_VIOLATION", "outcome BLOCKED but ok is not false")

    # Optional rationale block: if present, it must be a dict with exactly the
    # typed fields. The seal already bound it (checked first), so this is a
    # structural check, not a re-seal.
    rationale = receipt.get("rationale")
    if rationale is not None:
        if not isinstance(rationale, dict):
            return _fail("FIELD_CONTRACT_VIOLATION", "rationale is present but not an object")
        if set(rationale.keys()) != set(_RATIONALE_FIELDS):
            return _fail(
                "FIELD_CONTRACT_VIOLATION",
                f"rationale fields {set(rationale.keys())} != {_RATIONALE_FIELDS}",
            )
        if not isinstance(rationale.get("options_considered"), list):
            return _fail("FIELD_CONTRACT_VIOLATION", "rationale.options_considered is not a list")

    result = {
        "schema": SCHEMA,
        "verdict": MATCH,
        "source": receipt.get("source", ""),
        "outcome": outcome,
        "seal": {"algorithm": "sha256", "hex": stored_hex},
    }
    if rationale is not None:
        result["has_rationale"] = True
    return result


def _fail(failure_class: str, detail: str) -> dict[str, Any]:
    verdict = TAMPERED if failure_class == "SEAL_MISMATCH" else UNVERIFIABLE
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "failure_class": failure_class,
        "detail": detail,
    }


def verify_chain(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify a chain of tool-call receipts: each seal + chain linkage.

    Each receipt's prev_receipt_sha256 must equal the sha256 of the prior
    receipt's canonical sealed bytes (or empty for the first). Returns a
    summary with per-receipt verdicts and an overall verdict (MATCH only if
    every receipt verifies AND the chain links hold).
    """
    if not receipts:
        return {"verdict": UNVERIFIABLE, "detail": "empty chain", "receipts": []}

    results: list[dict[str, Any]] = []
    chain_ok = True
    expected_prev = ""
    for i, receipt in enumerate(receipts):
        v = verify_receipt(receipt)
        if v.get("verdict") != MATCH:
            chain_ok = False
            results.append(v)
            continue
        # chain linkage
        actual_prev = receipt.get("prev_receipt_sha256", "")
        if actual_prev != expected_prev:
            chain_ok = False
            results.append({**v, "verdict": TAMPERED, "failure_class": "CHAIN_BROKEN",
                            "detail": f"prev link mismatch at seq {i}"})
        else:
            results.append(v)
        # compute the next expected prev: canonical sha256 of this receipt
        probe = dict(receipt)
        probe["seal"] = {"algorithm": "sha256", "hex": ""}
        expected_prev = _sha256_hex(_canonical_bytes(probe))

    return {
        "verdict": MATCH if chain_ok else TAMPERED,
        "n": len(receipts),
        "receipts": results,
    }
