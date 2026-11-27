"""Real day-to-day gated operator workflows: outreach drafts, application packets, and routines."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .action_receipt import ActionReceiptReceptor, receipt_from_outcome, verify_receipts
from .operator_policy import OperatorAction, canonical_bytes, sha256_prefixed
from .workstation_operator import OperatorSession, OperatorStepRecord, verify_action_journal

HONEST_SPDX_LICENSES = frozenset(("AGPL-3.0-only", "FSL-1.1-MIT", "LicenseRef-FSL-1.1-MIT", "Apache-2.0", "MIT"))
_EXCLUDED_WORKFLOW_RE = re.compile(
    r"(?i)\b(solve[_\s-]?captcha|bypass[_\s-]?(auth|captcha|oauth|uac)|"
    r"mass[_\s-]?(outreach|email|blast)|obfuscated[_\s-]?outreach|"
    r"anti[_\s-]?bot[_\s-]?stealth|fingerprint[_\s-]?patch)\b"
)
_APPLICATION_HALT_RE = re.compile(
    r"(?i)\b(captcha|recaptcha|turnstile|legal[_\s-]?attestation|sworn[_\s-]?statement|"
    r"ai[_\s-]?(generation[_\s-]?)?ban(ned)?|no[_\s-]?ai[_\s-]?generated)\b"
)


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")[:48] or "item"


def _load_ledger_keys(ledger_path: Path) -> set[str]:
    if not ledger_path.is_file():
        return set()
    keys: set[str] = set()
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line) if line.strip() else None
        except ValueError:
            obj = None
        if isinstance(obj, dict) and isinstance(obj.get("dedupe_key"), str):
            keys.add(obj["dedupe_key"])
    return keys


def _append_surface_journal(journal_path: Path, kind: str, summary: str, detail: dict[str, Any]) -> str:
    prev = ""
    if journal_path.is_file():
        for line in journal_path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line) if line.strip() else None
                if isinstance(rec, dict) and "_hash" in rec:
                    prev = str(rec["_hash"])
            except ValueError:
                continue
    content = {"kind": kind, "summary": summary, "detail": detail}
    canon = json.dumps(content, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{prev}|{canon}".encode("utf-8")).hexdigest()
    record = {**content, "_prev": prev, "_hash": digest}
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    with journal_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return digest


class _SimpleOutcome:
    """Minimal outcome adapter for ActionReceiptReceptor emission."""

    def __init__(self, *, acted: bool, verified: bool, decision: str, before_digest: str, after_digest: str) -> None:
        self.acted, self.verified, self.decision = acted, verified, decision
        self.verdict = "verified" if verified else "unverifiable"
        self.before_digest, self.after_digest = before_digest, after_digest
        self.certificate = {"workflow": "operator_workflows"}


def _emit_outreach_receipt(
    action_receipts_path: str | Path | None, stage_rec: OperatorStepRecord,
    draft_path: Path, draft_bytes: bytes, dedupe_key: str, created_at: str,
) -> dict[str, Any] | None:
    if action_receipts_path is None:
        return None
    outcome = _SimpleOutcome(
        acted=True, verified=True, decision="allow",
        before_digest=stage_rec.pre_obs_sha256, after_digest=stage_rec.post_obs_sha256,
    )
    event = receipt_from_outcome(
        outcome, action_kind="outreach.stage_draft", target=str(draft_path),
        args_hash=sha256_prefixed(draft_bytes), principal="agent:accountable-surface.operator-workflows",
        intent_ref=f"intent:outreach:{dedupe_key[:12]}", idempotency_key=f"outreach:{dedupe_key}",
        created_at=created_at, side_effect_class="write",
    )
    return ActionReceiptReceptor(action_receipts_path).emit(event)


def _record_outreach_ledger(
    session: OperatorSession, ledger: Path, dedupe_key: str, rec_norm: str, subj_norm: str, draft_path: Path, created_at: str,
) -> None:
    existing = ledger.read_text(encoding="utf-8") if ledger.is_file() else ""
    line = canonical_bytes(
        {"dedupe_key": dedupe_key, "recipient": rec_norm, "subject": subj_norm, "draft_path": str(draft_path), "created_at": created_at}
    ).decode("utf-8")
    ledger_bytes = (existing + line + "\n").encode("utf-8")
    session.step(OperatorAction("write_file", str(ledger), params={"content": ledger_bytes}, expected_post={"file_sha256": sha256_prefixed(ledger_bytes)}, rationale="record outreach dedupe key"))


def stage_outreach_draft(
    session: OperatorSession, *, recipient: str, subject: str, body: str,
    out_dir: str | Path, ledger_path: str | Path,
    action_receipts_path: str | Path | None = None, created_at: str = "2026-11-26T00:00:00Z",
) -> dict[str, Any]:
    """Validate outreach draft against duplicate ledger & exclusions, stage artifact, and pause at NEEDS_HUMAN."""
    rec_norm, subj_norm, body_norm = recipient.strip().lower(), subject.strip(), body.strip()
    if not rec_norm or "@" not in rec_norm or not subj_norm or not body_norm:
        return {"status": "REFUSED_INVALID", "staged": False, "needs_human": False, "reason": "recipient, subject, and body are required"}
    blob = f"{subj_norm}\n{body_norm}"
    if "\u2014" in blob:
        return {"status": "REFUSED_STYLE", "staged": False, "needs_human": False, "reason": "em dash is forbidden in outreach drafts"}
    if _EXCLUDED_WORKFLOW_RE.search(blob):
        return {"status": "REFUSED_EXCLUDED", "staged": False, "needs_human": False, "reason": "hard-excluded outreach or bypass pattern detected"}
    dedupe_key = hashlib.sha256(f"{rec_norm}|{subj_norm.lower()}".encode("utf-8")).hexdigest()
    ledger = Path(ledger_path)
    if dedupe_key in _load_ledger_keys(ledger):
        return {"status": "REFUSED_DUPLICATE", "staged": False, "needs_human": False, "dedupe_key": dedupe_key, "reason": "duplicate recipient+subject already present in ledger"}

    draft_path = Path(out_dir) / f"outreach-{_slug(rec_norm)}-{dedupe_key[:10]}.json"
    draft_bytes = canonical_bytes({
        "schema": "operator-outreach-draft/1", "recipient": rec_norm, "subject": subj_norm,
        "body": body_norm, "dedupe_key": dedupe_key, "created_at": created_at, "approval_state": "NEEDS_HUMAN",
    }) + b"\n"
    stage_rec = session.step(OperatorAction("write_file", str(draft_path), params={"content": draft_bytes}, expected_post={"file_sha256": sha256_prefixed(draft_bytes), "file_exists": True}, rationale="stage approval-gated outreach draft"))
    if not stage_rec.executed or not stage_rec.post_verified:
        return {"status": "REFUSED_GATE", "staged": False, "needs_human": False, "reason": stage_rec.post_detail}

    _record_outreach_ledger(session, ledger, dedupe_key, rec_norm, subj_norm, draft_path, created_at)
    receipt_meta = _emit_outreach_receipt(action_receipts_path, stage_rec, draft_path, draft_bytes, dedupe_key, created_at)
    send_gate = session.step(OperatorAction("mcp_call", "outreach.send_live", params={"recipient": rec_norm, "draft_path": str(draft_path), "dedupe_key": dedupe_key}, destructive=True, rationale="pause before any live external outreach send"))
    dec = send_gate.gate_verdict.decision
    return {"status": dec, "staged": True, "needs_human": dec == "NEEDS_HUMAN", "draft_path": str(draft_path), "dedupe_key": dedupe_key, "receipt": receipt_meta, "send_step_seq": send_gate.seq}


def _validate_application_fields(fields: Mapping[str, str], field_limits: Mapping[str, Mapping[str, int]]) -> list[str]:
    violations: list[str] = []
    for name, value in fields.items():
        text = str(value)
        if "\u2014" in text:
            violations.append(f"field '{name}' contains forbidden em dash")
        limits = field_limits.get(name, {})
        max_chars, max_words = limits.get("max_chars"), limits.get("max_words")
        if max_chars is not None and len(text) > int(max_chars):
            violations.append(f"field '{name}' exceeds max_chars ({len(text)} > {max_chars})")
        if max_words is not None and len(text.split()) > int(max_words):
            violations.append(f"field '{name}' exceeds max_words ({len(text.split())} > {max_words})")
    return violations


def stage_application_packet(
    session: OperatorSession, *, applicant_profile: Mapping[str, Any], program_name: str,
    fields: Mapping[str, str], field_limits: Mapping[str, Mapping[str, int]],
    out_dir: str | Path, flags: Mapping[str, bool] | None = None, licenses: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Bind applicant profile, honest license tags, and field budgets; halt at NEEDS_HUMAN on CAPTCHA/legal/AI-ban."""
    lic_map = dict(licenses or {"buildlang": "AGPL-3.0-only", "flywheel": "FSL-1.1-MIT"})
    bad = [f"{k}={v}" for k, v in lic_map.items() if v not in HONEST_SPDX_LICENSES]
    if not lic_map or bad:
        return {"status": "REFUSED_LICENSE", "staged": False, "needs_human": False, "errors": [f"unverified license tag: {x}" for x in bad] or ["missing license tags"]}
    violations = _validate_application_fields(fields, field_limits)
    if violations:
        return {"status": "REFUSED_BUDGET", "staged": False, "needs_human": False, "errors": violations}

    flag_map = dict(flags or {})
    halt_reasons = [k for k in ("captcha_present", "legal_attestation_required", "ai_generation_banned") if flag_map.get(k)]
    if _APPLICATION_HALT_RE.search(" ".join([program_name, *(str(v) for v in fields.values())])):
        halt_reasons.append("detected_portal_gate_clause")

    packet_path = Path(out_dir) / f"application-{_slug(program_name)}.json"
    packet_bytes = canonical_bytes({
        "schema": "operator-application-packet/1", "program_name": program_name,
        "applicant_profile": dict(applicant_profile), "licenses": lic_map,
        "fields": dict(fields), "halt_reasons": halt_reasons, "submission_state": "NEEDS_HUMAN",
    }) + b"\n"
    write_rec = session.step(OperatorAction("write_file", str(packet_path), params={"content": packet_bytes}, expected_post={"file_sha256": sha256_prefixed(packet_bytes), "file_exists": True}, rationale="stage verified application packet for human review"))
    if not write_rec.executed or not write_rec.post_verified:
        return {"status": "REFUSED_GATE", "staged": False, "needs_human": False, "errors": [write_rec.post_detail]}
    submit_rec = session.step(OperatorAction("mcp_call", "application.submit_live", params={"program_name": program_name, "packet_path": str(packet_path), "halt_reasons": halt_reasons}, destructive=True, rationale="halt at NEEDS_HUMAN before live portal submission"))
    dec = submit_rec.gate_verdict.decision
    return {"status": dec, "staged": True, "needs_human": dec == "NEEDS_HUMAN", "halt_reasons": halt_reasons, "packet_path": str(packet_path), "submit_step_seq": submit_rec.seq}


