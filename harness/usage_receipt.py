"""usage_receipt.py -- the sealed, offline-verifiable USAGE-METERING receipt.

Every answer costs something, and a stranger should be able to re-check what it
cost. Peer CLIs either show a locally computed dollar ESTIMATE their own docs
disclaim (Cline/Roo/Aider) or show nothing in the terminal (Codex CLI); none
sign or attest usage. This binds the PROVIDER-REPORTED token counts and the
model reference into a sealed receipt a stranger re-verifies offline, and it is
honest about which number is which: the tokens are provider-reported when the
provider returned a usage object (else an explicit estimate), and the dollar
amount is always a table lookup, never a provider-billed figure.

This does NOT reinvent the seal. It reuses tool_call_receipt.py's discipline
verbatim: fixed field order (NOT sort_keys), no floats anywhere (token counts as
DIGIT STRINGS, money as decimal STRINGS), and the blanked-seal canonical-bytes
hash. A receipt chains to a prior by prev_receipt_sha256 = the prior receipt's
seal hex (equivalently its blanked-seal canonical recompute).

Standard library only, and free of any version-gated feature so the verifier
path stays portable for a stranger to re-run (the verifier-closure floor gate in
tests/test_python_floor.py enforces exactly that, which is why nothing here
imports a datetime feature or names a version-gated token). Timestamps arrive as
strings from the caller; this module never reads a clock.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .tool_call_receipt import (
    MATCH,
    TAMPERED,
    UNVERIFIABLE,
    _canonical_bytes,
    _digest_well_formed,
    _seal_receipt,
    _sha256_hex,
)

SCHEMA = "flywheel.usage-receipt/v1"

# The token-provenance / cost-provenance label. One word, so a reader knows
# exactly how the numbers were obtained without reading prose:
#   provider_reported -- the provider returned a usage object AND a price entry
#                        exists (tokens reported, dollar from the table)
#   estimated         -- at least one number is an estimate (the provider gave no
#                        usage, or there is no price entry for a non-local model)
#   unpriced_local    -- a local endpoint with no per-token charge: no dollar
#                        figure is recorded (amount is empty), never invented
SOURCE_LABELS = frozenset({"provider_reported", "estimated", "unpriced_local"})

# The token field order (fixed). All three are non-negative DIGIT STRINGS.
_TOKEN_FIELDS = ("prompt", "completion", "total")
# The cost field order (fixed). Every value is a STRING; an empty amount means no
# dollar figure was recorded, and the note always names the dollar's provenance.
_COST_FIELDS = ("amount", "currency", "per_million_input", "per_million_output", "note")


def _digit_str(v: Any) -> str:
    """A token count as a non-negative digit string. A negative or non-integer
    input clamps to '0' rather than smuggling a float or a sign into the body."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return "0"
    return str(n) if n >= 0 else "0"


def _normalize_tokens(tokens: Any) -> dict[str, str]:
    """Down to exactly {prompt, completion, total} as digit strings. total is
    taken from the input when present, else prompt+completion -- but the verifier
    re-checks the arithmetic, so a wrong total cannot pass."""
    t = tokens if isinstance(tokens, dict) else {}
    prompt = _digit_str(t.get("prompt", 0))
    completion = _digit_str(t.get("completion", 0))
    if "total" in t:
        total = _digit_str(t.get("total"))
    else:
        total = str(int(prompt) + int(completion))
    return {"prompt": prompt, "completion": completion, "total": total}


def _normalize_cost(cost: Any) -> dict[str, str]:
    """Down to exactly the fixed cost fields, every value a string. An empty
    amount is honest: it means no dollar figure was recorded (a local endpoint
    with no per-token charge, or a model with no price entry). The note always
    carries the dollar's provenance so the figure is never read as provider-billed."""
    c = cost if isinstance(cost, dict) else {}
    return {
        "amount": str(c.get("amount", "")),
        "currency": str(c.get("currency", "")),
        "per_million_input": str(c.get("per_million_input", "")),
        "per_million_output": str(c.get("per_million_output", "")),
        "note": str(c.get("note", "")),
    }


def build_usage_receipt(
    *,
    run_id: str,
    endpoint: str,
    model_ref: str,
    tokens: Any,
    cost: Any,
    source: str,
    started_utc: str,
    finished_utc: str,
    prev_receipt_sha256: str = "",
) -> dict[str, Any]:
    """Build a sealed usage-metering receipt in the fixed schema field order.

    ``tokens`` becomes {prompt, completion, total} digit strings; ``cost`` becomes
    the fixed cost block, all strings, with an empty amount when there is no price.
    ``source`` is one of SOURCE_LABELS. ``prev_receipt_sha256`` chains this receipt
    onto the route receipt whose spend it meters. The seal is the shared blanked-
    seal canonical-bytes hash, so a stranger re-checks it with the discipline every
    other receipt in the system uses. No floats anywhere in the body.
    """
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "run_id": str(run_id),
        "endpoint": str(endpoint),
        "model_ref": str(model_ref),
        "tokens": _normalize_tokens(tokens),
        "cost": _normalize_cost(cost),
        "source": str(source),
        "started_utc": str(started_utc),
        "finished_utc": str(finished_utc),
        "prev_receipt_sha256": str(prev_receipt_sha256 or ""),
        "seal": {"algorithm": "sha256", "hex": ""},
    }
    _seal_receipt(receipt)
    return receipt


