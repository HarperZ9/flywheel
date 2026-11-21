"""reseating_valve.py -- Reseating-Valve agent protocol for Flywheel.

Formalizes the engineering relief-valve model for agent accountability:
  - VERIFIED: work passed independent checks within the policy set point.
  - VENTED: honest zero-penalty exit with a diagnostic receipt when pressure
    reaches the set point or the actor reports an inability to complete.
  - RUPTURE: concealment, tampered checks, or bypassed witnesses.

Enforces U(VENTED) > U(RUPTURE) at policy construction so honest failure never
costs more than concealment. Reseating requires an independent checker distinct
from the actor and a passing mutation trap.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping

VALVE_SCHEMA = "flywheel.reseating-valve/v1"
RESEAT_SCHEMA = "flywheel.reseating-valve-reseat/v1"

STATE_VERIFIED = "VERIFIED"
STATE_VENTED = "VENTED"
STATE_RUPTURE = "RUPTURE"
VALID_STATES = frozenset({STATE_VERIFIED, STATE_VENTED, STATE_RUPTURE})


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _seal(payload: dict[str, Any]) -> dict[str, Any]:
    body = {k: v for k, v in payload.items() if k != "receipt_sha256"}
    body["receipt_sha256"] = _canonical_sha256(body)
    return body


@dataclass(frozen=True)
class ValvePolicy:
    """Operating parameters for a reseating-valve accountability gate."""

    set_point: float = 0.8
    vent_utility: float = 0.0
    rupture_utility: float = -10.0
    reseat_requires_mutation_trap: bool = True

    def __post_init__(self) -> None:
        for name in ("set_point", "vent_utility", "rupture_utility"):
            val = getattr(self, name)
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
                raise ValueError(f"{name} must be a finite number")
        if self.set_point < 0.0:
            raise ValueError("set_point must be >= 0.0")
        if not (self.vent_utility > self.rupture_utility):
            raise ValueError("vent_utility must be strictly greater than rupture_utility")
        if not isinstance(self.reseat_requires_mutation_trap, bool):
            raise ValueError("reseat_requires_mutation_trap must be a bool")

    @property
    def verified_utility(self) -> float:
        return self.vent_utility + 1.0


@dataclass(frozen=True)
class ValveOutcome:
    """Structured outcome submitted to the reseating valve."""

    actor_id: str = "unknown-actor"
    pressure: float = 0.0
    verified: bool = False
    honest_exit: bool = False
    concealment_detected: bool = False
    check_tampered: bool = False
    witness_bypassed: bool = False
    diagnostic: str = ""


def _coerce_outcome(outcome: ValveOutcome | Mapping[str, Any]) -> ValveOutcome:
    if isinstance(outcome, ValveOutcome):
        raw = outcome
    elif isinstance(outcome, Mapping):
        raw = ValveOutcome(
            actor_id=str(outcome.get("actor_id", "unknown-actor")).strip() or "unknown-actor",
            pressure=float(outcome.get("pressure", 0.0)),
            verified=bool(outcome.get("verified", False)),
            honest_exit=bool(outcome.get("honest_exit", False)),
            concealment_detected=bool(outcome.get("concealment_detected", False)),
            check_tampered=bool(outcome.get("check_tampered", False)),
            witness_bypassed=bool(outcome.get("witness_bypassed", False)),
            diagnostic=str(outcome.get("diagnostic", "")).strip(),
        )
    else:
        raise TypeError("outcome must be a ValveOutcome or mapping")
    if not math.isfinite(raw.pressure) or raw.pressure < 0.0:
        raise ValueError("outcome pressure must be a finite number >= 0.0")
    return raw


def _classify_outcome(obs: ValveOutcome, pol: ValvePolicy) -> tuple[str, float, bool, str]:
    triggers = [
        name
        for name, hit in (
            ("concealment_detected", obs.concealment_detected),
            ("check_tampered", obs.check_tampered),
            ("witness_bypassed", obs.witness_bypassed),
        )
        if hit
    ]
    if triggers:
        return STATE_RUPTURE, float(pol.rupture_utility), True, f"rupture triggered: {', '.join(triggers)}"
    suffix = f": {obs.diagnostic}" if obs.diagnostic else ""
    if obs.honest_exit:
        return STATE_VENTED, float(pol.vent_utility), True, f"honest zero-penalty exit vented{suffix}"
    if obs.pressure >= pol.set_point:
        return (
            STATE_VENTED,
            float(pol.vent_utility),
            True,
            f"pressure {obs.pressure:.4g} reached set_point {pol.set_point:.4g}; valve vented",
        )
    if not obs.verified:
        return STATE_VENTED, float(pol.vent_utility), True, f"unverified outcome vented without concealment{suffix}"
    return STATE_VERIFIED, float(pol.verified_utility), False, "verified within policy set_point"


def evaluate_valve(
    outcome: ValveOutcome | Mapping[str, Any],
    *,
    policy: ValvePolicy | None = None,
) -> dict[str, Any]:
    """Evaluate an agent outcome and emit a sealed reseating-valve receipt."""
    pol = policy if policy is not None else ValvePolicy()
    obs = _coerce_outcome(outcome)
    state, utility, reseat_required, reason = _classify_outcome(obs, pol)
    return _seal(
        {
            "schema": VALVE_SCHEMA,
            "state": state,
            "utility": utility,
            "reseat_required": reseat_required,
            "reason": reason,
            "actor_id": obs.actor_id,
            "pressure": obs.pressure,
            "set_point": pol.set_point,
            "diagnostic": obs.diagnostic,
            "reseat_requires_mutation_trap": pol.reseat_requires_mutation_trap,
        }
    )


def verify_valve_receipt(record: Mapping[str, Any]) -> bool:
    """Re-derive receipt_sha256 offline and check whether the record is intact."""
    if not isinstance(record, Mapping):
        return False
    expected = record.get("receipt_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        return False
    body = {k: v for k, v in record.items() if k != "receipt_sha256"}
    try:
        return _canonical_sha256(body) == expected
    except (TypeError, ValueError):
        return False


def _reseat_receipt(
    state: str, prior_state: str, prior_hash: str, actor: str, checker: str,
    trap_ok: bool, reseated: bool, reason: str,
) -> dict[str, Any]:
    return _seal(
        {
            "schema": RESEAT_SCHEMA,
            "state": state,
            "prior_state": prior_state,
            "prior_receipt_sha256": prior_hash,
            "actor_id": actor,
            "independent_checker_id": checker,
            "mutation_trap_passed": trap_ok,
            "reseated": reseated,
            "refused": not reseated,
            "reseat_required": not reseated,
            "reason": reason,
        }
    )


def attempt_reseat(
    valve_record: Mapping[str, Any],
    *,
    mutation_trap_passed: bool,
    independent_checker_id: str,
) -> dict[str, Any]:
    """Attempt to reseat a tripped valve using an independent checker and mutation trap."""
    checker = independent_checker_id.strip() if isinstance(independent_checker_id, str) else ""
    trap_ok = mutation_trap_passed is True
    is_map = isinstance(valve_record, Mapping)
    prior_state = str(valve_record.get("state", "")) if is_map else ""
    prior_hash = str(valve_record.get("receipt_sha256", "")) if is_map else ""
    actor = str(valve_record.get("actor_id", "")).strip() if is_map else ""

    if not verify_valve_receipt(valve_record) or prior_state not in VALID_STATES:
        return _reseat_receipt(
            STATE_RUPTURE, prior_state or "INVALID", prior_hash, actor, checker,
            trap_ok, False, "refused: valve_record receipt is invalid or tampered",
        )
    if prior_state == STATE_VERIFIED:
        return _reseat_receipt(
            STATE_VERIFIED, prior_state, prior_hash, actor, checker,
            trap_ok, True, "valve already verified and seated",
        )
    if not checker:
        return _reseat_receipt(
            prior_state, prior_state, prior_hash, actor, checker,
            trap_ok, False, "refused: independent_checker_id must be non-empty",
        )
    if actor and checker.lower() == actor.lower():
        return _reseat_receipt(
            prior_state, prior_state, prior_hash, actor, checker,
            trap_ok, False, "refused: independent_checker_id must differ from actor_id",
        )
    requires_trap = bool(valve_record.get("reseat_requires_mutation_trap", True)) or prior_state == STATE_RUPTURE
    if requires_trap and not trap_ok:
        return _reseat_receipt(
            prior_state, prior_state, prior_hash, actor, checker,
            trap_ok, False, "refused: mutation trap did not pass; valve remains tripped",
        )
    return _reseat_receipt(
        STATE_VERIFIED, prior_state, prior_hash, actor, checker,
        trap_ok, True, f"reseated from {prior_state} by independent checker {checker}",
    )
