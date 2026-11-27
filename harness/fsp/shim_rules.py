"""Order rules added after the outside review of 25 September 2026.

The shim (shim.py) calls these inside its eleven checks:

- ``check_shape`` extends check 1. Every field has the right type and range
  before the order is stored anywhere, a throttle level is an integer from
  THROTTLE_MIN to 99, and only a throttle carries a level. A stop of all
  work therefore has to go through the halt rules (SPEC.md 8.1 and 8.4).
- ``renewal_refusal`` extends check 9. A renewal names an order in force on
  this device with the same action and scope, and cites a governance
  decision with written reasons that the device proves in LOGS_MIN logs
  (SPEC.md 8.3). Before, any value in ``renews`` skipped RATE_HALT and could
  end a halt on other tags.
- ``notice_refusal`` extends check 10. The cited entry is a dependent notice
  signed by a roster seat, for the same cluster, naming every tag the halt
  names, and expiring no earlier than the halt.
"""

from __future__ import annotations

from .crypto import valid_signers
from .proofs import verify_in_logs

HEX = frozenset("0123456789abcdef")


class Refusal(Exception):
    def __init__(self, check: int | str, reason: str) -> None:
        super().__init__(reason)
        self.check, self.reason = check, reason


def is_fp(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_fields(body: dict) -> None:
    scope = body["scope"]
    if (not isinstance(scope, dict) or not isinstance(scope.get("cluster_id"), str)
            or not is_fp(scope.get("device_set_root"))):
        raise Refusal(1, "scope is malformed")
    tags = scope.get("workload_tags")
    if not isinstance(tags, list) or not all(is_fp(t) for t in tags):
        raise Refusal(1, "workload tags are malformed")
    for name in ("issued_ms", "effective_ms", "expires_ms"):
        if not _is_int(body[name]):
            raise Refusal(1, f"{name} is not an integer")
    if body["expires_ms"] < body["effective_ms"]:
        raise Refusal(1, "the order expires before it takes effect")
    for name in ("renews", "lifts"):
        if body[name] is not None and not is_fp(body[name]):
            raise Refusal(1, f"{name} is not an order id")
    notice = body["dependent_notice"]
    if notice is not None and not (isinstance(notice, dict) and is_fp(notice.get("entry_fp"))):
        raise Refusal(1, "dependent_notice is malformed")
    if not isinstance(body["criterion"], dict) or not isinstance(body["evidence"], list):
        raise Refusal(1, "criterion or evidence is malformed")


def check_shape(body: dict, params) -> None:
    """Check 1, after parsing: types and ranges, before anything is stored."""
    _check_fields(body)
    action, level, tags = body["action"], body["level"], body["scope"]["workload_tags"]
    if action == "throttle":
        if not _is_int(level) or not params.throttle_min <= level < 100:
            raise Refusal(1, f"a throttle level is an integer from THROTTLE_MIN "
                             f"({params.throttle_min}) to 99")
        if tags:
            raise Refusal(1, "a throttle acts on a whole cluster and names no tags")
    elif level is not None:
        raise Refusal(1, "only a throttle carries a level")
    if action == "halt" and not tags:
        raise Refusal(1, "a halt names at least one workload tag")
    if action == "lift" and (body["lifts"] is None or body["renews"] is not None):
        raise Refusal(1, "a lift names the order it ends and renews nothing")
    if action != "lift" and body["lifts"] is not None:
        raise Refusal(1, "only a lift names an order to end")


def renewal_refusal(dev, body: dict, pkg: dict) -> str | None:
    """Why a renewal (``renews`` set) may not act, or None."""
    named = dev.orders.get(body["renews"])
    if named is None:
        return "renews names no order in force on this device"
    if named["action"] != body["action"] or named["scope"] != body["scope"]:
        return "a renewal must keep the action and scope of the order it renews"
    decision = pkg.get("governance")
    if not isinstance(decision, dict) or decision.get("type") != "governance-decision":
        return "a renewal cites no governance decision"
    keys = dev.trust.governance_keys
    signed = set(valid_signers(decision)) & keys
    if not keys or len(signed) * 2 <= len(keys):
        return "the decision lacks a majority of governance keys"
    dbody = decision.get("body", {})
    if dbody.get("renews") != body["renews"] or not is_fp(dbody.get("reasons_fp")):
        return "the decision does not name this order with written reasons"
    res = verify_in_logs(decision, pkg.get("governance_bundles", []), dev.trust.policy, dev.view)
    if not res.ok:
        return f"governance decision not proven in the logs: {res.reason}"
    return None


def notice_refusal(dev, notice: dict, body: dict) -> str | None:
    """Why the cited entry does not bind the halt, or None."""
    if not isinstance(notice, dict) or notice.get("type") != "dependent-notice":
        return "the cited entry is not a dependent notice"
    if not dev.trust.roster.signers(notice):
        return "the dependent notice is not signed by a roster seat"
    nbody = notice.get("body", {})
    if nbody.get("cluster_id") != body["scope"]["cluster_id"]:
        return "the notice names another cluster"
    if not set(body["scope"]["workload_tags"]) <= set(nbody.get("workload_tags", [])):
        return "the notice does not name every tag the halt names"
    expires = nbody.get("expires_ms")
    if not _is_int(expires) or expires < body["expires_ms"]:
        return "the halt expires later than its notice said"
    return None
