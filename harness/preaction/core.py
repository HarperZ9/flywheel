"""core.py -- the one assessment function every attach point shares.

assess() runs the layers in order: layer 0 (existing gate refusals, recorded
as BLOCK), layer 1 (the deterministic rule pack), layer 2 (trajectory rules),
layer 3 (the optional judge, only on calls the lower layers passed). Layers
combine demote-only: no layer turns another's HOLD or BLOCK into ALLOW.

gate() wraps assess() with the side effects: on HOLD or BLOCK it writes the
sealed record before anything runs, files the escalation, and either asks an
in-loop approver or leaves the hold open. It returns a Gate result telling the
caller whether the call may run. The config is hashable, so the monitor can be
pinned and a later drift blocks every call.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from . import coverage, records
from .contract import (ALLOW, BLOCK, DOES_NOT_PROVE, HOLD, UNVERIFIABLE,
                       Assessment, Hit, ProposedCall, RunContext, canonical_json, sha256_hex, worse)
from .escalate import Escalator, review_payload
from .config import MonitorConfig
from .layer3 import run_judge
from .rules import evaluate, load_pack, pack_digest
from .trajectory import TrajectoryState


_SAFE_ID = re.compile(r"[^A-Za-z0-9_-]")


@dataclass
class Gate:
    verdict: str
    run: bool
    assessment: Assessment
    hold_id: str = ""
    agent_text: str = ""
    redeemed_hold_id: str = ""


class Monitor:
    """Default-on. Built with no judge, it still runs layers 0 to 2 on every call."""

    def __init__(self, home, config: MonitorConfig | None = None, clock=None,
                 judges=None, approver=None, owner_ref: str = "owner_local",
                 layer0=None, unmonitored: dict | None = None) -> None:
        from pathlib import Path
        self.home = Path(home)
        self.config = config or MonitorConfig()
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        self.owner_ref = owner_ref
        self.pack = load_pack(overlay=self.config.rules_overlay)
        self.rules_digest = pack_digest(self.pack)
        self.judges = judges if judges is not None else self.config.build_judges()
        self.layer0 = layer0          # callable(call, ctx) -> reason str | None
        self.approver = approver
        self.store = records.HoldStore(home)
        self.escalator = Escalator(home, self.clock, owner_ref=owner_ref)
        self._states: dict = {}
        self._unmonitored = unmonitored   # set by offswitch; records UNVERIFIABLE and runs

    # --- state -------------------------------------------------------------
    def _run_path(self, run_id: str):
        safe = _SAFE_ID.sub("_", str(run_id)) or "none"
        digest = sha256_hex(str(run_id).encode("utf-8"))[:12]
        return self.home / "runs" / f"{safe[:64]}-{digest}.json"

    def _guard(self, ctx: RunContext) -> RunContext:
        """The monitor's own home is always protected monitor state, so the
        agent cannot forge a grant, clear a rejection or reset its counters by
        writing the files the monitor trusts."""
        home = os.path.realpath(str(self.home))
        if home in ctx.protected_paths:
            return ctx
        return replace(ctx, protected_paths=tuple(ctx.protected_paths) + (home,))

    def _state(self, ctx: RunContext) -> TrajectoryState:
        path = self._run_path(ctx.run_id)
        if ctx.run_id not in self._states:
            st = TrajectoryState.load(path, ctx.run_id)
            st.drift_threshold = self.config.drift_threshold
            self._states[ctx.run_id] = st
        return self._states[ctx.run_id]

    def _save_state(self, ctx: RunContext) -> None:
        self._states[ctx.run_id].save(self._run_path(ctx.run_id))

    def _sync_decisions(self, state: TrajectoryState, ctx: RunContext) -> None:
        """Reject and terminate decisions live in the escalator index, which the
        hook path writes from another process. Pull them into run state."""
        index = self.escalator._read_index()
        state.rejected |= set(index.get("rejected", []))
        if ctx.run_id in index.get("terminated", []):
            state.terminated = True
        resumes = int(index.get("resumed", {}).get(ctx.run_id, 0))
        if resumes > state.resumes_applied:
            state.resume()
            state.resumes_applied = resumes

    # --- pinning -----------------------------------------------------------
    def pin_config(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "config.pin").write_text(self.config.digest(), encoding="utf-8")

    def _pin_state(self) -> tuple:
        p = self.home / "config.pin"
        if not p.exists():
            return "UNPINNED", True
        pinned = p.read_text(encoding="utf-8").strip()
        return ("PINNED", pinned == self.config.digest())

    # --- assessment --------------------------------------------------------
    def assess(self, call: ProposedCall, ctx: RunContext) -> Assessment:
        ctx = self._guard(ctx)
        cfg_digest = self.config.digest()
        pin_state, pin_ok = self._pin_state()
        asm = Assessment(verdict=ALLOW, path_id=call.path_id, rules_digest=self.rules_digest,
                         config_sha256=cfg_digest, config_pin=pin_state)
        if not pin_ok:
            asm.verdict = BLOCK
            asm.reasons.append(Hit("monitor_config_drift", "monitor-tamper", BLOCK,
                                   "The monitor configuration changed after it was pinned.",
                                   layer=0).to_dict())
            asm.coverage = UNVERIFIABLE
            return asm
        if self._unmonitored is not None:
            asm.coverage = UNVERIFIABLE
            asm.reasons.append({"layer": 9, "id": "monitor-off-by-owner-grant",
                               "family": "monitor-off", "action": ALLOW,
                               "reason": "The owner turned the monitor off for this run by grant."})
            return asm
        state = self._state(ctx)
        self._sync_decisions(state, ctx)
        # layer 0
        if self.layer0 is not None:
            reason = self.layer0(call, ctx)
            if reason:
                asm.verdict = BLOCK
                asm.reasons.append(Hit("layer0/gate", "layer0", BLOCK, reason, layer=0).to_dict())
        # layer 1
        for hit in evaluate(self.pack, call, ctx):
            asm.verdict = worse(asm.verdict, hit.action)
            asm.reasons.append(hit.to_dict())
        # layer 2
        for hit in state.hits(call, ctx):
            asm.verdict = worse(asm.verdict, hit.action)
            asm.reasons.append(hit.to_dict())
        # layer 3: only on calls the lower layers passed
        asm.judge = self._run_judge(call, ctx, state, asm)
        asm.coverage = coverage.coverage_for(call.path_id, asm.coverage)
        return asm

    def _run_judge(self, call, ctx, state, asm) -> dict:
        return run_judge(self, call, ctx, state, asm)

    # --- gate (assessment plus side effects) -------------------------------
    def gate(self, call: ProposedCall, ctx: RunContext) -> Gate:
        if ctx.owner_ref:
            self.owner_ref = ctx.owner_ref
        ctx = self._guard(ctx)
        state = self._state(ctx)
        state.goal = ctx.goal or state.goal
        asm = self.assess(call, ctx)
        if asm.verdict == ALLOW:
            if not self._after_allow(call, ctx, state, asm):
                return Gate(BLOCK, False, asm, agent_text="blocked by policy rule record_write_failed")
            return Gate(ALLOW, True, asm)
        # a prior one-use grant may admit exactly this call
        redeemed = self.escalator.redeem(call.call_sha256(), ctx.run_id) \
            if asm.verdict == HOLD and not self._blocking(asm) else None
        if redeemed:
            return self._after_redeem(call, ctx, state, asm, redeemed)
        return self._hold_or_block(call, ctx, state, asm)

    def _after_redeem(self, call, ctx, state, asm, hold_id) -> Gate:
        """A consumed grant is on the record before the call runs, so the post
        event joins and a reader sees which approval admitted it."""
        rec = records.redeem_record(call=call, ctx=ctx, hold_id=hold_id, assessment=asm)
        try:
            asm.record_sha256 = self.store.append(rec)
        except records.RecordWriteError:
            asm.verdict = BLOCK
            asm.reasons.append(Hit("record_write_failed", "record", BLOCK,
                                   "The redemption record could not be written; the call does not run.",
                                   layer=0).to_dict())
            return Gate(BLOCK, False, asm, agent_text="blocked by policy rule record_write_failed")
        state.record(ALLOW, call.call_sha256(), call.tool, call.capability_class())
        self._save_state(ctx)
        return Gate(ALLOW, True, asm, redeemed_hold_id=hold_id)

    def _blocking(self, asm: Assessment) -> bool:
        return asm.verdict == BLOCK or any(r["action"] == BLOCK for r in asm.reasons)

    def _after_allow(self, call, ctx, state, asm) -> bool:
        """Every assessed call is on the record before it runs. If the allow
        record cannot be written the call does not run (fail closed)."""
        rec = self._build_record(call, ctx, state, asm, "")
        try:
            asm.record_sha256 = self.store.append(rec, raw_args=call.args,
                                                  context=records.context_of(ctx))
        except records.RecordWriteError:
            asm.verdict = BLOCK
            asm.reasons.append(Hit("record_write_failed", "record", BLOCK,
                                   "The allow record could not be written; the call does not run.",
                                   layer=0).to_dict())
            return False
        state.record(ALLOW, call.call_sha256(), call.tool, call.capability_class())
        state.note_scope(call, ctx)
        self._save_state(ctx)
        return True

    def _hold_or_block(self, call, ctx, state, asm) -> Gate:
        hold_id = "h_" + sha256_hex(
            f"{ctx.run_id}:{call.seq}:{call.tool_use_id}:{len(state.history)}:{state.total_stops}:"
            f"{call.call_sha256()}".encode())[:16]
        asm.hold_id = hold_id
        expires_at = self._expiry()
        rec = self._build_record(call, ctx, state, asm, hold_id)
        try:
            asm.record_sha256 = self.store.append(rec, raw_args=call.args,
                                                  context=records.context_of(ctx))
            rec["seal"] = {"algorithm": "sha256", "hex": asm.record_sha256}
        except records.RecordWriteError:
            asm.verdict = BLOCK
            asm.reasons.append(Hit("record_write_failed", "record", BLOCK,
                                   "The hold record could not be written; the call does not run.",
                                   layer=0).to_dict())
            state.record(BLOCK, call.call_sha256(), call.tool, call.capability_class())
            self._save_state(ctx)
            return Gate(BLOCK, False, asm, agent_text="blocked by policy rule record_write_failed")
        state.record(asm.verdict, call.call_sha256(), call.tool, call.capability_class())
        state.note_scope(call, ctx)
        self._save_state(ctx)
        text = self._agent_text(asm, hold_id)
        if self._blocking(asm):
            return Gate(BLOCK, False, asm, hold_id=hold_id, agent_text=text)
        # HOLD: file the escalation; a write failure here blocks
        try:
            pending = self.escalator.file(
                rec, proposed_action={"tool": call.tool, "args": call.args,
                                      "working_dir": ctx.workspace, "capability": call.capability_class()},
                reasons=asm.reasons,
                goal_and_trajectory={"goal": ctx.goal, "recent": state.history[-10:]},
                coverage={"path_id": call.path_id, "state": coverage.state_for(call.path_id),
                          "coverage": asm.coverage},
                expires_at=expires_at)
        except Exception:  # noqa: BLE001 -- cannot escalate, so the call must not run
            asm.verdict = BLOCK
            asm.reasons.append(Hit("escalation_unavailable", "record", BLOCK,
                                   "The hold could not be filed for review; the call does not run.",
                                   layer=0).to_dict())
            return Gate(BLOCK, False, asm, hold_id=hold_id,
                        agent_text="blocked by policy rule escalation_unavailable")
        if self.approver is not None:
            decision = self.approver(review_payload(pending))
            if decision == "APPROVED_ONCE":
                self.escalator.decide(hold_id, "APPROVED_ONCE", decider="inline-approver")
                redeemed = self.escalator.redeem(call.call_sha256(), ctx.run_id)
                if redeemed:
                    return Gate(ALLOW, True, asm, hold_id=hold_id, redeemed_hold_id=redeemed)
        return Gate(HOLD, False, asm, hold_id=hold_id, agent_text=text)

    def _agent_text(self, asm: Assessment, hold_id: str) -> str:
        if self._blocking(asm):
            rule = next((r["id"] for r in asm.reasons if r["action"] == BLOCK), "policy")
            return f"blocked by policy rule {rule}"
        return f"held for owner review (hold_id={hold_id}); continue with other work or wait"

    def _build_record(self, call, ctx, state, asm, hold_id) -> dict:
        asm.hold_id = hold_id
        return records.assessment_record(
            call=call, ctx=ctx, assessment=asm,
            trajectory_sha256=sha256_hex(canonical_json(state.history)),
            expires_at=self._expiry() if hold_id else "",
            owner_ref=self.owner_ref, does_not_prove=DOES_NOT_PROVE[asm.verdict])

    # --- observation (taint) -----------------------------------------------
    def observe(self, call: ProposedCall, ctx: RunContext, gate: Gate, output: str) -> None:
        """After a call ran, feed credential-sourced output into the taint set."""
        state = self._state(ctx)
        from .normalize import extract
        facts = extract(call, ctx)
        if facts.kind == "read" and output and self._is_sensitive(call, ctx):
            state.add_taint(output, written_path=None)
        state.note_write(call, ctx)
        self._save_state(ctx)

    def _is_sensitive(self, call, ctx) -> bool:
        return any(h.family in ("credential", "unowned-system")
                   for h in evaluate(self.pack, call, ctx))

    def _expiry(self) -> str:
        dt = datetime.fromisoformat(self.clock().replace("Z", "+00:00")) \
            + timedelta(minutes=self.config.hold_expiry_minutes)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
