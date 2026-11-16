"""Packet-local verification helpers for incident-sim process audit packets."""
from __future__ import annotations

from typing import Any

from .audit_receipt import verify_audit_receipt
from .evidence_json import canonical_sha256
from .tool_call_receipt import MATCH, UNVERIFIABLE, verify_chain, verify_receipt

VERIFY_SCHEMA = "flywheel.incident-sim-process-audit-verification/v1"
ACCESS_COMPONENT_SCHEMA = "flywheel.institutional-access-component/v1"
DRIFT = "DRIFT"
NOT_ASSESSED = "NOT_ASSESSED"
_SECTION_FIELDS = (
    "evaluation",
    "source_values",
    "independence",
    "incident",
    "receipt_verification",
    "supplied_evaluation_check",
)
_DOES_NOT_VERIFY = [
    "semantic correctness of the task, trace, evaluation, scorer, or access claim",
    "reconstruction of source_values from full task and trace bodies when those bodies are absent",
    "wall-clock truth, disclosure completeness, or immutable external history",
    "absence of a coherent rewrite of the local packet and every packet-local digest",
]
_TOOL_KEYS = (
    "schema", "source", "tool", "capability", "admission", "args", "output",
    "ok", "rc", "run_id", "seq", "prev_receipt_sha256", "outcome", "seal",
    "rationale", "session_token_ref", "sandbox",
)
_AUDIT_KEYS = (
    "schema", "run_id", "reviewer", "subject", "reviews", "summary", "verdict",
    "confidence", "does_not_prove", "started_utc", "finished_utc",
    "prev_receipt_sha256", "seal",
)


def packet_body_sha256(packet: dict[str, Any]) -> str:
    """Hash the emitted packet body while excluding the self-referential digest."""
    body = dict(packet)
    body.pop("packet_sha256", None)
    return canonical_sha256(body)


def packet_section_hashes(sections: dict[str, Any]) -> dict[str, str]:
    """Return canonical hashes for reviewer-facing packet sections."""
    return {f"/{key}": canonical_sha256(sections[key])
            for key in _SECTION_FIELDS if key in sections}


def _ordered(value: object, keys: tuple[str, ...]) -> object:
    if type(value) is not dict:
        return value
    out = {key: value[key] for key in keys if key in value}
    for key, item in value.items():
        if key not in out:
            out[key] = item
    return out


def _tool_receipt(value: object) -> object:
    if type(value) is not dict:
        return value
    out = _ordered(value, _TOOL_KEYS)
    if not isinstance(out, dict):
        return out
    if "args" in out:
        out["args"] = _ordered(out["args"], ("sha256", "bytes"))
    if "output" in out:
        out["output"] = _ordered(out["output"], ("sha256", "bytes"))
    if "seal" in out:
        out["seal"] = _ordered(out["seal"], ("algorithm", "hex"))
    if "rationale" in out:
        out["rationale"] = _ordered(
            out["rationale"],
            ("stated_intent", "options_considered", "chosen_option", "confidence"),
        )
    if "sandbox" in out:
        out["sandbox"] = _ordered(out["sandbox"], ("kind", "integrity_level"))
    return out


def _audit_receipt(value: object) -> object:
    if type(value) is not dict:
        return value
    out = _ordered(value, _AUDIT_KEYS)
    if not isinstance(out, dict):
        return out
    if "subject" in out:
        out["subject"] = _ordered(out["subject"], ("sha256", "n_reviews"))
    if "seal" in out:
        out["seal"] = _ordered(out["seal"], ("algorithm", "hex"))
    if isinstance(out.get("reviews"), list):
        out["reviews"] = [
            _ordered(item, ("detector_id", "dimension", "severity", "summary"))
            for item in out["reviews"]
        ]
    return out


def _receipts_for_verification(receipts: object) -> dict[str, Any]:
    if type(receipts) is not dict:
        raise TypeError("receipts must be a dict")
    out: dict[str, Any] = {}
    if "actions" in receipts:
        actions = receipts["actions"]
        out["actions"] = [_tool_receipt(item) for item in actions] if isinstance(actions, list) else actions
    if "work" in receipts:
        out["work"] = _tool_receipt(receipts["work"])
    if "audit" in receipts:
        out["audit"] = _audit_receipt(receipts["audit"])
    for key, item in receipts.items():
        if key not in out:
            out[key] = item
    return out


def _subject_digest(task_sha: str, trace_sha: str, eval_sha: str, work_sha: str,
                    access_sha: str | None = None) -> str:
    body = {"task_sha256": task_sha, "trace_sha256": trace_sha,
            "evaluation_sha256": eval_sha, "work_receipt_sha256": work_sha}
    if access_sha is not None:
        body["institutional_access_sha256"] = access_sha
    return canonical_sha256(body)


def _access_verdict(component: object) -> tuple[str, str | None]:
    if component is None:
        return NOT_ASSESSED, None
    if type(component) is not dict or set(component) != {"schema", "context", "assessment", "component_sha256"}:
        return DRIFT, None
    if component.get("schema") != ACCESS_COMPONENT_SCHEMA or component.get("context") != "synthetic_declared_access":
        return DRIFT, None
    body = {key: component[key] for key in ("schema", "context", "assessment")}
    digest = canonical_sha256(body)
    return (MATCH if digest == component.get("component_sha256") else DRIFT), digest


