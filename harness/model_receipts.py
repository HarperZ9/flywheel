"""model_receipts.py: model boundary receipt construction, sealing, emission.

Split out of model_shim.py (which holds the wire protocol and serving loop)
so each file stays under the repo's 300-line gate. `--receipt-dir PATH` on
the shim (v1.1 of the shim contract) routes here: one sealed
`buildlang-model-boundary-receipt/v0` JSON per connection -- a provenance
artifact witnessing the exact bytes that crossed the boundary, never the
model's quality or weights. No flag, no receipt: behavior on the wire is
byte-identical to before this feature existed either way.

Contract source: buildlang's docs/MODEL-RECEIPT.md and
docs/superpowers/specs/2026-07-29-model-boundary-receipts-design.md. The seal
is sha256 over the compact-JSON canonical body with `seal.hex` blanked,
computed to be byte-identical to buildlang's Rust sealer (same field order,
same compact separators, no floats anywhere in the schema) -- see
`seal_receipt` and the golden fixture pinned in both repos
(tests/fixtures/model-receipt-golden.json here, compiler/tests/fixtures of
the same name in buildlang). Receipt emission never raises: any failure (a
bad directory, a permission error) is logged to stderr and swallowed,
because it must never block or break the reply path (see `emit_receipt`).
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# SHIM_VERSION is sealed into every receipt's `shim.version` field and is
# pinned by the golden fixture in both repos -- changing it changes the golden
# fixture's seal, so it must not be bumped without re-deriving that fixture in
# lockstep with buildlang.
MODEL_RECEIPT_SCHEMA = "buildlang-model-boundary-receipt/v0"
SHIM_VERSION = "0.1.0"
ECHO_MODEL_NAME = "echo/v1"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hashed_bytes(data: bytes) -> dict:
    """`{ sha256, bytes }` over raw bytes -- the receipt's `prompt`/`reply`
    shape. `bytes` is a byte COUNT, never content: the receipt carries no
    plaintext (docs/MODEL-RECEIPT.md's deliberate exclusions)."""
    return {"sha256": sha256_hex(data), "bytes": len(data)}


def seal_receipt(receipt: dict) -> str:
    """Seal a receipt dict IN PLACE: sha256 over the canonical JSON with
    `seal.hex` blanked and `seal.algorithm` fixed to `"sha256"`. Returns the
    computed hex.

    This is the Python half of the cross-language canonicalization contract
    (docs/MODEL-RECEIPT.md in buildlang): compact separators (no whitespace,
    matching `serde_json::to_vec`), object keys in the schema's FIXED order
    (Python dicts preserve insertion order; the receipt dict is always built
    with keys inserted in that order -- see `emit_receipt`), non-ASCII
    unescaped (`ensure_ascii=False`, matching serde_json's default), and no
    floats anywhere in the schema, which is what makes this agree byte-for-
    byte with the Rust sealer despite being two different JSON libraries.
    Mutates `receipt["seal"]` in place (rather than reassigning the `seal`
    key) so the key's ALREADY-CORRECT position in insertion order is
    preserved regardless of call order.
    """
    receipt["seal"]["algorithm"] = "sha256"
    receipt["seal"]["hex"] = ""
    canonical = json.dumps(receipt, separators=(",", ":"), ensure_ascii=False)
    hex_digest = sha256_hex(canonical.encode("utf-8"))
    receipt["seal"]["hex"] = hex_digest
    return hex_digest


def build_model_block(mode: str, model: str, endpoint: str,
                      request_body_sha256: str | None = None,
                      daemon_digest: dict | None = None) -> dict:
    """The receipt's `model` block. Echo mode carries only `name` (the three
    ollama-only keys are OMITTED, not null, on an echo receipt). For ollama,
    `request_body_sha256`/`daemon_digest` are each included only when a value
    was actually computed (never for a PROTOCOL_VIOLATION, where no request
    was ever constructed or sent -- there is nothing honest to claim)."""
    if mode == "echo":
        return {"name": ECHO_MODEL_NAME}
    block = {"name": model, "endpoint": endpoint}
    if request_body_sha256 is not None:
        block["request_body_sha256"] = request_body_sha256
    if daemon_digest is not None:
        block["daemon_digest"] = daemon_digest
    return block


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_compact_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def emit_receipt(receipt_dir: str, *, mode: str, model: str, endpoint: str,
                 listen: str, shim_version: str, nonce: str,
                 request_received_utc: str, reply_written_utc: str | None,
                 prompt_raw: bytes | None, reply_bytes: bytes | None,
                 outcome: str, request_body_sha256: str | None = None,
                 daemon_digest: dict | None = None) -> None:
    """Build, seal, and write one model boundary receipt to `receipt_dir`.

    Never raises. Any failure here (a missing/unwritable directory, a
    serialization bug) is logged to stderr and swallowed: emission is
    opt-in and additive, so it must never block or break the reply path
    (the reply, when there is one, has already been sent to the client by
    the time this is called -- see `handle_connection` in model_shim).
    """
    try:
        name_for_source = ECHO_MODEL_NAME if mode == "echo" else model
        receipt: dict = {
            "schema": MODEL_RECEIPT_SCHEMA,
            "source": f"model:{mode}:{name_for_source}",
            "shim": {"name": "model_shim.py", "version": shim_version, "mode": mode},
            "session": {
                "listen": listen,
                "nonce": nonce,
                "request_received_utc": request_received_utc,
                "reply_written_utc": reply_written_utc,
            },
            "prompt": hashed_bytes(prompt_raw) if prompt_raw is not None else None,
            "reply": hashed_bytes(reply_bytes) if reply_bytes is not None else None,
            "model": build_model_block(mode, model, endpoint, request_body_sha256,
                                       daemon_digest),
            "seed": {"status": "NOT_SENT"},
            "outcome": outcome,
            "seal": {"algorithm": "sha256", "hex": ""},
        }
        seal_receipt(receipt)

        receipt_dir_path = Path(receipt_dir)
        receipt_dir_path.mkdir(parents=True, exist_ok=True)
        path = receipt_dir_path / f"model-receipt-{utc_compact_stamp()}-{nonce}.json"
        path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    except Exception as e:  # fail-closed: receipt emission must never crash
        print(f"[model_shim] receipt emission failed: {e!r}", file=sys.stderr)
