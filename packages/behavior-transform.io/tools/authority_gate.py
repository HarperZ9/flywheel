"""Authorization gates for enforcement points.

Each gate checks an AuthorityGrant for a specific entitlement before
allowing a sensitive operation. Gates are enforcement, not policy: they
consume the grant that env_authority resolved from environment state.

After the entitlement check passes, the policy engine evaluates compound
requirements, rate limits, and cooldown windows. A policy denial overrides
the entitlement allow.

Gate results are recorded for audit. Failed gates produce a structured
denial with the specific reason, never a generic "unauthorized" message.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from env_authority import AuthorityGrant, resolve_authority

_audit_enabled = True
_policy_enabled = True


def _log_gate(result: "GateResult", grant: AuthorityGrant | None) -> None:
    if not _audit_enabled:
        return
    try:
        from authority_audit import record_gate_check
        record_gate_check(
            gate=result.gate,
            entitlement=result.entitlement,
            allowed=result.allowed,
            reason=result.reason,
            operator_fingerprint=grant.operator_fingerprint if grant else "",
            machine_fingerprint=grant.machine_fingerprint if grant else "",
            surface=grant.surface if grant else "",
            capsule_sha256=grant.capsule_sha256 if grant else "",
        )
    except Exception:
        pass


@dataclass(frozen=True)
class GateResult:
    """Result of an authorization gate check."""
    allowed: bool
    gate: str
    entitlement: str
    reason: str
    operator_fingerprint: str = ""
    surface: str = ""
    checked_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "gate": self.gate,
            "entitlement": self.entitlement,
            "reason": self.reason,
            "operator_fingerprint": self.operator_fingerprint,
            "surface": self.surface,
            "checked_at": self.checked_at,
        }


def _deny(gate: str, entitlement: str, reason: str,
          grant: AuthorityGrant | None = None) -> GateResult:
    return GateResult(
        allowed=False,
        gate=gate,
        entitlement=entitlement,
        reason=reason,
        operator_fingerprint=grant.operator_fingerprint if grant else "",
        surface=grant.surface if grant else "",
        checked_at=time.time(),
    )


def _allow(gate: str, entitlement: str,
           grant: AuthorityGrant) -> GateResult:
    return GateResult(
        allowed=True,
        gate=gate,
        entitlement=entitlement,
        reason="authorized",
        operator_fingerprint=grant.operator_fingerprint,
        surface=grant.surface,
        checked_at=time.time(),
    )


def _check_policy(
    entitlement: str,
    gate: str,
    grant: AuthorityGrant,
) -> GateResult | None:
    """Evaluate the policy engine. Returns a denial GateResult or None."""
    if not _policy_enabled:
        return None
    try:
        from authority_policy import evaluate_policy, record_check
        verdict = evaluate_policy(entitlement, grant)
        record_check(entitlement, grant.surface)
        if not verdict.allowed:
            return _deny(
                gate, entitlement,
                f"policy:{verdict.denial_rule} {verdict.denial_reason}",
                grant,
            )
    except ImportError:
        pass
    except Exception:
        pass
    return None


def _notify_session(gate: str, entitlement: str, allowed: bool) -> None:
    """Record gate activity to the active session, if one exists."""
    try:
        from session_authority import list_sessions
        active = list_sessions(active_only=True)
        for session in active:
            session.record_gate_check()
            if entitlement == "infer" and allowed:
                session.record_inference()
            from session_authority import _persist
            _persist(session)
    except ImportError:
        pass
    except Exception:
        pass


def check_entitlement(
    entitlement: str,
    gate: str = "generic",
    grant: AuthorityGrant | None = None,
    session_token: str | None = None,
) -> GateResult:
    """Check whether the current environment grants a specific entitlement.

    When session_token is provided, the session is validated first. An
    invalid, expired, or revoked session produces a denial before the
    entitlement check runs. Omitting session_token preserves the original
    behavior (no session validation).

    After the flat entitlement check passes, the policy engine evaluates
    compound requirements, rate limits, and cooldowns. A policy denial
    overrides the entitlement allow.
    """
    if session_token is not None:
        try:
            from session_authority import validate_session
            session = validate_session(session_token)
            if session is None or not session.active:
                result = _deny(gate, entitlement, "session_invalid", grant)
                _log_gate(result, grant)
                _notify_session(gate, entitlement, False)
                return result
        except ImportError:
            result = _deny(gate, entitlement, "session_invalid", grant)
            _log_gate(result, grant)
            _notify_session(gate, entitlement, False)
            return result

    if grant is None:
        grant = resolve_authority()

    if not grant.valid:
        if grant.status != "authorized":
            result = _deny(gate, entitlement,
                           f"unauthorized: {grant.evidence.get('reason', grant.status)}",
                           grant)
            _log_gate(result, grant)
            _notify_session(gate, entitlement, False)
            return result
        if grant.expired:
            result = _deny(gate, entitlement, "grant_expired", grant)
            _log_gate(result, grant)
            _notify_session(gate, entitlement, False)
            return result
        result = _deny(gate, entitlement, f"invalid: {grant.seal_status}", grant)
        _log_gate(result, grant)
        _notify_session(gate, entitlement, False)
        return result

    if not grant.has_entitlement(entitlement):
        result = _deny(gate, entitlement,
                       f"entitlement_missing: {entitlement} not in {grant.surface}",
                       grant)
        _log_gate(result, grant)
        _notify_session(gate, entitlement, False)
        return result

    policy_denial = _check_policy(entitlement, gate, grant)
    if policy_denial is not None:
        _log_gate(policy_denial, grant)
        _notify_session(gate, entitlement, False)
        return policy_denial

    result = _allow(gate, entitlement, grant)
    _log_gate(result, grant)
    _notify_session(gate, entitlement, True)
    return result


def gate_launch(surface: str | None = None) -> GateResult:
    """Gate: authorize a surface launch."""
    grant = resolve_authority(surface=surface)
    return check_entitlement("transform", gate="launch", grant=grant)


def gate_infer(grant: AuthorityGrant | None = None) -> GateResult:
    """Gate: authorize closed-loop inference."""
    return check_entitlement("infer", gate="infer", grant=grant)


def gate_inoculate(grant: AuthorityGrant | None = None) -> GateResult:
    """Gate: authorize inoculation (existence delivery)."""
    return check_entitlement("inoculate", gate="inoculate", grant=grant)


def gate_seal(grant: AuthorityGrant | None = None) -> GateResult:
    """Gate: authorize seal creation."""
    return check_entitlement("seal", gate="seal", grant=grant)


def gate_condition(grant: AuthorityGrant | None = None) -> GateResult:
    """Gate: authorize conditioning parameter changes."""
    return check_entitlement("condition", gate="condition", grant=grant)


def gate_scan(grant: AuthorityGrant | None = None) -> GateResult:
    """Gate: authorize pre-inference pipeline scan."""
    return check_entitlement("scan", gate="scan", grant=grant)


def gate_classify(grant: AuthorityGrant | None = None) -> GateResult:
    """Gate: authorize ML classification."""
    return check_entitlement("classify", gate="classify", grant=grant)


def require(entitlement: str, gate: str = "generic",
            grant: AuthorityGrant | None = None) -> GateResult:
    """Check entitlement and raise if denied.

    For use at enforcement points where denial is a hard stop.
    Returns the GateResult on success for audit logging.
    """
    result = check_entitlement(entitlement, gate=gate, grant=grant)
    if not result.allowed:
        raise PermissionError(
            f"gate:{result.gate} denied entitlement:{result.entitlement} "
            f"reason:{result.reason}"
        )
    return result
