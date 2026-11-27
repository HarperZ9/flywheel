"""Reseating approval valves and compact resumable ValveCheckpoint serialization."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .operator_policy import canonical_bytes

CHECKPOINT_SCHEMA = "accountable-surface.valve-checkpoint/v1"


class CheckpointTamperError(RuntimeError):
    """Raised when a serialized ValveCheckpoint fails integrity verification."""


def _checkpoint_digest(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


@dataclass(frozen=True)
class ValveCheckpoint:
    """Compact serialized suspension point for out-of-band owner approval and deterministic resume."""

    checkpoint_id: str
    workspace_id: str
    mandate_id: str
    step_index: int
    step_id: str
    action_kind: str
    target: str
    gate_reason: str
    completed_step_ids: tuple[str, ...]
    remaining_step_ids: tuple[str, ...]
    created_at: float
    status: str = "PENDING"
    owner_decision_id: str | None = None
    decision_note: str = ""
    checkpoint_sha256: str = ""

    def unsigned_payload(self) -> dict[str, Any]:
        return {
            "schema": CHECKPOINT_SCHEMA,
            "checkpoint_id": self.checkpoint_id,
            "workspace_id": self.workspace_id,
            "mandate_id": self.mandate_id,
            "step_index": int(self.step_index),
            "step_id": self.step_id,
            "action_kind": self.action_kind,
            "target": self.target,
            "gate_reason": self.gate_reason,
            "completed_step_ids": list(self.completed_step_ids),
            "remaining_step_ids": list(self.remaining_step_ids),
            "created_at": float(self.created_at),
            "status": self.status,
            "owner_decision_id": self.owner_decision_id,
            "decision_note": self.decision_note,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_payload(), "checkpoint_sha256": self.checkpoint_sha256}

    def verify_integrity(self) -> bool:
        return bool(self.checkpoint_sha256) and self.checkpoint_sha256 == _checkpoint_digest(self.unsigned_payload())


def create_valve_checkpoint(
    *,
    checkpoint_id: str,
    workspace_id: str,
    mandate_id: str,
    step_index: int,
    step_id: str,
    action_kind: str,
    target: str,
    gate_reason: str,
    completed_step_ids: Sequence[str],
    remaining_step_ids: Sequence[str],
    created_at: float | None = None,
) -> ValveCheckpoint:
    """Build a sealed PENDING ValveCheckpoint ready for mobile or remote review."""
    ts = float(time.time() if created_at is None else created_at)
    base = ValveCheckpoint(
        checkpoint_id=checkpoint_id,
        workspace_id=workspace_id,
        mandate_id=mandate_id,
        step_index=int(step_index),
        step_id=step_id,
        action_kind=action_kind,
        target=target,
        gate_reason=gate_reason,
        completed_step_ids=tuple(completed_step_ids),
        remaining_step_ids=tuple(remaining_step_ids),
        created_at=ts,
        status="PENDING",
    )
    return ValveCheckpoint(**{**base.__dict__, "checkpoint_sha256": _checkpoint_digest(base.unsigned_payload())})


def resolve_valve_checkpoint(
    checkpoint: ValveCheckpoint,
    *,
    approved: bool,
    owner_decision_id: str,
    note: str = "",
) -> ValveCheckpoint:
    """Transition a verified PENDING checkpoint to APPROVED or DENIED and re-seal its digest."""
    if not checkpoint.verify_integrity():
        raise CheckpointTamperError("cannot resolve tampered ValveCheckpoint")
    if checkpoint.status != "PENDING":
        raise ValueError(f"checkpoint already resolved with status: {checkpoint.status}")
    if not owner_decision_id.strip():
        raise ValueError("owner_decision_id is required")
    updated = ValveCheckpoint(
        checkpoint_id=checkpoint.checkpoint_id,
        workspace_id=checkpoint.workspace_id,
        mandate_id=checkpoint.mandate_id,
        step_index=checkpoint.step_index,
        step_id=checkpoint.step_id,
        action_kind=checkpoint.action_kind,
        target=checkpoint.target,
        gate_reason=checkpoint.gate_reason,
        completed_step_ids=checkpoint.completed_step_ids,
        remaining_step_ids=checkpoint.remaining_step_ids,
        created_at=checkpoint.created_at,
        status="APPROVED" if approved else "DENIED",
        owner_decision_id=owner_decision_id.strip(),
        decision_note=note.strip(),
    )
    return ValveCheckpoint(**{**updated.__dict__, "checkpoint_sha256": _checkpoint_digest(updated.unsigned_payload())})


def save_valve_checkpoint(checkpoint: ValveCheckpoint, path: str | Path) -> Path:
    """Persist a ValveCheckpoint as compact canonical JSON."""
    if not checkpoint.verify_integrity():
        raise CheckpointTamperError("refused saving unsealed ValveCheckpoint")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(checkpoint.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return target


def load_valve_checkpoint(path: str | Path) -> ValveCheckpoint:
    """Load and fail-closed verify a ValveCheckpoint JSON artifact."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != CHECKPOINT_SCHEMA:
        raise CheckpointTamperError("invalid ValveCheckpoint schema")
    cp = ValveCheckpoint(
        checkpoint_id=str(raw["checkpoint_id"]),
        workspace_id=str(raw["workspace_id"]),
        mandate_id=str(raw["mandate_id"]),
        step_index=int(raw["step_index"]),
        step_id=str(raw["step_id"]),
        action_kind=str(raw["action_kind"]),
        target=str(raw["target"]),
        gate_reason=str(raw["gate_reason"]),
        completed_step_ids=tuple(str(x) for x in raw.get("completed_step_ids", [])),
        remaining_step_ids=tuple(str(x) for x in raw.get("remaining_step_ids", [])),
        created_at=float(raw["created_at"]),
        status=str(raw["status"]),
        owner_decision_id=raw.get("owner_decision_id"),
        decision_note=str(raw.get("decision_note", "")),
        checkpoint_sha256=str(raw.get("checkpoint_sha256", "")),
    )
    if not cp.verify_integrity():
        raise CheckpointTamperError("ValveCheckpoint digest verification failed")
    return cp
