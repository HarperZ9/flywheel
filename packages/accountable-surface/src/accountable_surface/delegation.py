"""Owner-signed, revocable, monotonically-narrowable DelegatedMandate authority model."""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable

from .operator_policy import canonical_bytes, normalize_virtual_path, path_within_roots

MANDATE_SCHEMA = "accountable-surface.delegated-mandate/v1"

_HARD_EXCLUDED_RE = re.compile(
    r"(?i)(captcha|recaptcha|hcaptcha|turnstile|"
    r"anti[_\s-]?bot|stealth|fingerprint[_\s-]?patch|"
    r"bypass[_\s-]?(auth|oauth|uac|permission|sandbox)|"
    r"mass[_\s-]?(outreach|email)|obfuscated[_\s-]?outreach|"
    r"send_bulk|scrape[_\s-]?credential|token[_\s-]?harvest)"
)


class MandateError(RuntimeError):
    """Base error for delegation mandate failures."""


class MandateScopeError(MandateError):
    """Raised on hard-excluded capability or scope-widening sub-delegation."""


def is_hard_excluded_action(action_kind: str, target: str = "", rationale: str = "") -> bool:
    """Return True if an action, target, or rationale hits any hard exclusion boundary."""
    blob = f"{action_kind} {target} {rationale}"
    return bool(_HARD_EXCLUDED_RE.search(blob))


def _sign_payload(payload: dict[str, Any], signing_key: str | bytes) -> str:
    key = signing_key.encode("utf-8") if isinstance(signing_key, str) else bytes(signing_key)
    return "hmac-sha256:" + hmac.new(key, canonical_bytes(payload), hashlib.sha256).hexdigest()


def _norm_tuple(items: Iterable[str], *, lower: bool = False) -> tuple[str, ...]:
    vals = [(x.strip().lower() if lower else x.strip()) for x in items if str(x).strip()]
    return tuple(sorted(set(vals)))


@dataclass(frozen=True)
class DelegatedMandate:
    """Owner-signed, time/budget-capped delegation allowing autonomous actuation in place of owner."""

    mandate_id: str
    principal_id: str
    agent_id: str
    issued_at: float
    expires_at: float
    max_actions: int
    max_mutations: int
    max_budget_units: int
    allowed_roots: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    allowed_apps: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    parent_mandate_id: str | None = None
    signature: str = ""

    def unsigned_payload(self) -> dict[str, Any]:
        return {
            "schema": MANDATE_SCHEMA,
            "mandate_id": self.mandate_id,
            "principal_id": self.principal_id,
            "agent_id": self.agent_id,
            "issued_at": float(self.issued_at),
            "expires_at": float(self.expires_at),
            "max_actions": int(self.max_actions),
            "max_mutations": int(self.max_mutations),
            "max_budget_units": int(self.max_budget_units),
            "allowed_roots": list(self.allowed_roots),
            "allowed_hosts": list(self.allowed_hosts),
            "allowed_apps": list(self.allowed_apps),
            "allowed_actions": list(self.allowed_actions),
            "parent_mandate_id": self.parent_mandate_id,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_payload(), "signature": self.signature}

    def verify_signature(self, signing_key: str | bytes) -> bool:
        expected = _sign_payload(self.unsigned_payload(), signing_key)
        return bool(self.signature) and hmac.compare_digest(self.signature, expected)