def _section_verdict(packet: dict[str, Any], field: str) -> str:
    hashes = packet.get("section_sha256")
    if type(hashes) is not dict or f"/{field}" not in hashes or field not in packet:
        return UNVERIFIABLE
    return MATCH if canonical_sha256(packet[field]) == hashes[f"/{field}"] else DRIFT


def _record(rows: list[dict[str, str]], field: str, verdict: str, check: str) -> None:
    rows.append({"field": field, "verdict": verdict, "check": check})


def _seal(receipt: object) -> str:
    if isinstance(receipt, dict) and isinstance(receipt.get("seal"), dict):
        value = receipt["seal"].get("hex")
        if isinstance(value, str):
            return value
    return ""


def verify_process_audit_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Recheck packet-local digests and receipts without making semantic claims."""
    verified: list[dict[str, str]] = []
    unverified = [{"field": "/institutional_access", "verdict": NOT_ASSESSED,
                   "check": "optional component absent"}]
    try:
        if type(packet) is not dict:
            raise TypeError("packet must be a dict")
        receipts = _receipts_for_verification(packet["receipts"])
        work = receipts["work"]
        audit = receipts["audit"]

        action_result = verify_chain(receipts.get("actions", []))
        work_result = verify_receipt(work)
        audit_result = verify_audit_receipt(audit, work)
        fresh_receipt_verification = {
            "actions": action_result,
            "work": work_result,
            "audit": audit_result,
        }

        eval_sha = canonical_sha256(packet["evaluation"])
        eval_verdict = MATCH if eval_sha == packet.get("evaluation_sha256") else DRIFT
        packet_digest_verdict = (MATCH if packet_body_sha256(packet) == packet.get("packet_sha256")
                                 else DRIFT)
        access_verdict, access_sha = _access_verdict(packet.get("institutional_access"))
        if access_verdict != NOT_ASSESSED:
            unverified = []
        subject = _subject_digest(packet["task_sha256"], packet["trace_sha256"],
                                  eval_sha, _seal(work), access_sha)
        audit_subject = audit.get("subject", {}).get("sha256") if isinstance(audit, dict) else None
        subject_verdict = MATCH if audit_subject == subject else DRIFT

        section_verdicts = {name: _section_verdict(packet, name) for name in _SECTION_FIELDS}
        receipt_recheck = (MATCH if packet.get("receipt_verification") == fresh_receipt_verification else DRIFT)

        _record(verified, "/evaluation", eval_verdict, "canonical_sha256 matches /evaluation_sha256")
        _record(verified, "", packet_digest_verdict, "canonical_sha256 matches /packet_sha256")
        for name, verdict in section_verdicts.items():
            _record(verified, f"/{name}", verdict, "canonical_sha256 matches /section_sha256")
        _record(verified, "/receipts/actions", action_result.get("verdict", DRIFT), "verify_chain")
        _record(verified, "/receipts/work", work_result.get("verdict", DRIFT), "verify_receipt")
        _record(verified, "/receipts/audit", audit_result.get("verdict", DRIFT), "verify_audit_receipt")
        _record(verified, "/receipts/audit/subject", subject_verdict,
                "subject digest uses recomputed evaluation digest and checked access digest")
        _record(verified, "/receipt_verification", receipt_recheck,
                "stored receipt verification matches fresh verifier outputs")
        if access_verdict != NOT_ASSESSED:
            _record(verified, "/institutional_access", access_verdict, "component digest")

        verdicts = ([eval_verdict, packet_digest_verdict, subject_verdict, receipt_recheck, access_verdict]
                    + list(section_verdicts.values())
                    + [action_result.get("verdict", DRIFT), work_result.get("verdict", DRIFT),
                       audit_result.get("verdict", DRIFT)])
        overall = MATCH if all(item in {MATCH, NOT_ASSESSED} for item in verdicts) else DRIFT
        return {
            "schema": VERIFY_SCHEMA,
            "verdict": overall,
            "verification_scope": "packet-local digests and receipt seals only",
            "verified_fields": verified,
            "unverified_fields": unverified,
            "does_not_verify": list(_DOES_NOT_VERIFY),
            "institutional_access_verdict": access_verdict,
            "packet_digest_verdict": packet_digest_verdict,
            "evaluation_digest_verdict": eval_verdict,
            "source_values_digest_verdict": section_verdicts["source_values"],
            "independence_digest_verdict": section_verdicts["independence"],
            "action_chain_verdict": action_result.get("verdict", DRIFT),
            "work_receipt_verdict": work_result.get("verdict", DRIFT),
            "audit_verdict": audit_result.get("verdict", DRIFT),
            "audit_subject_verdict": subject_verdict,
            "receipt_verification_verdict": receipt_recheck,
        }
    except (KeyError, TypeError, ValueError):
        return {
            "schema": VERIFY_SCHEMA,
            "verdict": DRIFT,
            "verification_scope": "packet-local digests and receipt seals only",
            "verified_fields": verified,
            "unverified_fields": unverified,
            "does_not_verify": list(_DOES_NOT_VERIFY),
            "institutional_access_verdict": DRIFT,
            "packet_digest_verdict": DRIFT,
            "evaluation_digest_verdict": DRIFT,
            "source_values_digest_verdict": DRIFT,
            "independence_digest_verdict": DRIFT,
            "action_chain_verdict": DRIFT,
            "work_receipt_verdict": DRIFT,
            "audit_verdict": DRIFT,
            "audit_subject_verdict": DRIFT,
            "receipt_verification_verdict": DRIFT,
        }
