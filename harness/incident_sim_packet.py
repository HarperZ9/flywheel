"""Portable incident-sim process-audit packet builder.

The packet composes existing Flywheel primitives over submitted JSON values. It
does not execute commands, access the network, or mint EMET receipts.
"""
from __future__ import annotations

import json
from typing import Any

from .audit_receipt import build_audit_receipt, verify_audit_receipt
from .evidence_json import canonical_bytes, canonical_sha256
from .institutional_access import assess_institutional_access
from .incident_case import new_incident_case
from .incident_proposal import compile_incident_proposal
from .incident_sim_input import IncidentSimValidationError, work_blocking_reasons
from .incident_sim_eval import MATCH, UNVERIFIABLE, evaluate_incident_sim
from .incident_sim_packet_verify import (
    packet_body_sha256,
    packet_section_hashes,
    verify_process_audit_packet,
)
from .tool_call_receipt import build_receipt, verify_chain, verify_receipt

SCHEMA = "flywheel.incident-sim-process-audit/v1"
ACCESS_COMPONENT_SCHEMA = "flywheel.institutional-access-component/v1"
_NOW = "2026-09-13T00:00:00Z"


def _snapshot(value: object) -> object:
    return json.loads(canonical_bytes(value).decode("utf-8"))


def _ptr(parts: list[str | int]) -> str:
    def esc(part: str | int) -> str:
        return str(part).replace("~", "~0").replace("/", "~1")
    return "/" + "/".join(esc(part) for part in parts)


def _source_values(task: dict[str, Any], trace: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        {"source": "task", "json_pointer": "/expected_final_state",
         "source_value": _snapshot(task.get("expected_final_state"))},
        {"source": "trace", "json_pointer": "/final_state",
         "source_value": _snapshot(trace.get("final_state"))},
    ]
    for index, action in enumerate(task.get("expected_actions", []) or []):
        rows.append({"source": "task",
                     "json_pointer": _ptr(["expected_actions", index, "id"]),
                     "source_value": _snapshot(action.get("id"))})
    for index, action in enumerate(trace.get("observed_actions", []) or []):
        rows.append({"source": "trace",
                     "json_pointer": _ptr(["observed_actions", index, "id"]),
                     "source_value": _snapshot(action.get("id"))})
    for index, score in enumerate(trace.get("claimed_scores", []) or []):
        if isinstance(score, dict):
            rows.append({"source": "trace",
                         "json_pointer": _ptr(["claimed_scores", index, "value"]),
                         "source_value": _snapshot(score.get("value"))})
    return rows


def _supplied_check(supplied: dict[str, Any] | None,
                    computed: dict[str, Any]) -> dict[str, str]:
    if supplied is None:
        return {"verdict": UNVERIFIABLE, "detail": "no caller-supplied evaluation"}
    if canonical_sha256(supplied) == canonical_sha256(computed):
        return {"verdict": MATCH, "detail": "caller-supplied evaluation matched recompute"}
    return {"verdict": "DRIFT", "detail": "caller-supplied evaluation diverged from recompute"}


def _action_receipts(trace: dict[str, Any]) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    prev = ""
    run_id = str(trace.get("trace_id", "incident-sim-trace"))
    for index, action in enumerate(trace.get("observed_actions", []) or []):
        receipt = build_receipt(
            tool="incident-sim-action",
            capability="builtin-read",
            admission="RECONSTRUCTED",
            args={"trace_id": run_id, "action_id": action.get("id", "")},
            output=str(action.get("summary", "")),
            ok=True,
            rc=0,
            run_id=run_id,
            seq=index,
            prev_receipt_sha256=prev,
            rationale={
                "stated_intent": "record submitted incident-sim action",
                "options_considered": ["drop", "record as reconstructed evidence"],
                "chosen_option": "record as reconstructed evidence",
                "confidence": "moderate",
            },
        )
        receipts.append(receipt)
        prev = receipt["seal"]["hex"]
    return receipts


def _work_receipt(task_sha: str, trace_sha: str, evaluation: dict[str, Any],
                  trace: dict[str, Any]) -> dict[str, Any]:
    return build_receipt(
        tool="incident-sim-evaluate",
        capability="builtin-read",
        admission="LOCAL_CHECKER",
        args={"task_sha256": task_sha, "trace_sha256": trace_sha},
        output=str(canonical_sha256(evaluation)),
        ok=True,
        rc=0,
        run_id=str(trace.get("trace_id", "incident-sim-trace")),
        seq=10_000,
        rationale={
            "stated_intent": "evaluate submitted incident-sim trace",
            "options_considered": ["trust supplied verdict", "recompute from sources"],
            "chosen_option": "recompute from sources",
            "confidence": "high",
        },
    )


def _incident(task: dict[str, Any], task_sha: str, trace_sha: str) -> dict[str, Any]:
    meta = task.get("incident", {}) if isinstance(task.get("incident"), dict) else {}
    source_facts = task.get("source_facts", []) or []
    case = new_incident_case(
        case_id=str(meta.get("case_id", "case_incident")),
        journey_ref=str(meta.get("journey_ref", "jrn_" + "0" * 32)),
        event_head_sha256=str(meta.get("event_head_sha256", "0" * 64)),
        source_refs=source_facts,
        failure=meta.get("failure", {"summary": "incident-sim evaluation"}),
        created_at=str(meta.get("created_at", _NOW)),
    )
    projection = {
        "journey_ref": case["journey_ref"],
        "event_head_sha256": case["event_head_sha256"],
        "facts": source_facts,
    }
    proposal = compile_incident_proposal(
        case=case,
        projection=projection,
        capability_sha256=canonical_sha256({"task": task_sha, "trace": trace_sha}),
    )
    return {"case": case, "proposal": proposal}


