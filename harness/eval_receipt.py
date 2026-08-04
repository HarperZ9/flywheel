"""eval_receipt.py -- the sealed, offline-verifiable eval-run receipt.

The primary product wedge, as a data structure: a real eval run through a real
provider produces a sealed receipt binding the outcome to the endpoint, the
model, the dataset (as a hash, never the tasks themselves), the config, and the
judge. Anyone re-checks it offline; corrupting one byte makes the verifier
refuse. The refusal is the point -- it is what makes the seal mean something.

This does NOT reinvent the seal. It reuses tool_call_receipt.py's discipline
verbatim: fixed field order (NOT sort_keys), no floats anywhere (bools stored
as "true"/"false" strings, counts as digit strings), args/output-style content
stored only as {sha256, bytes}, and the blanked-seal canonical-bytes hash
(blank seal.hex, fix algorithm, hash, write the hash back). A receipt chains to
a prior by prev_receipt_sha256 = the prior's blanked-seal recompute.

Standard library only. Python 3.10-safe (datetime.timezone.utc, never the 3.11
datetime.UTC alias).
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

SCHEMA = "flywheel.eval-receipt/v1"

# The per-result fields, in fixed order. A result is the disposition of ONE
# task: which task, what the oracle said, whether it was accepted. No floats.
_RESULT_FIELDS = ("task_id", "verdict", "accepted")


def _bool_str(v: Any) -> str:
    """Bools serialize as the strings "true"/"false" -- the no-floats, no-bools
    discipline of the shared receipt schema."""
    return "true" if (v is True or str(v).lower() == "true") else "false"


def _dataset_digest(tasks: Any) -> str:
    """The canonical hash of the task set. The receipt stores ONLY this digest
    and the count -- never the tasks themselves, so a receipt discloses that a
    run happened over a bound dataset without disclosing the dataset. Sorted
    keys here (this is a content digest, not the fixed-order sealed body)."""
    payload = json.dumps(tasks, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return _sha256_hex(payload)


def _normalize_results(results: Any) -> list[dict[str, str]]:
    """Each result down to exactly {task_id, verdict, accepted}, all strings.
    Unknown fields dropped (additionalProperties: false)."""
    out: list[dict[str, str]] = []
    for r in results or []:
        r = r if isinstance(r, dict) else {}
        out.append({
            "task_id": str(r.get("task_id", "")),
            "verdict": str(r.get("verdict", "")),
            "accepted": _bool_str(r.get("accepted", False)),
        })
    return out


def build_eval_receipt(
    *,
    run_id: str,
    endpoint: str,
    model_ref: str,
    tasks: Any,
    config: dict[str, Any],
    judge: str,
    results: Any,
    started_utc: str,
    finished_utc: str,
    prev_receipt_sha256: str = "",
) -> dict[str, Any]:
    """Build a sealed eval-run receipt in the fixed schema field order.

    The task list is stored ONLY as {"sha256": <dataset digest>, "n": <count>}.
    Every config value is stringified (no floats). Each result is normalized to
    {task_id, verdict, accepted} with string values. The seal is the blanked-
    seal canonical-bytes hash from tool_call_receipt, so a stranger re-checks it
    with the same discipline that verifies every other receipt in the system.
    """
    norm_results = _normalize_results(results)
    dataset_n = str(len(tasks) if hasattr(tasks, "__len__") else 0)
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "run_id": str(run_id),
        "endpoint": str(endpoint),
        "model_ref": str(model_ref),
        "dataset": {"sha256": _dataset_digest(tasks), "n": dataset_n},
        "config": {str(k): str(v) for k, v in (config or {}).items()},
        "judge": str(judge),
        "results": norm_results,
        "n_results": str(len(norm_results)),
        "started_utc": str(started_utc),
        "finished_utc": str(finished_utc),
        "prev_receipt_sha256": str(prev_receipt_sha256 or ""),
        "seal": {"algorithm": "sha256", "hex": ""},
    }
    _seal_receipt(receipt)
    return receipt


def _fail(failure_class: str, detail: str) -> dict[str, Any]:
    """A tamper of the sealed body is TAMPERED; anything else the verifier
    cannot stand behind is UNVERIFIABLE. Same taxonomy split as the tool-call
    receipt, so a caller reads one vocabulary across every receipt family."""
    verdict = TAMPERED if failure_class == "SEAL_MISMATCH" else UNVERIFIABLE
    return {"schema": SCHEMA, "verdict": verdict,
            "failure_class": failure_class, "detail": detail}


def verify_eval_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Offline re-verification. Returns {verdict, failure_class, detail}.

    The checks run in the only order that is safe: SCHEMA first (so a foreign
    object is refused before any field is trusted), then the SEAL (so no sealed
    field is interpreted until the seal is proven), then digest well-formedness,
    then the field contracts (result count consistent with the dataset n). A
    single flipped hex character anywhere in the sealed body fails the seal --
    that is the refusal the whole surface stands on.
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
    dataset = receipt.get("dataset")
    if not isinstance(dataset, dict):
        return _fail("FIELD_CONTRACT_VIOLATION", "dataset is not an object")
    if not _digest_well_formed(dataset.get("sha256", "")):
        return _fail("DIGEST_MALFORMED",
                     "dataset.sha256 is not a 64-char hex digest")
    prev = receipt.get("prev_receipt_sha256", "")
    if prev and not _digest_well_formed(prev):
        return _fail("DIGEST_MALFORMED",
                     "prev_receipt_sha256 is not a 64-char hex digest")

    # --- field contracts ------------------------------------------------------
    n_str = dataset.get("n", "")
    if not (isinstance(n_str, str) and n_str.isdigit()):
        return _fail("FIELD_CONTRACT_VIOLATION",
                     "dataset.n is not a non-negative digit string")
    results = receipt.get("results")
    if not isinstance(results, list):
        return _fail("FIELD_CONTRACT_VIOLATION", "results is not a list")
    if len(results) != int(n_str):
        return _fail("FIELD_CONTRACT_VIOLATION",
                     f"result count {len(results)} != dataset n {n_str}")
    n_results = receipt.get("n_results", "")
    if not (isinstance(n_results, str) and n_results.isdigit()
            and int(n_results) == len(results)):
        return _fail("FIELD_CONTRACT_VIOLATION",
                     "n_results is not a digit string equal to len(results)")
    for i, r in enumerate(results):
        if not isinstance(r, dict) or set(r.keys()) != set(_RESULT_FIELDS):
            return _fail("FIELD_CONTRACT_VIOLATION",
                         f"result {i} fields != {_RESULT_FIELDS}")
        if r.get("accepted") not in ("true", "false"):
            return _fail("FIELD_CONTRACT_VIOLATION",
                         f"result {i} accepted is not a bool string")

    return {
        "schema": SCHEMA,
        "verdict": MATCH,
        "failure_class": "",
        "detail": f"{len(results)} results over dataset "
                  f"sha256:{dataset['sha256'][:12]} verified",
        "run_id": receipt.get("run_id", ""),
        "endpoint": receipt.get("endpoint", ""),
        "seal": {"algorithm": "sha256", "hex": stored_hex},
    }


def emit_eval_receipt(receipt: dict[str, Any], receipt_dir: Path) -> Path | None:
    """Write one sealed eval receipt to ``receipt_dir``. Never raises.

    Mirrors tool_call_receipt.emit_receipt: mkdir parents, write compact JSON,
    swallow any failure to stderr, return the Path written or None. Emission
    must never block or break the run path. The filename carries the run_id and
    a short seal prefix so a directory of receipts is browsable.
    """
    try:
        receipt_dir.mkdir(parents=True, exist_ok=True)
        run_id = str(receipt.get("run_id", "run"))
        safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in run_id)[:48]
        seal_hex = str(receipt.get("seal", {}).get("hex", ""))[:12] or "unsealed"
        filename = f"eval-receipt-{safe}-{seal_hex}.json"
        path = receipt_dir / filename
        path.write_text(
            json.dumps(receipt, separators=(",", ":"), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path
    except Exception as exc:  # noqa: BLE001 -- emission must never break the run path
        print(f"eval-receipt: emission failed (non-fatal): {exc}", file=sys.stderr)
        return None