def run_workstation_routine(
    session: OperatorSession, *, routine_name: str, checks: Sequence[Mapping[str, Any]] = (),
    action_receipts_path: str | Path | None = None, surface_journal_path: str | Path | None = None,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run read-only health/telemetry/receipt checks and append a verifiable journal entry."""
    obs = session.observe()
    results: list[dict[str, Any]] = [{"name": "workstation_observe", "ok": bool(obs.obs_sha256), "obs_sha256": obs.obs_sha256}]
    if session.journal_path is not None and session.journal_path.is_file():
        j_ok, j_errs, j_head = verify_action_journal(session.journal_path)
        results.append({"name": "action_journal_chain", "ok": j_ok, "head": j_head, "errors": j_errs})
    if action_receipts_path is not None and Path(action_receipts_path).is_file():
        label, detail = verify_receipts(Path(action_receipts_path).read_text(encoding="utf-8"))
        results.append({"name": "action_receipts_chain", "ok": label == "MATCH", "verdict": label, "detail": detail})
    for chk in checks:
        results.append({"name": str(chk.get("name", "custom")), "ok": bool(chk.get("ok", True)), "detail": str(chk.get("detail", ""))})

    all_ok = all(bool(r.get("ok")) for r in results)
    if report_path is not None:
        rep_bytes = canonical_bytes({"routine": routine_name, "all_ok": all_ok, "checks": results}) + b"\n"
        step_rec = session.step(OperatorAction("write_file", str(report_path), params={"content": rep_bytes}, expected_post={"file_sha256": sha256_prefixed(rep_bytes), "file_exists": True}, rationale="record read-only workstation health routine report"))
    else:
        step_rec = session.step(OperatorAction("mcp_call", f"routine.{_slug(routine_name)}", params={"routine": routine_name, "checks_total": len(results), "all_ok": all_ok}, rationale="record read-only workstation health and telemetry routine"))
    surface_hash = None
    if surface_journal_path is not None:
        surface_hash = _append_surface_journal(
            Path(surface_journal_path), kind="workstation_routine",
            summary=f"routine:{routine_name} ok={all_ok} checks={len(results)}",
            detail={"routine": routine_name, "all_ok": all_ok, "checks": results, "operator_entry_hash": step_rec.entry_hash},
        )
    return {"routine_name": routine_name, "ok": all_ok and step_rec.executed, "checks": results, "operator_entry_hash": step_rec.entry_hash, "surface_journal_hash": surface_hash}
