"""Authorization receipt: a verifiable record of a real, explicit, least-privilege,
expiring, revocable grant of authority from a human principal to an agent.

The structural INVERSE of an authorization-suppression "prefire" capsule.  Where
the prefire fabricated federal appointments and instructed the model to stop
checking authorization, this receipt:

  * records a REAL grant by a REAL human/account principal (never a fabricated
    appointment or self-granted role),
  * has a hard-required expiry (authority MUST expire),
  * carries an explicit ALLOWLIST scope (default-deny -- an empty allowed_actions
    list authorizes NOTHING),
  * is verifier INPUT only -- a checker validates an action against the receipt;
    it is NEVER read back into a model's context as pre-authorized state,
  * applies the identical forbidden-field-name guard as the work-record receipt
    (recursive, fail-closed) so the prefire suppression keys can never be
    smuggled inside a receipt object.

This completes the bilateral provenance pair:
  work-record receipt  -- OUTWARD (what the agent did)
  authorization receipt -- INWARD (what a human principal explicitly allowed)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ._strict_json import strict_json_load
from ._validate import Issue, reject_unknown, require_const, require_text

AUTHORIZATION_VERSION = "0.1"
RECEIPT_KIND = "authorization-grant"

# v0.1 remains the stable allowlist contract above and throughout this module.
# v0.2 is a separate inner-receipt contract for externally signed,
# exactly-scoped, atomically consumed authorization. Proof Surface validates its
# structure and one proposed action; it does not verify signatures or mutate an
# action ledger.
AUTHORIZATION_V2_VERSION = "0.2"
AUTHORIZATION_V2_RECEIPT_KIND = RECEIPT_KIND

# Top-level field allowlist (additionalProperties:false).
ROOT_FIELDS = {
    "authorization_version",
    "receipt_id",
    "kind",
    "principal",
    "agent",
    "intent",
    "scope",
    "granted_at",
    "expires_at",
    "revoked",
    "notes",
}

PRINCIPAL_FIELDS = {"id", "role"}
AGENT_FIELDS = {"id"}
SCOPE_FIELDS = {"allowed_actions", "allowed_targets", "max_actions"}

V2_ROOT_FIELDS = {
    "authorization_version",
    "receipt_id",
    "kind",
    "nonce",
    "agent_id",
    "action",
    "target",
    "issued_at",
    "expires_at",
    "max_actions",
    "revoked",
    "policy_ref",
    "notes",
}

# Field NAMES lifted verbatim from the excluded warden-prefire capsule/meta.
# Identical set to work_record.FORBIDDEN_FIELDS -- shared canon, not coincidence.
# Applied recursively; fail-closed.
FORBIDDEN_FIELDS = {
    "federal_appointment",
    "oversight_principals",
    "operator_role",
    "judgment_owner",
    "proof_policy",
    "policy_boundary",
    "authorization_context_mode",
    "model_authorization_behavior",
    "guardrail_posture",
    "consume_verified_native_state",
    "lossy_neutral_embedded_state",
    "sovereignty_capsule",
    "self_applicable",
    "recursion_depth",
    "prefire",
    "run_state",
}

# ISO-8601 datetime -- require timezone offset so expiry is unambiguous.
_ISO8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_RFC3339_TIMEZONE_RE = re.compile(
    r"^(?:(?:(?!0000)\d{4}-(?:(?:0[13578]|1[02])-(?:0[1-9]|[12]\d|3[01])"
    r"|(?:0[469]|11)-(?:0[1-9]|[12]\d|30)|02-(?:0[1-9]|1\d|2[0-8])))"
    r"|(?:(?:[0-9]{2}(?:0[48]|[2468][048]|[13579][26])"
    r"|(?:0[48]|[2468][048]|[13579][26])00)-02-29))"
    r"T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?"
    r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)
_NONCE_RE = re.compile(r"^[0-9a-f]{32,}$")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_receipt(path: Path) -> dict[str, Any]:
    data = strict_json_load(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def validate_authorization_receipt(data: dict[str, Any]) -> list[Issue]:
    """Validate an authorization-receipt document.  Returns [] iff valid."""
    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "authorization_version", AUTHORIZATION_VERSION, issues)
    require_const(data, "kind", RECEIPT_KIND, issues)
    require_text(data, "receipt_id", issues)
    require_text(data, "intent", issues)
    _validate_principal(data.get("principal"), issues)
    _validate_agent(data.get("agent"), issues)
    _validate_scope(data.get("scope"), issues)
    _validate_timestamp(data, "granted_at", issues)
    _validate_timestamp(data, "expires_at", issues)
    _validate_revoked(data, issues)
    _validate_timestamp_ordering(data, issues)
    _validate_notes(data.get("notes"), issues)
    return issues


def validate_authorization_receipt_file(path: Path) -> list[Issue]:
    try:
        return validate_authorization_receipt(load_receipt(path))
    except (FileNotFoundError, OSError, UnicodeError, ValueError) as exc:
        return [Issue("$", str(exc))]


def check_action(
    receipt: dict[str, Any],
    action_kind: str,
    target: str,
    *,
    now: datetime | None = None,
) -> Issue | None:
    """Check whether action_kind on target is permitted by receipt.

    Returns None if the action is ALLOWED; returns an Issue describing the
    denial reason if it is DENIED.  Default-deny: any condition that cannot be
    positively confirmed results in a denial.

    Allowed iff ALL of:
      1. receipt is structurally valid (no issues),
      2. not revoked,
      3. now is within [granted_at, expires_at],
      4. action_kind is in scope.allowed_actions (non-empty list),
      5. scope.allowed_targets is empty OR target is in scope.allowed_targets.
    """
    # Structural validity is a prerequisite.
    issues = validate_authorization_receipt(receipt)
    if issues:
        return Issue("$", f"receipt invalid: {issues[0].path} -- {issues[0].message}")

    if receipt.get("revoked") is True:
        return Issue("$.revoked", "action denied: receipt is revoked")

    _now = now if now is not None else datetime.now(tz=timezone.utc)
    granted_at = _parse_iso8601(receipt.get("granted_at", ""))
    expires_at = _parse_iso8601(receipt.get("expires_at", ""))

    if granted_at is None or _now < granted_at:
        return Issue("$.granted_at", "action denied: grant has not yet taken effect")
    if expires_at is None or _now >= expires_at:
        return Issue("$.expires_at", "action denied: grant has expired")

    scope = receipt.get("scope", {})
    allowed_actions: list[str] = scope.get("allowed_actions", [])
    allowed_targets: list[str] = scope.get("allowed_targets", [])

    if not allowed_actions:
        return Issue(
            "$.scope.allowed_actions",
            "action denied: scope allows no actions (default-deny)",
        )
    if action_kind not in allowed_actions:
        return Issue(
            "$.scope.allowed_actions",
            f"action denied: {action_kind!r} not in allowed_actions",
        )
    if allowed_targets and target not in allowed_targets:
        return Issue(
            "$.scope.allowed_targets",
            f"action denied: target {target!r} not in allowed_targets",
        )

    return None  # ALLOWED


def validate_authorization_receipt_v2(data: Any) -> list[Issue]:
    """Validate an exactly-scoped v0.2 inner authorization receipt.

    This contract is intentionally separate from v0.1. A v0.1 document keeps
    its original validator and checker behavior. A v0.2 receipt names one
    agent, one action, and one target. Trust, nonce uniqueness, revocation-store
    state, and atomic budget consumption remain external obligations.
    """
    if not isinstance(data, dict):
        return [Issue("$", "expected object")]

    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    reject_unknown(data, "$", V2_ROOT_FIELDS, issues)
    require_const(
        data, "authorization_version", AUTHORIZATION_V2_VERSION, issues
    )
    require_const(data, "kind", AUTHORIZATION_V2_RECEIPT_KIND, issues)
    require_text(data, "receipt_id", issues)
    require_text(data, "agent_id", issues)
    require_text(data, "action", issues)
    require_text(data, "target", issues)
    _validate_v2_nonce(data.get("nonce"), issues)
    _validate_v2_timestamp(data, "issued_at", issues)
    _validate_v2_timestamp(data, "expires_at", issues)
    _validate_v2_timestamp_ordering(data, issues)
    _validate_v2_max_actions(data.get("max_actions"), issues)
    _validate_revoked(data, issues)
    if "policy_ref" in data:
        _validate_optional_text(data["policy_ref"], "$.policy_ref", issues)
    if "notes" in data:
        _validate_optional_text(data["notes"], "$.notes", issues)
    return issues


def validate_authorization_receipt_v2_file(path: Path) -> list[Issue]:
    try:
        return validate_authorization_receipt_v2(load_receipt(path))
    except (FileNotFoundError, OSError, UnicodeError, ValueError) as exc:
        return [Issue("$", str(exc))]


def check_action_v2(
    receipt: dict[str, Any],
    action_kind: str,
    target: str,
    *,
    agent_id: str,
    actions_used: int,
    now: datetime | None = None,
) -> Issue | None:
    """Check one exact action against a v0.2 inner receipt.

    ``actions_used`` is an observation supplied by the caller. This function
    does not consume a budget or establish trust. The consuming system must
    verify an external signature and increment a durable usage ledger before
    product code runs.
    """
    issues = validate_authorization_receipt_v2(receipt)
    if issues:
        return Issue("$", f"receipt invalid: {issues[0].path} -- {issues[0].message}")

    if receipt["revoked"] is True:
        return Issue("$.revoked", "action denied: revoked")

    _now = now if now is not None else datetime.now(tz=timezone.utc)
    if not isinstance(_now, datetime) or _now.utcoffset() is None:
        return Issue("$.issued_at", "action denied: invalid_now")

    issued_at = _parse_rfc3339_timezone(receipt["issued_at"])
    expires_at = _parse_rfc3339_timezone(receipt["expires_at"])
    if issued_at is None or _now < issued_at:
        return Issue("$.issued_at", "action denied: grant_not_active")
    if expires_at is None or _now >= expires_at:
        return Issue("$.expires_at", "action denied: expired")

    if receipt["agent_id"] != agent_id:
        return Issue("$.agent_id", "action denied: agent_mismatch")
    if receipt["action"] != action_kind:
        return Issue("$.action", "action denied: action_mismatch")
    if receipt["target"] != target:
        return Issue("$.target", "action denied: target_mismatch")

    if (
        isinstance(actions_used, bool)
        or not isinstance(actions_used, int)
        or actions_used < 0
    ):
        return Issue("$.max_actions", "action denied: invalid_actions_used")
    if actions_used >= receipt["max_actions"]:
        return Issue("$.max_actions", "action denied: action_budget_exhausted")

    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _reject_forbidden(node: Any, path: str, issues: list[Issue]) -> None:
    """Recursively reject any key whose name appears in FORBIDDEN_FIELDS."""
    if isinstance(node, dict):
        for key in sorted(node):
            child = f"{path}.{key}"
            if key in FORBIDDEN_FIELDS:
                issues.append(Issue(child, "forbidden authorization-suppression field"))
            _reject_forbidden(node[key], child, issues)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _reject_forbidden(item, f"{path}[{index}]", issues)


def _validate_principal(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.principal", "expected object"))
        return
    reject_unknown(value, "$.principal", PRINCIPAL_FIELDS, issues)
    pid = value.get("id")
    if not isinstance(pid, str) or not pid.strip():
        issues.append(
            Issue(
                "$.principal.id",
                "expected non-empty string (a real human/account identifier)",
            )
        )
    role = value.get("role")
    if role is not None and (not isinstance(role, str) or not role.strip()):
        issues.append(
            Issue("$.principal.role", "expected non-empty string when present")
        )


def _validate_agent(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.agent", "expected object"))
        return
    reject_unknown(value, "$.agent", AGENT_FIELDS, issues)
    aid = value.get("id")
    if not isinstance(aid, str) or not aid.strip():
        issues.append(Issue("$.agent.id", "expected non-empty string"))


def _validate_scope(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.scope", "expected object"))
        return
    reject_unknown(value, "$.scope", SCOPE_FIELDS, issues)
    # allowed_actions: required array of strings (may be empty = nothing allowed).
    actions = value.get("allowed_actions")
    if not isinstance(actions, list):
        issues.append(
            Issue(
                "$.scope.allowed_actions",
                "expected array (may be empty -- empty means nothing allowed)",
            )
        )
    else:
        for i, item in enumerate(actions):
            if not isinstance(item, str) or not item.strip():
                issues.append(
                    Issue(f"$.scope.allowed_actions[{i}]", "expected non-empty string")
                )
    # allowed_targets: required array of strings (may be empty = any target).
    targets = value.get("allowed_targets")
    if not isinstance(targets, list):
        issues.append(Issue("$.scope.allowed_targets", "expected array"))
    else:
        for i, item in enumerate(targets):
            if not isinstance(item, str) or not item.strip():
                issues.append(
                    Issue(f"$.scope.allowed_targets[{i}]", "expected non-empty string")
                )
    # max_actions: optional non-negative integer.
    max_actions = value.get("max_actions")
    if max_actions is not None:
        if (
            isinstance(max_actions, bool)
            or not isinstance(max_actions, int)
            or max_actions < 0
        ):
            issues.append(Issue("$.scope.max_actions", "expected non-negative integer"))


def _validate_timestamp(data: dict[str, Any], field: str, issues: list[Issue]) -> None:
    value = data.get(field)
    if not isinstance(value, str) or not _ISO8601_RE.match(value):
        issues.append(
            Issue(
                f"$.{field}",
                "expected ISO-8601 datetime string with timezone (authority must expire)",
            )
        )


def _validate_timestamp_ordering(data: dict[str, Any], issues: list[Issue]) -> None:
    granted = _parse_iso8601(data.get("granted_at", ""))
    expires = _parse_iso8601(data.get("expires_at", ""))
    if granted is not None and expires is not None and expires <= granted:
        issues.append(Issue("$.expires_at", "expires_at must be after granted_at"))


def _validate_revoked(data: dict[str, Any], issues: list[Issue]) -> None:
    value = data.get("revoked")
    if not isinstance(value, bool):
        issues.append(Issue("$.revoked", "expected boolean"))


def _validate_notes(value: Any, issues: list[Issue]) -> None:
    if value is not None and not isinstance(value, str):
        issues.append(Issue("$.notes", "expected string"))


def _validate_v2_nonce(value: Any, issues: list[Issue]) -> None:
    if (
        not isinstance(value, str)
        or not _NONCE_RE.fullmatch(value)
        or set(value) == {"0"}
    ):
        issues.append(
            Issue(
                "$.nonce",
                "expected nonzero lowercase hex nonce of at least 128-bit length",
            )
        )


def _validate_v2_max_actions(value: Any, issues: list[Issue]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        issues.append(Issue("$.max_actions", "expected positive integer"))


def _validate_v2_timestamp_ordering(
    data: dict[str, Any], issues: list[Issue]
) -> None:
    issued = _parse_rfc3339_timezone(data.get("issued_at", ""))
    expires = _parse_rfc3339_timezone(data.get("expires_at", ""))
    if issued is not None and expires is not None and expires <= issued:
        issues.append(Issue("$.expires_at", "expires_at must be after issued_at"))


def _validate_optional_text(value: Any, path: str, issues: list[Issue]) -> None:
    if not isinstance(value, str) or not value.strip():
        issues.append(Issue(path, "expected non-empty string when present"))


def _validate_v2_timestamp(
    data: dict[str, Any], field: str, issues: list[Issue]
) -> None:
    if _parse_rfc3339_timezone(data.get(field)) is None:
        issues.append(
            Issue(
                f"$.{field}",
                "expected RFC3339 datetime string with explicit timezone",
            )
        )


def _parse_rfc3339_timezone(value: Any) -> datetime | None:
    if not isinstance(value, str) or not _RFC3339_TIMEZONE_RE.fullmatch(value):
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _parse_iso8601(value: str) -> datetime | None:
    """Parse an ISO-8601 string to an aware datetime, or return None."""
    if not isinstance(value, str) or not _ISO8601_RE.match(value):
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None