def issue_mandate(
    *,
    mandate_id: str,
    principal_id: str,
    agent_id: str,
    signing_key: str | bytes,
    allowed_roots: Iterable[str] = (),
    allowed_hosts: Iterable[str] = (),
    allowed_apps: Iterable[str] = (),
    allowed_actions: Iterable[str] = (),
    max_actions: int = 32,
    max_mutations: int = 16,
    max_budget_units: int = 100,
    ttl_seconds: float = 3600.0,
    issued_at: float | None = None,
    parent_mandate_id: str | None = None,
) -> DelegatedMandate:
    """Issue and owner-sign a DelegatedMandate after rejecting any hard-excluded action."""
    actions = _norm_tuple(allowed_actions)
    for act in actions:
        if is_hard_excluded_action(act):
            raise MandateScopeError(f"cannot delegate hard-excluded capability: {act}")
    ts = float(time.time() if issued_at is None else issued_at)
    roots = tuple(sorted({normalize_virtual_path(r) for r in allowed_roots if str(r).strip()}))
    base = DelegatedMandate(
        mandate_id=mandate_id.strip(),
        principal_id=principal_id.strip(),
        agent_id=agent_id.strip(),
        issued_at=ts,
        expires_at=ts + max(float(ttl_seconds), 1.0),
        max_actions=max(int(max_actions), 0),
        max_mutations=max(int(max_mutations), 0),
        max_budget_units=max(int(max_budget_units), 0),
        allowed_roots=roots,
        allowed_hosts=_norm_tuple(allowed_hosts, lower=True),
        allowed_apps=_norm_tuple(allowed_apps, lower=True),
        allowed_actions=actions,
        parent_mandate_id=parent_mandate_id,
    )
    sig = _sign_payload(base.unsigned_payload(), signing_key)
    return DelegatedMandate(**{**base.__dict__, "signature": sig})


def sub_delegate_mandate(
    parent: DelegatedMandate,
    *,
    mandate_id: str,
    child_agent_id: str,
    signing_key: str | bytes,
    allowed_roots: Iterable[str] | None = None,
    allowed_hosts: Iterable[str] | None = None,
    allowed_apps: Iterable[str] | None = None,
    allowed_actions: Iterable[str] | None = None,
    max_actions: int | None = None,
    max_mutations: int | None = None,
    max_budget_units: int | None = None,
    expires_at: float | None = None,
    issued_at: float | None = None,
) -> DelegatedMandate:
    """Create a strictly narrower child mandate; fail-closed on ANY scope or ceiling widening."""
    if not parent.verify_signature(signing_key):
        raise MandateScopeError("parent mandate signature is invalid")
    c_actions = parent.allowed_actions if allowed_actions is None else _norm_tuple(allowed_actions)
    c_hosts = parent.allowed_hosts if allowed_hosts is None else _norm_tuple(allowed_hosts, lower=True)
    c_apps = parent.allowed_apps if allowed_apps is None else _norm_tuple(allowed_apps, lower=True)
    c_roots = parent.allowed_roots if allowed_roots is None else tuple(sorted({normalize_virtual_path(r) for r in allowed_roots if str(r).strip()}))
    c_max_act = parent.max_actions if max_actions is None else int(max_actions)
    c_max_mut = parent.max_mutations if max_mutations is None else int(max_mutations)
    c_max_bud = parent.max_budget_units if max_budget_units is None else int(max_budget_units)
    ts = float(time.time() if issued_at is None else issued_at)
    c_exp = parent.expires_at if expires_at is None else float(expires_at)

    if not set(c_actions).issubset(parent.allowed_actions):
        raise MandateScopeError("sub-delegation cannot widen allowed_actions")
    if not set(c_hosts).issubset(parent.allowed_hosts):
        raise MandateScopeError("sub-delegation cannot widen allowed_hosts")
    if not set(c_apps).issubset(parent.allowed_apps):
        raise MandateScopeError("sub-delegation cannot widen allowed_apps")
    for r in c_roots:
        if not path_within_roots(r, parent.allowed_roots):
            raise MandateScopeError(f"sub-delegation cannot widen allowed_roots: {r}")
    if c_max_act > parent.max_actions or c_max_mut > parent.max_mutations or c_max_bud > parent.max_budget_units:
        raise MandateScopeError("sub-delegation cannot widen action, mutation, or budget caps")
    if c_exp > parent.expires_at:
        raise MandateScopeError("sub-delegation cannot extend expires_at beyond parent")
    return issue_mandate(
        mandate_id=mandate_id, principal_id=parent.principal_id, agent_id=child_agent_id,
        signing_key=signing_key, allowed_roots=c_roots, allowed_hosts=c_hosts,
        allowed_apps=c_apps, allowed_actions=c_actions, max_actions=c_max_act,
        max_mutations=c_max_mut, max_budget_units=c_max_bud,
        ttl_seconds=max(c_exp - ts, 1.0), issued_at=ts, parent_mandate_id=parent.mandate_id,
    )


