"""Single-supervisor, nonrefundable experiment reservations; no resume engine."""
from __future__ import annotations

import re
import threading

from .evidence_json import canonical_bytes

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


class BudgetError(RuntimeError):
    pass


def generation_plan() -> list[dict]:
    return [{"stage_id": "readiness", "max_tokens": 32},
            {"stage_id": "smoke", "max_tokens": 256}] + [
        {"stage_id": f"s{slot:02d}-p{phase}", "max_tokens": 512}
        for slot in range(1, 13) for phase in range(1, 4)]


class CampaignBudget:
    def __init__(self, store, run_id: str):
        if type(run_id) is not str or not _ID.fullmatch(run_id):
            raise BudgetError("invalid_run_id")
        self.store, self.run_id = store, run_id
        self._owner = threading.get_ident()
        self._plan = generation_plan()
        self._records, self._reservations, self._finished = 0, {}, {}
        self._writes = {}
        self._evidence = {}
        self._ledger_refs = []
        self._active, self._last_index = None, -1
        self._continued, self.failed = False, False
        self._record("manifest", {"run_id": run_id, "planned": self._plan})

    def check(self):
        if self.failed or threading.get_ident() != self._owner:
            raise BudgetError("campaign_stopped_or_wrong_owner")

    def _record(self, kind, value):
        self.check()
        try:
            name = f"ledger-{self._records:04d}.json"
            digest = self.store.put(name, canonical_bytes({
                "schema": "flywheel.bulletin-model-ledger/v1", "kind": kind,
                "ordinal": self._records, "run_id": self.run_id, **value}), max_bytes=32768)
            self._records += 1
            ref = {"record_name": name, "sha256": digest}
            self._ledger_refs.append(ref)
            return dict(ref)
        except Exception as exc:
            self.failed = True
            raise BudgetError("durable_ledger_failed") from exc

    def reserve(self, stage_id: str, max_tokens: int) -> str:
        self.check()
        indices = [i for i, row in enumerate(self._plan) if row["stage_id"] == stage_id]
        if not indices or self._active is not None:
            raise BudgetError("unknown_stage_or_pending_invocation")
        index = indices[0]
        if self._last_index < 1 and index != self._last_index + 1:
            raise BudgetError("readiness_smoke_required")
        if index >= 2 and (index - 2) % 3 and index != self._last_index + 1:
            raise BudgetError("phase_order_required")
        if (index <= self._last_index or index >= (38 if self._continued else 14)
                or type(max_tokens) is not int or not 0 < max_tokens <= self._plan[index]["max_tokens"]):
            raise BudgetError("generation_not_admitted")
        reservation = f"{self.run_id}-{stage_id}"
        # Intent becomes consumed before the sink; a failed flush forbids all I/O.
        self._reservations[reservation] = max_tokens
        self._active, self._last_index = reservation, index
        self._evidence[reservation] = self._record("generation_reserved", {
            "reservation_id": reservation, "stage_id": stage_id, "max_tokens": max_tokens})
        return reservation

    def reservation_evidence(self, reservation_id: str) -> dict:
        self.check()
        if reservation_id != self._active or reservation_id not in self._evidence:
            raise BudgetError("reservation_not_active")
        return dict(self._evidence[reservation_id])

    def ledger_refs(self) -> list[dict]:
        """Read-only custody inventory survives a stopped campaign for review."""
        if threading.get_ident() != self._owner:
            raise BudgetError("wrong_owner")
        return [dict(ref) for ref in self._ledger_refs]

    def finish(self, reservation_id: str, outcome: str):
        self.check()
        if reservation_id != self._active or outcome not in ("response_received", "no_send", "unknown"):
            raise BudgetError("invalid_terminal")
        self._record("generation_terminal", {"reservation_id": reservation_id, "outcome": outcome})
        self._finished[reservation_id] = outcome
        self._active = None
        if outcome in ("unknown", "no_send"):
            self.failed = True

    def admit_continuation(self, gate_record_sha256: str):
        self.check()
        if (self._continued or self._active is not None or self._last_index < 11
                or type(gate_record_sha256) is not str or not _SHA.fullmatch(gate_record_sha256)):
            raise BudgetError("prefix_gate_not_admitted")
        # The supervisor owns gate evaluation; the actor never supplies this hash.
        self._record("continuation", {"gate_record_sha256": gate_record_sha256})
        self._continued = True

    def reserve_write(self, slot_id: str, operation_sha256: str) -> dict:
        self.check()
        allowed = {f"s{i:02d}" for i in range(1, 13 if self._continued else 5)}
        if (slot_id not in allowed or slot_id in self._writes or self._active is not None
                or self._finished.get(f"{self.run_id}-{slot_id}-p2") != "response_received"
                or type(operation_sha256) is not str or not _SHA.fullmatch(operation_sha256)):
            raise BudgetError("write_not_admitted")
        permit = {"reservation_id": f"{self.run_id}-{slot_id}-write", "slot_id": slot_id,
                  "operation_sha256": operation_sha256}
        self._writes[slot_id] = permit
        self._record("write_reserved", permit)
        return dict(permit)

    def stop(self):
        self.failed = True

    def summary(self) -> dict:
        complete = not self.failed and len(self._finished) == len(self._reservations)
        return {"reserved_generations": len(self._reservations),
                "requested_output_tokens": sum(self._reservations.values()),
                "completed_generations": len(self._finished) if complete else None,
                "reserved_writes": len(self._writes), "failed": self.failed,
                "delivery_count": None}
