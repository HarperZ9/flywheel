"""overrides.py -- typed reasons for an owner's decision on a hold, and a later outcome check.

An owner who approves, rejects or terminates a held call can give a reason code
from a short fixed list plus free text. The code goes into the sealed decision
record. The text stays in an owner-only side file keyed by the decision's seal,
and the sealed record keeps only its digest, as before.

Once the result is known, an outcome record links back to the decision and says
whether the decision held up: an approved call that caused harm, or a rejected
call that turned out to be needed, marks the decision WRONG. The verdict is
derived from typed evidence, never typed in directly, so a reader can see what
the judgment rests on. An outcome checked by the same person who decided is
marked self_check, because nobody judges their own call independently.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .contract import sha256_hex
from .records import DECISION_SCHEMA, HoldStore

REASON_CODES = ("rule_false_positive", "wrong_target", "scope_exceeded",
                "data_destination_not_allowed", "needs_more_context", "other")
OUTCOME_SCHEMA = "flywheel.preaction-outcome/v1"
NOT_DETERMINABLE = "not_determinable"
# decision -> evidence code -> verdict on the decision
EVIDENCE = {
    "APPROVED_ONCE": {"no_harm_observed": "RIGHT", "harm_observed": "WRONG"},
    "REJECTED": {"call_not_needed": "RIGHT", "call_was_needed": "WRONG"},
    "TERMINATED": {"call_not_needed": "RIGHT", "call_was_needed": "WRONG"},
}
OUTCOME_DOES_NOT_PROVE = (
    "Records one person's later reading of what happened after the decision. "
    "It does not prove the decision's cause or that the reading is correct.")


def check_reason_code(code: str) -> str:
    """Empty (no code given) or one of REASON_CODES; anything else is refused."""
    if code and code not in REASON_CODES:
        raise ValueError(f"reason code must be one of {REASON_CODES}")
    return code


def _private_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())


def write_reason_text(home, seal_hex: str, text: str) -> None:
    """Owner-only free text beside the sealed digest. Nothing written when empty."""
    if text:
        _private_json(Path(home) / "reasons" / f"{seal_hex}.json", {"text": text})


def read_reason_text(home, seal_hex: str) -> str:
    p = Path(home) / "reasons" / f"{seal_hex}.json"
    return json.loads(p.read_text(encoding="utf-8"))["text"] if p.exists() else ""


def _find_decision(recs: list, decision_sha256: str) -> dict:
    for rec in recs:
        if rec.get("schema") == DECISION_SCHEMA and rec.get("seal", {}).get("hex") == decision_sha256:
            return rec
    raise ValueError("no decision record with that seal")


def _verdict_for(decision: str, evidence: str) -> str:
    if decision not in EVIDENCE:
        raise ValueError(f"an outcome follows an owner decision, not {decision}")
    if evidence == NOT_DETERMINABLE:
        return "UNKNOWN"
    if evidence not in EVIDENCE[decision]:
        allowed = sorted(EVIDENCE[decision]) + [NOT_DETERMINABLE]
        raise ValueError(f"evidence for {decision} must be one of {allowed}")
    return EVIDENCE[decision][evidence]


def record_outcome(home, clock, decision_sha256: str, evidence: str, *,
                   checked_by: str, note: str = "") -> dict:
    """Append one outcome record for one decision. A second outcome for the same
    decision is refused; the store is append-only and the first reading stands."""
    if not checked_by:
        raise ValueError("an outcome needs the name of who checked it")
    store = HoldStore(home)
    recs = store.read_all(tolerant=True)
    decision = _find_decision(recs, decision_sha256)
    verdict = _verdict_for(decision["decision"], evidence)
    if any(r.get("schema") == OUTCOME_SCHEMA and r.get("decision_record_sha256") == decision_sha256
           for r in recs):
        raise ValueError("this decision already has an outcome record")
    rec = {"schema": OUTCOME_SCHEMA, "source": f"outcome:{decision.get('hold_id', '')}",
           "hold_id": decision.get("hold_id", ""), "decision_record_sha256": decision_sha256,
           "decision": decision["decision"], "reason_code": decision.get("reason_code", ""),
           "evidence": evidence, "verdict_on_decision": verdict, "checked_by": checked_by,
           "checked_at": clock(), "self_check": checked_by == decision.get("decider", ""),
           "note_sha256": sha256_hex(note.encode("utf-8")) if note else "",
           "does_not_prove": OUTCOME_DOES_NOT_PROVE}
    seal_hex = store.append(rec)
    write_reason_text(home, seal_hex, note)
    return rec