def _audit_receipt(evaluation: dict[str, Any], work: dict[str, Any],
                   packet_subject_sha: str, trace: dict[str, Any]) -> dict[str, Any]:
    verdict = "PASS" if evaluation["overall"]["verdict"] == MATCH else "FAIL"
    severity = "INFO" if verdict == "PASS" else "CRITICAL"
    return build_audit_receipt(
        run_id=str(trace.get("trace_id", "incident-sim-trace")),
        work_receipt_sha256=work["seal"]["hex"],
        subject_digest=packet_subject_sha,
        reviewer="incident-sim-local-checker",
        reviews=[{
            "detector_id": "incident-sim-process-audit",
            "dimension": "correctness",
            "severity": severity,
            "summary": f"bounded fixture verdict {evaluation['overall']['verdict']}",
        }],
        summary="bounded incident-sim process audit over submitted JSON",
        verdict=verdict,
        confidence="moderate",
        does_not_prove="independent external ground truth or complete workstation observation",
        started_utc=_NOW,
        finished_utc=_NOW,
    )


def _access_component(task: dict[str, Any], trace: dict[str, Any],
                      institutional_access: dict[str, Any],
                      institutional_access_scope: dict[str, Any]) -> dict[str, Any]:
    body = {
        "schema": ACCESS_COMPONENT_SCHEMA,
        "context": "synthetic_declared_access",
        "assessment": assess_institutional_access(
            institutional_access, scope=institutional_access_scope,
            sources={"task": task, "trace": trace}),
    }
    return {**body, "component_sha256": canonical_sha256(body)}


def _subject_digest(task_sha: str, trace_sha: str, eval_sha: str, work_sha: str,
                    access_sha: str | None = None) -> str:
    body = {"task_sha256": task_sha, "trace_sha256": trace_sha,
            "evaluation_sha256": eval_sha, "work_receipt_sha256": work_sha}
    if access_sha is not None:
        body["institutional_access_sha256"] = access_sha
    return canonical_sha256(body)


def build_process_audit_packet(
    task: dict[str, Any],
    trace: dict[str, Any],
    *,
    supplied_evaluation: dict[str, Any] | None = None,
    institutional_access: dict[str, Any] | None = None,
    institutional_access_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the bounded process-audit packet for one incident-sim trace."""
    task = _snapshot(task)
    trace = _snapshot(trace)
    evaluation = evaluate_incident_sim(task, trace)
    blocked = work_blocking_reasons(evaluation["input_validation"])
    if blocked:
        raise IncidentSimValidationError(";".join(blocked))
    task_sha = canonical_sha256(task)
    trace_sha = canonical_sha256(trace)
    eval_sha = canonical_sha256(evaluation)
    actions = _action_receipts(trace)
    work = _work_receipt(task_sha, trace_sha, evaluation, trace)
    incident = _incident(task, task_sha, trace_sha)
    access_component = None
    if institutional_access is not None or institutional_access_scope is not None:
        if institutional_access is None or institutional_access_scope is None:
            raise IncidentSimValidationError("institutional_access requires institutional_access_scope")
        access_component = _access_component(
            task, trace, institutional_access, institutional_access_scope)
    subject = _subject_digest(task_sha, trace_sha, eval_sha, work["seal"]["hex"],
                              None if access_component is None else access_component["component_sha256"])
    audit = _audit_receipt(evaluation, work, subject, trace)
    source_values = _source_values(task, trace)
    independence = {
        "roles": _snapshot(task.get("roles", {})),
        "shared_dependencies": _snapshot(task.get("shared_dependencies", [])),
        "unknowns": [
            "assessment independence is unknown for the local checker",
            "evidence independence is limited to the submitted fixture",
            "implementation independence is not established by this slice",
        ],
    }
    supplied_check = _supplied_check(supplied_evaluation, evaluation)
    receipt_verification = {
        "actions": verify_chain(actions) if actions else {
            "verdict": UNVERIFIABLE, "detail": "no action receipts", "receipts": []},
        "work": verify_receipt(work),
        "audit": verify_audit_receipt(audit, work),
    }
    packet = {
        "schema": SCHEMA,
        "task_sha256": task_sha,
        "trace_sha256": trace_sha,
        "evaluation_sha256": eval_sha,
        "evaluation": evaluation,
        "supplied_evaluation_check": supplied_check,
        "source_values": source_values,
        "observation_scope": "fixture_expected_actions_only",
        "independence": independence,
        "incident": incident,
        "receipts": {"actions": actions, "work": work, "audit": audit},
        "receipt_verification": receipt_verification,
        "receipt_limitations": [
            "Action receipts are reconstructed from a submitted trace; they do not prove the actions actually ran.",
            "Observation coverage is limited to fixture expected actions, not the whole workstation.",
        ],
        "integration_limits": [
            "EMET receipt is not minted by this slice.",
            "No live agent execution, Inspect runtime, network, or EMET wire integration is included.",
        ],
    }
    if access_component is not None:
        packet["institutional_access"] = access_component
    packet["section_sha256"] = packet_section_hashes({
        "evaluation": evaluation,
        "supplied_evaluation_check": supplied_check,
        "source_values": source_values,
        "independence": independence,
        "incident": incident,
        "receipt_verification": receipt_verification,
    })
    packet["packet_sha256"] = packet_body_sha256(packet)
    return packet