class MandateEnforcer:
    """Tracks instant revocation and atomic action/mutation/budget consumption for mandates."""

    def __init__(self, *, signing_key: str | bytes | None = None) -> None:
        self._signing_key = signing_key
        self._revoked: dict[str, str] = {}
        self._usage: dict[str, dict[str, int]] = {}

    def revoke(self, mandate_id: str, reason: str = "revoked by owner") -> None:
        self._revoked[mandate_id] = reason

    def is_revoked(self, mandate: DelegatedMandate) -> bool:
        return mandate.mandate_id in self._revoked or (
            mandate.parent_mandate_id is not None and mandate.parent_mandate_id in self._revoked
        )

    def usage_for(self, mandate_id: str) -> dict[str, int]:
        return dict(self._usage.get(mandate_id, {"actions": 0, "mutations": 0, "budget": 0}))

    def check_only(
        self, mandate: DelegatedMandate, *, action_kind: str, target: str = "",
        host: str = "", app: str = "", mutates: bool = False, cost: int = 1,
        now: float | None = None, rationale: str = "",
    ) -> tuple[bool, str]:
        if is_hard_excluded_action(action_kind, target, rationale):
            return False, "hard-excluded capability refused fail-closed"
        if self._signing_key is not None and not mandate.verify_signature(self._signing_key):
            return False, "mandate signature verification failed"
        if self.is_revoked(mandate):
            return False, f"mandate revoked: {mandate.mandate_id}"
        ts = float(time.time() if now is None else now)
        if ts >= mandate.expires_at:
            return False, f"mandate expired at {mandate.expires_at}"
        if action_kind not in mandate.allowed_actions:
            return False, f"action not delegated: {action_kind}"
        if host and host.strip().lower() not in mandate.allowed_hosts:
            return False, f"host not delegated: {host}"
        if app and app.strip().lower() not in mandate.allowed_apps:
            return False, f"app not delegated: {app}"
        if target and action_kind.startswith("fs.") and not path_within_roots(target, mandate.allowed_roots):
            return False, f"target path outside delegated roots: {target}"
        u = self._usage.get(mandate.mandate_id, {"actions": 0, "mutations": 0, "budget": 0})
        if u["actions"] + 1 > mandate.max_actions:
            return False, "mandate max_actions budget exhausted"
        if mutates and u["mutations"] + 1 > mandate.max_mutations:
            return False, "mandate max_mutations budget exhausted"
        if u["budget"] + max(int(cost), 0) > mandate.max_budget_units:
            return False, "mandate max_budget_units exhausted"
        return True, "authorized under delegated mandate"

    def authorize_and_consume(
        self, mandate: DelegatedMandate, *, action_kind: str, target: str = "",
        host: str = "", app: str = "", mutates: bool = False, cost: int = 1,
        now: float | None = None, rationale: str = "",
    ) -> tuple[bool, str]:
        ok, reason = self.check_only(
            mandate, action_kind=action_kind, target=target, host=host, app=app,
            mutates=mutates, cost=cost, now=now, rationale=rationale,
        )
        if not ok:
            return False, reason
        u = self._usage.setdefault(mandate.mandate_id, {"actions": 0, "mutations": 0, "budget": 0})
        u["actions"] += 1
        if mutates:
            u["mutations"] += 1
        u["budget"] += max(int(cost), 0)
        return True, reason
