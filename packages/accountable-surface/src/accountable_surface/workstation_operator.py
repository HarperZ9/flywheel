"""Closed-loop verified model-as-operator workstation control plane."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .operator_backends import RollbackSnapshot, WorkstationBackend
from .operator_policy import (
    AuthorityGate,
    GateVerdict,
    OperatorAction,
    WorkstationObservation,
    canonical_bytes,
    normalize_virtual_path,
)
from .operator_receipt import emit_operator_engine_receipt, verify_operator_engine_receipt

JOURNAL_GENESIS = ""
JOURNAL_SCHEMA = "workstation-operator-journal/1"


def compute_entry_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    """Compute SHA-256 hash linking an action journal entry to prev_hash."""
    raw = f"{prev_hash}|".encode("utf-8") + canonical_bytes(payload)
    return hashlib.sha256(raw).hexdigest()


def verify_action_journal(source: str | Path | Sequence[dict[str, Any]]) -> tuple[bool, list[str], str]:
    """Fail-closed verifier for a hash-chained operator Action Journal."""
    entries, parse_errors = _load_journal_entries(source)
    if parse_errors:
        return False, parse_errors, JOURNAL_GENESIS
    head = JOURNAL_GENESIS
    errors: list[str] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entry {idx} is not a JSON object")
            continue
        prev = entry.get("prev_hash")
        stored = entry.get("entry_hash")
        payload = {k: v for k, v in entry.items() if k not in ("prev_hash", "entry_hash")}
        if prev != head:
            errors.append(f"entry {idx} prev_hash mismatch")
        if not isinstance(stored, str) or stored != compute_entry_hash(head, payload):
            errors.append(f"entry {idx} entry_hash mismatch")
        if payload.get("seq") != idx:
            errors.append(f"entry {idx} sequence gap or reorder (got {payload.get('seq')})")
        head = stored if isinstance(stored, str) else head
    return len(errors) == 0, errors, head


def _load_journal_entries(source: str | Path | Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    if isinstance(source, (str, Path)):
        text = Path(source).read_text(encoding="utf-8")
        entries: list[dict[str, Any]] = []
        errors: list[str] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entries.append(json.loads(stripped))
            except ValueError as exc:
                errors.append(f"line {lineno} invalid JSON: {exc}")
        return entries, errors
    return list(source), []


def _check_post_state(
    expected: dict[str, Any] | None,
    post_obs: WorkstationObservation,
    result: dict[str, Any],
    target: str,
) -> tuple[bool, str]:
    if not expected:
        return bool(result.get("ok", True)), "result ok check"
    norm_t = normalize_virtual_path(target)
    if "exit_code" in expected and result.get("exit_code") != expected["exit_code"]:
        return False, f"expected exit_code={expected['exit_code']}, got {result.get('exit_code')}"
    if "file_sha256" in expected:
        actual = post_obs.file_digests.get(norm_t)
        if actual != expected["file_sha256"]:
            return False, f"expected file_sha256={expected['file_sha256']}, got {actual}"
    if "file_exists" in expected:
        exists = post_obs.file_digests.get(norm_t, "missing") != "missing"
        if exists != bool(expected["file_exists"]):
            return False, f"expected file_exists={expected['file_exists']}, got {exists}"
    if "surface_title" in expected and post_obs.active_surface.get("title") != expected["surface_title"]:
        return False, f"expected surface_title={expected['surface_title']}, got {post_obs.active_surface.get('title')}"
    if "result_equals" in expected:
        for k, v in dict(expected["result_equals"]).items():
            if result.get(k) != v:
                return False, f"expected result[{k}]={v!r}, got {result.get(k)!r}"
    return True, "post-state verified"


@dataclass(frozen=True)
class OperatorStepRecord:
    """Single hash-chained step outcome recorded by OperatorSession."""

    seq: int
    action: OperatorAction
    pre_obs_sha256: str
    gate_verdict: GateVerdict
    executed: bool
    result: dict[str, Any]
    post_obs_sha256: str
    post_verified: bool
    post_detail: str
    rolled_back: bool
    rollback_verified: bool
    snapshot_sha256: str | None
    prev_hash: str
    entry_hash: str

    def to_entry(self) -> dict[str, Any]:
        return {
            "schema": JOURNAL_SCHEMA,
            "seq": self.seq,
            "action": self.action.to_dict(),
            "pre_obs_sha256": self.pre_obs_sha256,
            "gate_verdict": self.gate_verdict.to_dict(),
            "executed": self.executed,
            "result": dict(self.result),
            "post_obs_sha256": self.post_obs_sha256,
            "post_verified": self.post_verified,
            "post_detail": self.post_detail,
            "rolled_back": self.rolled_back,
            "rollback_verified": self.rollback_verified,
            "snapshot_sha256": self.snapshot_sha256,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }


@dataclass(frozen=True)
class ReplayReport:
    """Outcome of deterministically replaying a recorded Action Journal."""

    ok: bool
    journal_ok: bool
    steps_replayed: int
    mismatches: tuple[str, ...]
    final_obs_sha256: str


class OperatorSession:
    """Closed-loop Observe -> Gate -> Snapshot -> Actuate -> Verify -> Journal -> Replay controller."""

    def __init__(
        self,
        backend: WorkstationBackend,
        gate: AuthorityGate,
        *,
        journal_path: str | Path | None = None,
        observed_targets: tuple[str, ...] = (),
    ) -> None:
        self.backend = backend
        self.gate = gate
        self.journal_path = Path(journal_path) if journal_path is not None else None
        self.observed_targets = tuple(observed_targets)
        self.records: list[OperatorStepRecord] = []
        self._head = JOURNAL_GENESIS

    def observe(self, targets: tuple[str, ...] = ()) -> WorkstationObservation:
        merged = tuple(dict.fromkeys((*self.observed_targets, *targets)))
        return self.backend.observe(merged)

    def _targets_for(self, action: OperatorAction) -> tuple[str, ...]:
        extra = (action.target,) if action.verb in ("read_file", "write_file") and action.target else ()
        return tuple(dict.fromkeys((*self.observed_targets, *extra)))

    def step(self, action: OperatorAction, *, human_approval_id: str | None = None) -> OperatorStepRecord:
        """Run one full closed-loop step and append a hash-chained journal entry."""
        watch = self._targets_for(action)
        pre_obs = self.backend.observe(watch)
        verdict = self.gate.evaluate(action, human_approval_id=human_approval_id)
        if verdict.decision != "ALLOW":
            return self._append_record(action, pre_obs, verdict, False, {}, pre_obs, False, verdict.reason, False, False, None)
        snap: RollbackSnapshot | None = self.backend.snapshot_target(action.target) if action.verb == "write_file" else None
        result = self.backend.execute(action)
        self.gate.record_execution(action)
        post_obs = self.backend.observe(watch)
        post_ok, post_detail = _check_post_state(action.expected_post, post_obs, result, action.target)
        rolled_back, rollback_ok = False, False
        if not post_ok and snap is not None:
            rolled_back = self.backend.restore_snapshot(snap)
            post_obs = self.backend.observe(watch)
            rollback_ok = post_obs.obs_sha256 == pre_obs.obs_sha256
        return self._append_record(
            action, pre_obs, verdict, True, result, post_obs, post_ok, post_detail,
            rolled_back, rollback_ok, snap.sha256 if snap else None,
        )

    def run_plan(self, actions: Sequence[OperatorAction], *, stop_on_halt: bool = True) -> list[OperatorStepRecord]:
        """Execute an ordered plan of actions, halting on valve trip or unverified failure."""
        out: list[OperatorStepRecord] = []
        for action in actions:
            rec = self.step(action)
            out.append(rec)
            if stop_on_halt and (rec.gate_verdict.valve_tripped or not rec.executed or not rec.post_verified):
                break
        return out

    def _append_record(
        self, action: OperatorAction, pre_obs: WorkstationObservation, verdict: GateVerdict,
        executed: bool, result: dict[str, Any], post_obs: WorkstationObservation,
        post_ok: bool, post_detail: str, rolled_back: bool, rollback_ok: bool, snapshot_sha256: str | None,
    ) -> OperatorStepRecord:
        seq = len(self.records)
        payload = {
            "schema": JOURNAL_SCHEMA, "seq": seq, "action": action.to_dict(),
            "pre_obs_sha256": pre_obs.obs_sha256, "gate_verdict": verdict.to_dict(),
            "executed": executed, "result": dict(result), "post_obs_sha256": post_obs.obs_sha256,
            "post_verified": post_ok, "post_detail": post_detail, "rolled_back": rolled_back,
            "rollback_verified": rollback_ok, "snapshot_sha256": snapshot_sha256,
        }
        prev = self._head
        ehash = compute_entry_hash(prev, payload)
        rec = OperatorStepRecord(
            seq=seq, action=action, pre_obs_sha256=pre_obs.obs_sha256, gate_verdict=verdict,
            executed=executed, result=dict(result), post_obs_sha256=post_obs.obs_sha256,
            post_verified=post_ok, post_detail=post_detail, rolled_back=rolled_back,
            rollback_verified=rollback_ok, snapshot_sha256=snapshot_sha256, prev_hash=prev, entry_hash=ehash,
        )
        self.records.append(rec)
        self._head = ehash
        if self.journal_path is not None:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            with self.journal_path.open("a", encoding="utf-8") as fh:
                fh.write(canonical_bytes(rec.to_entry()).decode("utf-8") + "\n")
        return rec

    def replay(self, fresh_backend: WorkstationBackend, fresh_gate: AuthorityGate) -> ReplayReport:
        """Verify the journal chain and deterministically replay all steps on a fresh backend."""
        entries = [r.to_entry() for r in self.records]
        journal_ok, j_errors, _ = verify_action_journal(self.journal_path if self.journal_path else entries)
        if not journal_ok:
            return ReplayReport(False, False, 0, tuple(j_errors), "")
        replay_session = OperatorSession(fresh_backend, fresh_gate, observed_targets=self.observed_targets)
        mismatches: list[str] = []
        for expected in self.records:
            replayed = replay_session.step(expected.action)
            if replayed.post_obs_sha256 != expected.post_obs_sha256 or replayed.entry_hash != expected.entry_hash:
                mismatches.append(f"seq {expected.seq}: digest divergence on replay")
        final_obs = replay_session.observe().obs_sha256
        return ReplayReport(len(mismatches) == 0, True, len(self.records), tuple(mismatches), final_obs)

    def seal_engine_receipt(self, out_dir: str | Path, task_id: str, *, hmac_key: str | None = None) -> tuple[Path, dict[str, Any]]:
        """Persist journal + summary report and emit a verified canonical engine-receipt/1."""
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        journal_file = self.journal_path if (self.journal_path and self.journal_path.is_file()) else out / "action_journal.jsonl"
        if not journal_file.is_file():
            journal_file.write_text("\n".join(canonical_bytes(r.to_entry()).decode("utf-8") for r in self.records) + "\n", encoding="utf-8")
        j_ok, j_errs, head = verify_action_journal(journal_file)
        pass_steps = sum(1 for r in self.records if r.executed and r.post_verified)
        fail_steps = sum(1 for r in self.records if not r.executed or not r.post_verified)
        report_file = out / "operator_report.json"
        report_payload = {
            "schema": "workstation-operator-report/1", "task_id": task_id, "journal_ok": j_ok,
            "journal_head": head, "steps_total": len(self.records), "steps_verified": pass_steps,
            "steps_halted_or_failed": fail_steps, "errors": j_errs,
        }
        report_file.write_text(json.dumps(report_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        receipt = emit_operator_engine_receipt(
            task_id, out, [journal_file, report_file],
            verified=j_ok and fail_steps == 0, pass_count=pass_steps, fail_count=fail_steps + len(j_errs),
            summary=f"operator session {task_id}: journal_ok={j_ok} verified={pass_steps}/{len(self.records)}",
            hmac_key=hmac_key,
        )
        ok, errs = verify_operator_engine_receipt(receipt, check_files=True, hmac_key=hmac_key)
        if not ok:
            raise RuntimeError(f"emitted operator engine-receipt failed self-verification: {errs}")
        receipt_path = out / "engine_receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return receipt_path, receipt