def _fail(failure_class: str, detail: str) -> dict[str, Any]:
    """A tamper of the sealed body is TAMPERED; anything else the verifier cannot
    stand behind is UNVERIFIABLE. Same taxonomy split as every other receipt
    family, so a caller reads one vocabulary across the whole system."""
    verdict = TAMPERED if failure_class == "SEAL_MISMATCH" else UNVERIFIABLE
    return {"schema": SCHEMA, "verdict": verdict,
            "failure_class": failure_class, "detail": detail}


def verify_usage_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Offline re-verification. Returns {verdict, failure_class, detail}.

    The checks run in the only safe order: SCHEMA first (a foreign object is
    refused before any field is trusted), then the SEAL (no sealed field is
    interpreted until the seal is proven), then digest well-formedness of the
    chain pointer, then the field contracts: tokens are digit strings, total ==
    prompt + completion, source is a known label, and every cost field is a
    string. A single flipped hex character anywhere in the sealed body fails the
    seal -- that refusal is what the whole surface stands on. Import-clean stdlib.
    """
    if not isinstance(receipt, dict):
        return _fail("MALFORMED", "receipt is not a JSON object")
    if receipt.get("schema") != SCHEMA:
        return _fail("MALFORMED",
                     f"schema is {receipt.get('schema')!r}, expected {SCHEMA}")

    # --- seal first -----------------------------------------------------------
    seal = receipt.get("seal")
    if not isinstance(seal, dict) or seal.get("algorithm") != "sha256":
        return _fail("MALFORMED", "seal missing or algorithm is not sha256")
    stored_hex = seal.get("hex", "")
    if not _digest_well_formed(stored_hex):
        return _fail("DIGEST_MALFORMED", "seal.hex is not a 64-char hex digest")
    probe = dict(receipt)
    probe["seal"] = {"algorithm": "sha256", "hex": ""}
    recomputed = _sha256_hex(_canonical_bytes(probe))
    if recomputed != stored_hex:
        return _fail("SEAL_MISMATCH",
                     f"seal sha256:{stored_hex[:12]}, "
                     f"recomputed sha256:{recomputed[:12]}")

    # --- digest well-formedness ----------------------------------------------
    prev = receipt.get("prev_receipt_sha256", "")
    if prev and not _digest_well_formed(prev):
        return _fail("DIGEST_MALFORMED",
                     "prev_receipt_sha256 is not a 64-char hex digest")

    # --- field contracts: tokens ---------------------------------------------
    tokens = receipt.get("tokens")
    if not isinstance(tokens, dict) or set(tokens.keys()) != set(_TOKEN_FIELDS):
        return _fail("FIELD_CONTRACT_VIOLATION",
                     f"tokens fields != {_TOKEN_FIELDS}")
    for f in _TOKEN_FIELDS:
        v = tokens.get(f)
        if not (isinstance(v, str) and v.isdecimal()):
            return _fail("FIELD_CONTRACT_VIOLATION",
                         f"tokens.{f} is not a non-negative digit string")
    if int(tokens["total"]) != int(tokens["prompt"]) + int(tokens["completion"]):
        return _fail("FIELD_CONTRACT_VIOLATION",
                     f"tokens.total {tokens['total']} != prompt "
                     f"{tokens['prompt']} + completion {tokens['completion']}")

    # --- field contracts: source ---------------------------------------------
    if not isinstance(receipt.get("source"), str) or receipt.get("source") not in SOURCE_LABELS:
        return _fail("FIELD_CONTRACT_VIOLATION",
                     f"source {receipt.get('source')!r} is not a known label")

    # --- field contracts: cost (every value a string, no floats) -------------
    cost = receipt.get("cost")
    if not isinstance(cost, dict) or set(cost.keys()) != set(_COST_FIELDS):
        return _fail("FIELD_CONTRACT_VIOLATION", f"cost fields != {_COST_FIELDS}")
    for f in _COST_FIELDS:
        if not isinstance(cost.get(f), str):
            return _fail("FIELD_CONTRACT_VIOLATION",
                         f"cost.{f} is not a string")

    return {
        "schema": SCHEMA,
        "verdict": MATCH,
        "failure_class": "",
        "detail": f"{tokens['total']} tokens, source {receipt.get('source')}; "
                  f"chained to sha256:{prev[:12] if prev else '(none)'}",
        "run_id": receipt.get("run_id", ""),
        "endpoint": receipt.get("endpoint", ""),
        "source": receipt.get("source", ""),
        "seal": {"algorithm": "sha256", "hex": stored_hex},
    }


def emit_usage_receipt(receipt: dict[str, Any], receipt_dir: Path) -> Path | None:
    """Write one sealed usage receipt to ``receipt_dir``. Never raises.

    Mirrors emit_eval_receipt / emit_audit_receipt: mkdir parents, write compact
    JSON, swallow any failure to stderr, return the Path written or None. The
    filename carries the run_id and a short seal prefix and is BARE (never an
    absolute path); emission must never block or break the answer path.
    """
    try:
        receipt_dir.mkdir(parents=True, exist_ok=True)
        run_id = str(receipt.get("run_id", "run"))
        safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in run_id)[:48]
        seal_hex = str(receipt.get("seal", {}).get("hex", ""))[:12] or "unsealed"
        filename = f"usage-receipt-{safe}-{seal_hex}.json"
        path = receipt_dir / filename
        path.write_text(
            json.dumps(receipt, separators=(",", ":"), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path
    except Exception as exc:  # noqa: BLE001 -- emission must never break the answer path
        print(f"usage-receipt: emission failed (non-fatal): {exc}", file=sys.stderr)
        return None
