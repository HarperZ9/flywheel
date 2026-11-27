"""Pure agent-native workspace runtime with multi-effector transactional rollback and receipts."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

from .approval_valve import CheckpointTamperError, ValveCheckpoint, create_valve_checkpoint, save_valve_checkpoint
from .delegation import DelegatedMandate, MandateEnforcer, is_hard_excluded_action
from .operator_policy import canonical_bytes, path_within_roots, sha256_prefixed

WORKSPACE_RECEIPT_SCHEMA = "workspace-session-receipt/v1"


@dataclass(frozen=True)
class WorkspaceStep:
    """Single dependency-ordered step inside an autonomous AgentWorkspace plan."""

    step_id: str
    effector: str
    action_kind: str
    target: str
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    mutates: bool = False
    reversible: bool = True
    requires_approval: bool = False
    cost: int = 1
    host: str = ""
    app: str = ""
    expected_digest: str | None = None
    rationale: str = ""


class EffectorAdapter(Protocol):
    """Unified perceive / execute / rollback interface for AgentWorkspace effectors."""

    def perceive(self, target: str) -> dict[str, Any]: ...
    def execute(self, step: WorkspaceStep) -> dict[str, Any]: ...
    def rollback(self, step: WorkspaceStep, snapshot: dict[str, Any]) -> bool: ...


class FilesystemStepAdapter:
    """Bounded filesystem adapter with bit-exact snapshots and SHA-256 verification."""

    def __init__(self, allowed_roots: tuple[str, ...]) -> None:
        self._roots = allowed_roots

    def _safe_path(self, target: str) -> Path:
        p = Path(target).resolve()
        if not path_within_roots(str(p), self._roots):
            raise PermissionError(f"filesystem target outside workspace roots: {p}")
        return p

    def perceive(self, target: str) -> dict[str, Any]:
        p = self._safe_path(target)
        raw = p.read_bytes() if p.is_file() else None
        return {"exists": raw is not None, "bytes": raw, "digest": sha256_prefixed(raw) if raw is not None else "missing"}

    def execute(self, step: WorkspaceStep) -> dict[str, Any]:
        p = self._safe_path(step.target)
        if step.action_kind == "fs.read":
            raw = p.read_bytes()
        elif step.action_kind == "fs.write":
            content = step.params.get("content", "")
            raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
        else:
            raise ValueError(f"unsupported filesystem action_kind: {step.action_kind}")
        return {"ok": True, "digest": sha256_prefixed(raw), "size": len(raw)}

    def rollback(self, step: WorkspaceStep, snapshot: dict[str, Any]) -> bool:
        p = self._safe_path(step.target)
        if snapshot.get("exists") and snapshot.get("bytes") is not None:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(snapshot["bytes"])
        elif p.is_file():
            p.unlink()
        return True


class CallableEffectorAdapter:
    """Adapter wrapping ApiEffector, WebEffector, NativeWin32Backend, OAuth, or Signer."""

    def __init__(self, *, exec_fn: Callable[[WorkspaceStep], dict[str, Any]], perceive_fn: Callable[[str], dict[str, Any]] | None = None, rollback_fn: Callable[[WorkspaceStep, dict[str, Any]], bool] | None = None) -> None:
        self._exec, self._perceive, self._rollback = exec_fn, perceive_fn, rollback_fn

    def perceive(self, target: str) -> dict[str, Any]:
        return self._perceive(target) if self._perceive else {"target": target, "digest": sha256_prefixed(target.encode("utf-8"))}

    def execute(self, step: WorkspaceStep) -> dict[str, Any]:
        return dict(self._exec(step))

    def rollback(self, step: WorkspaceStep, snapshot: dict[str, Any]) -> bool:
        return bool(self._rollback(step, snapshot)) if self._rollback else True


def _append_journal_line(journal_path: Path, kind: str, summary: str, detail: dict[str, Any]) -> str:
    prev = ""
    if journal_path.is_file():
        for line in journal_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rec = json.loads(line)
                    prev = str(rec.get("_hash", prev)) if isinstance(rec, dict) else prev
                except ValueError:
                    continue
    content = {"kind": kind, "summary": summary, "detail": detail}
    digest = hashlib.sha256(f"{prev}|{json.dumps(content, sort_keys=True, separators=(',', ':'))}".encode("utf-8")).hexdigest()
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    with journal_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({**content, "_prev": prev, "_hash": digest}, sort_keys=True, separators=(",", ":")) + "\n")
    return digest


def order_plan_steps(steps: Sequence[WorkspaceStep]) -> list[WorkspaceStep]:
    """Validate and topologically order steps by depends_on; fail-closed on missing/cyclic deps."""
    by_id = {s.step_id: s for s in steps}
    if len(by_id) != len(steps):
        raise ValueError("duplicate step_id in workspace plan")
    if any(dep not in by_id for s in steps for dep in s.depends_on):
        raise ValueError("workspace plan references unknown dependency")
    ordered, done, remaining = [], set(), list(steps)
    while remaining:
        ready = [s for s in remaining if all(d in done for d in s.depends_on)]
        if not ready:
            raise ValueError("cyclic dependency detected in workspace plan")
        for s in ready:
            ordered.append(s)
            done.add(s.step_id)
            remaining.remove(s)
    return ordered


class AgentWorkspace:
    """Self-contained agent-native workspace running transactional multi-effector plans under a mandate."""

    def __init__(self, *, workspace_id: str, root_dir: str | Path, mandate: DelegatedMandate, enforcer: MandateEnforcer) -> None:
        self.workspace_id, self.root_dir = workspace_id, Path(root_dir).resolve()
        self.scratch_dir, self.artifacts_dir = self.root_dir / "scratch", self.root_dir / "artifacts"
        self.journal_path, self.receipt_path = self.artifacts_dir / "journal.jsonl", self.artifacts_dir / "workspace_session_receipt.json"
        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.mandate, self.enforcer = mandate, enforcer
        self._effectors: dict[str, EffectorAdapter] = {"filesystem": FilesystemStepAdapter(mandate.allowed_roots)}
        self._completed_stack: list[tuple[WorkspaceStep, dict[str, Any]]] = []
        self._step_logs: list[dict[str, Any]] = []

    def register_effector(self, name: str, adapter: EffectorAdapter) -> None:
        self._effectors[name] = adapter

    def _rollback_completed(self) -> list[str]:
        rolled: list[str] = []
        while self._completed_stack:
            step, snap = self._completed_stack.pop()
            if step.reversible and step.effector in self._effectors:
                self._effectors[step.effector].rollback(step, snap)
                rolled.append(step.step_id)
                _append_journal_line(self.journal_path, "rollback", f"rolled back {step.step_id}", {"step_id": step.step_id, "target": step.target})
        return rolled

    def _seal_receipt(self, status: str, rolled_back: Sequence[str], detail: str) -> dict[str, Any]:
        head = _append_journal_line(self.journal_path, "workspace_session", f"{self.workspace_id}:{status}", {"status": status, "steps": len(self._step_logs), "rolled_back": list(rolled_back), "detail": detail})
        core = {
            "schema": WORKSPACE_RECEIPT_SCHEMA, "workspace_id": self.workspace_id, "mandate_id": self.mandate.mandate_id,
            "principal_id": self.mandate.principal_id, "agent_id": self.mandate.agent_id, "status": status,
            "detail": detail, "steps": list(self._step_logs), "rolled_back": list(rolled_back), "journal_head": head,
        }
        receipt = {**core, "receipt_sha256": sha256_prefixed(canonical_bytes(core))}
        self.receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return receipt

    def _execute_step(self, step: WorkspaceStep, *, now: float | None) -> tuple[bool, str]:
        if step.effector not in self._effectors:
            return False, f"unregistered effector: {step.effector}"
        ok, reason = self.enforcer.authorize_and_consume(
            self.mandate, action_kind=step.action_kind, target=step.target, host=step.host,
            app=step.app, mutates=step.mutates, cost=step.cost, now=now, rationale=step.rationale,
        )
        if not ok:
            return False, reason
        adapter = self._effectors[step.effector]
        pre = adapter.perceive(step.target)
        res = adapter.execute(step)
        self._completed_stack.append((step, pre))
        post = adapter.perceive(step.target)
        verified = bool(res.get("ok", True)) and (step.expected_digest is None or post.get("digest") == step.expected_digest)
        entry = {"step_id": step.step_id, "effector": step.effector, "action_kind": step.action_kind, "target": step.target, "pre_digest": str(pre.get("digest", "")), "post_digest": str(post.get("digest", "")), "verified": verified}
        self._step_logs.append(entry)
        _append_journal_line(self.journal_path, "actuation", f"{step.step_id}:{step.action_kind}", entry)
        return (True, "verified") if verified else (False, f"post-state verification drift on {step.step_id}")

    def run_plan(
        self, steps: Sequence[WorkspaceStep], *, now: float | None = None,
        checkpoint_path: str | Path | None = None, start_index: int = 0, approved_step_id: str | None = None,
    ) -> dict[str, Any]:
        ordered = order_plan_steps(steps)
        for idx in range(start_index, len(ordered)):
            step = ordered[idx]
            if is_hard_excluded_action(step.action_kind, step.target, step.rationale):
                rolled = self._rollback_completed()
                return {"status": "REFUSED_EXCLUDED", "rolled_back": rolled, "receipt": self._seal_receipt("REFUSED_EXCLUDED", rolled, f"hard exclusion on {step.step_id}")}
            if step.requires_approval and step.step_id != approved_step_id:
                cp = create_valve_checkpoint(
                    checkpoint_id=f"cp-{self.workspace_id}-{step.step_id}", workspace_id=self.workspace_id,
                    mandate_id=self.mandate.mandate_id, step_index=idx, step_id=step.step_id,
                    action_kind=step.action_kind, target=step.target, gate_reason="step requires explicit owner approval",
                    completed_step_ids=[s.step_id for s, _ in self._completed_stack],
                    remaining_step_ids=[s.step_id for s in ordered[idx:]], created_at=now,
                )
                cp_file = save_valve_checkpoint(cp, checkpoint_path or (self.artifacts_dir / "valve_checkpoint.json"))
                _append_journal_line(self.journal_path, "valve_suspended", f"suspended at {step.step_id}", cp.to_dict())
                return {"status": "SUSPENDED_NEEDS_HUMAN", "checkpoint": cp, "checkpoint_path": str(cp_file)}
            ok, reason = self._execute_step(step, now=now)
            if not ok:
                rolled = self._rollback_completed()
                status = "ROLLED_BACK" if "drift" in reason else "REFUSED_MANDATE"
                return {"status": status, "reason": reason, "rolled_back": rolled, "receipt": self._seal_receipt(status, rolled, reason)}
        return {"status": "COMPLETED", "rolled_back": [], "receipt": self._seal_receipt("COMPLETED", [], "all steps verified"), "receipt_path": str(self.receipt_path)}

    def resume_from_checkpoint(self, checkpoint: ValveCheckpoint, steps: Sequence[WorkspaceStep], *, now: float | None = None) -> dict[str, Any]:
        if not checkpoint.verify_integrity():
            raise CheckpointTamperError("refused resuming tampered ValveCheckpoint")
        if checkpoint.workspace_id != self.workspace_id or checkpoint.mandate_id != self.mandate.mandate_id:
            raise ValueError("checkpoint workspace or mandate mismatch")
        if checkpoint.status == "DENIED":
            rolled = self._rollback_completed()
            return {"status": "DENIED_ROLLED_BACK", "rolled_back": rolled, "receipt": self._seal_receipt("DENIED_ROLLED_BACK", rolled, checkpoint.decision_note or "owner denied valve")}
        if checkpoint.status != "APPROVED":
            return {"status": "SUSPENDED_NEEDS_HUMAN", "checkpoint": checkpoint}
        _append_journal_line(self.journal_path, "valve_resumed", f"resumed {checkpoint.step_id}", {"owner_decision_id": checkpoint.owner_decision_id})
        return self.run_plan(steps, now=now, start_index=checkpoint.step_index, approved_step_id=checkpoint.step_id)


def verify_workspace_session_receipt(receipt: dict[str, Any], *, journal_path: str | Path | None = None) -> tuple[bool, list[str]]:
    """Offline verifier for workspace-session-receipt/v1 and optional journal.jsonl linkage."""
    errors: list[str] = []
    if receipt.get("schema") != WORKSPACE_RECEIPT_SCHEMA:
        errors.append("unexpected workspace receipt schema")
    core = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    if receipt.get("receipt_sha256") != sha256_prefixed(canonical_bytes(core)):
        errors.append("receipt_sha256 mismatch")
    if journal_path is not None:
        head = ""
        for idx, line in enumerate(Path(journal_path).read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            rec = json.loads(line)
            content = {"kind": rec["kind"], "summary": rec["summary"], "detail": rec.get("detail", {})}
            expected = hashlib.sha256(f"{head}|{json.dumps(content, sort_keys=True, separators=(',', ':'))}".encode("utf-8")).hexdigest()
            if rec.get("_prev") != head or rec.get("_hash") != expected:
                errors.append(f"journal chain drift at entry {idx}")
                break
            head = rec["_hash"]
        if head != receipt.get("journal_head"):
            errors.append("journal_head mismatch")
    return len(errors) == 0, errors


def mcp_workspace_status(workspace_dir: str) -> dict[str, Any]:
    root, art = Path(workspace_dir), Path(workspace_dir) / "artifacts"
    return {"workspace_dir": str(root), "exists": root.is_dir(), "has_journal": (art / "journal.jsonl").is_file(), "has_receipt": (art / "workspace_session_receipt.json").is_file(), "has_checkpoint": (art / "valve_checkpoint.json").is_file()}


def mcp_workspace_plan(steps_raw: Sequence[dict[str, Any]]) -> dict[str, Any]:
    steps = [WorkspaceStep(step_id=str(s["step_id"]), effector=str(s.get("effector", "filesystem")), action_kind=str(s["action_kind"]), target=str(s.get("target", "")), depends_on=tuple(str(d) for d in s.get("depends_on", ())), requires_approval=bool(s.get("requires_approval", False)), rationale=str(s.get("rationale", ""))) for s in steps_raw]
    excluded = [s.step_id for s in steps if is_hard_excluded_action(s.action_kind, s.target, s.rationale)]
    if excluded:
        return {"ok": False, "decision": "DENY", "reason": "hard-excluded capability in plan", "excluded_steps": excluded}
    ordered = order_plan_steps(steps)
    return {"ok": True, "decision": "ALLOW_DRY_RUN", "ordered_step_ids": [s.step_id for s in ordered], "approval_gated_steps": [s.step_id for s in ordered if s.requires_approval]}


def mcp_workspace_verify_session(receipt_path: str, journal_path: str | None = None) -> dict[str, Any]:
    receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    ok, errs = verify_workspace_session_receipt(receipt, journal_path=journal_path)
    return {"ok": ok, "verdict": "MATCH" if ok else "DRIFT", "errors": errs, "workspace_id": receipt.get("workspace_id")}
