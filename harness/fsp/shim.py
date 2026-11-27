"""The enforcement shim: the eleven checks of SPEC.md section 8.4.

``receive_order`` runs the checks in order and acts only if every one
passes. Any failure yields a signed refusal naming the failed check, which
goes to the device's outbox for the seats to log. An order whose only
failing condition is that its effective time has not come stays pending
and is re-evaluated on ``tick``.
"""

from __future__ import annotations

from .canon import CanonError, canon, fingerprint, parse_canonical
from .crypto import msg_id, valid_signers
from .device import Device
from .merkle import leaf_hash, verify_inclusion
from .orders import ACTIONS
from .params import Params
from .proofs import verify_in_logs
from .shim_rules import Refusal, check_shape, notice_refusal, renewal_refusal

FIELDS = ("action", "scope", "level", "criterion", "evidence", "issued_ms", "effective_ms",
          "expires_ms", "renews", "lifts", "dependent_notice")
MALFORMED = (KeyError, TypeError, ValueError, AttributeError, IndexError)

__all__ = ["Refusal", "evaluate", "receive_order", "tick"]


def _check1(raw: bytes | dict, params: Params | None = None) -> dict:
    try:
        msg = parse_canonical(raw if isinstance(raw, bytes) else canon(raw))
    except CanonError as exc:
        raise Refusal(1, f"not canonical: {exc}") from exc
    body = msg.get("body", {}) if isinstance(msg, dict) else {}
    if msg.get("type") != "order" or body.get("action") not in ACTIONS:
        raise Refusal(1, "unknown message type or action")
    missing = [f for f in FIELDS if f not in body]
    if missing:
        raise Refusal(1, f"missing fields {missing}")
    check_shape(body, params or Params())
    return msg


def _check2_3(dev: Device, msg: dict) -> None:
    signers = dev.trust.roster.signers(msg)
    if len(signers) < dev.params.k_order:
        raise Refusal(2, f"{len(signers)} of {dev.params.k_order} required seat signatures")
    span = len(dev.trust.roster.signer_regions(msg))
    if span < dev.params.min_signer_regions:
        raise Refusal(2, f"signers span {span} of {dev.params.min_signer_regions} required regions")
    if msg["body"]["action"] == "halt" and not dev.trust.roster.non_frontier_signers(msg):
        raise Refusal(3, "no signer holds the non_frontier_state flag")


def _check7(dev: Device, body: dict) -> bool:
    """True when in force now; False when not yet effective. Raises when expired."""
    now = dev.t_work()
    if now is None:
        raise Refusal(7, "no trustworthy working time")
    span = body["expires_ms"] - body["effective_ms"]
    if body["action"] != "lift" and span > dev.params.t_halt_max * 1000:
        raise Refusal(7, "expiry is more than T_HALT_MAX after effective time")
    if now > body["expires_ms"]:
        raise Refusal(7, "order expired")
    return now >= body["effective_ms"]


def _check8(dev: Device, body: dict, proof: dict | None) -> None:
    cluster, scope = dev.trust.cluster, body["scope"]
    if scope["cluster_id"] != cluster["cluster_id"]:
        raise Refusal(8, "order names another cluster")
    if scope["device_set_root"] != cluster["device_set_root"]:
        raise Refusal(8, "device set root differs from the logged cluster record")
    if proof is None:
        raise Refusal(8, "no scope proof")
    path = [bytes.fromhex(h) for h in proof["path"]]
    lh = leaf_hash(dev.key.encode("ascii"))
    if not verify_inclusion(lh, proof["index"], proof["size"], path,
                            bytes.fromhex(scope["device_set_root"])):
        raise Refusal(8, "this device is not in the order's device set")


def _check9(dev: Device, body: dict, pkg: dict) -> None:
    now = dev.t_work()
    if body["renews"] is not None:
        why = renewal_refusal(dev, body, pkg)
        if why is not None:
            raise Refusal(9, why)
    if body["action"] == "throttle":
        key = "throttle:" + body["scope"]["cluster_id"]
        recent = [t for t in dev.rate.get(key, []) if now - t < dev.params.rate_throttle_window * 1000]
        if recent:
            raise Refusal(9, "throttle level changed within the rate window")
    if body["action"] == "halt" and body["renews"] is None:
        window = dev.params.rate_halt_window * 1000
        for tag in body["scope"]["workload_tags"]:
            recent = [t for t in dev.rate.get("halt:" + tag, []) if now - t < window]
            if len(recent) >= dev.params.rate_halt_max and not _appeal_allows(dev, pkg, tag):
                raise Refusal(9, "halt rate limit reached for a named tag")


def _appeal_allows(dev: Device, pkg: dict, tag: str) -> bool:
    appeal = pkg.get("appeal")
    if appeal is None or appeal.get("type") != "appeal-decision":
        return False
    panel = [k for k in valid_signers(appeal) if k in dev.trust.panel_keys]
    if len(panel) * 2 <= len(dev.trust.panel_keys):
        return False
    if tag not in appeal["body"].get("allows_extra_halt_for", []):
        return False
    return verify_in_logs(appeal, pkg.get("appeal_bundles", []), dev.trust.policy,
                          dev.view).ok


def _check10(dev: Device, msg: dict, pkg: dict, order_idx: dict) -> None:
    body = msg["body"]
    notice, ref = pkg.get("notice"), body["dependent_notice"]
    if notice is None or ref is None or fingerprint("entry", notice) != ref.get("entry_fp"):
        raise Refusal(10, "no dependent notice matching the order")
    res = verify_in_logs(notice, pkg.get("notice_bundles", []), dev.trust.policy, dev.view)
    if not res.ok:
        raise Refusal(10, f"dependent notice not proven in the logs: {res.reason}")
    for log_id, idx in order_idx.items():
        if log_id in res.indices and res.indices[log_id] >= idx:
            raise Refusal(10, f"notice is not before the order in {log_id}")
    lead = dev.params.t_halt_notice * 1000
    if body["effective_ms"] < max(res.logged_ms.values()) + lead:
        raise Refusal(10, "effective time is less than T_HALT_NOTICE after the notice")
    why = notice_refusal(dev, notice, body)
    if why is not None:
        raise Refusal(10, why)


def _checks(dev: Device, pkg: dict, at: list[int]) -> tuple[str, dict]:
    msg = _check1(pkg.get("order_bytes") or pkg.get("order"), dev.params)
    at[0] = 2
    _check2_3(dev, msg)
    at[0] = 4
    res = verify_in_logs(msg, pkg.get("bundles", []), dev.trust.policy, dev.view)
    if not res.ok:
        raise Refusal(res.check, res.reason)
    at[0] = 7
    in_force = _check7(dev, msg["body"])
    at[0] = 8
    _check8(dev, msg["body"], pkg.get("scope_proof"))
    at[0] = 9
    _check9(dev, msg["body"], pkg)
    at[0] = 10
    if msg["body"]["action"] == "halt":
        _check10(dev, msg, pkg, res.indices)
    at[0] = 11
    if msg_id(msg) in dev.applied:
        raise Refusal(11, "order already applied; replay refused")
    if msg_id(msg) in dev.lifted:
        raise Refusal(11, "a lift ended this order; it cannot act")
    return ("apply" if in_force else "pending"), msg


def evaluate(dev: Device, pkg: dict) -> tuple[str, dict]:
    """Run checks 1 to 11. Returns (status, msg); raises Refusal.

    Malformed input of any shape becomes a refusal at the check where it
    surfaced, so a carrier that strips a field still gets a signed refusal.
    """
    if dev.failed:
        raise Refusal("fc", f"device is failed closed ({dev.failed})")
    at = [1]
    try:
        if not isinstance(pkg, dict):
            raise TypeError("package is not an object")
        status, msg = _checks(dev, pkg, at)
        if dev.params.stage == "L" and msg["body"]["action"] in ("throttle", "halt"):
            raise Refusal(
                "stage_l",
                "Stage L active: logging/audit only; remote stop/throttle disabled until Stage F",
            )
        return status, msg
    except MALFORMED as exc:
        raise Refusal(at[0], f"malformed input at check {at[0]}: {type(exc).__name__}") from exc


def _subject(pkg: dict) -> str:
    raw = (pkg.get("order_bytes") or pkg.get("order")) if isinstance(pkg, dict) else pkg
    try:
        msg = parse_canonical(raw if isinstance(raw, bytes) else canon(raw))
        return msg_id(msg)
    except (CanonError, KeyError, TypeError, AttributeError):
        data = raw if isinstance(raw, bytes) else repr(raw).encode()
        return fingerprint("raw", data.hex())


def _refuse(dev: Device, pkg: dict, err: Refusal) -> dict:
    body = {"subject_fp": _subject(pkg), "check": err.check, "reason": err.reason,
            "device_key": dev.key, "counter": dev.backend.counter_read(), "at_ms": dev.t_work()}
    dev.outbox.append(dev.sign("refusal", body))
    return {"status": "refused", "check": err.check, "reason": err.reason,
            "order_id": body["subject_fp"]}


def _apply(dev: Device, msg: dict) -> dict:
    body, oid, now = msg["body"], msg_id(msg), dev.t_work()
    if body["action"] == "lift":
        # A lift ends the named order whether it is in force or still pending
        # in its notice lead, and the device refuses that order afterwards.
        dev.orders.pop(body["lifts"], None)
        dev.pending.pop(body["lifts"], None)
        dev.lifted.add(body["lifts"])
    else:
        dev.orders[oid] = body
        if body["renews"]:
            dev.orders.pop(body["renews"], None)
    dev.applied.add(oid)
    dev.pending.pop(oid, None)
    if body["action"] == "throttle":
        dev.rate.setdefault("throttle:" + body["scope"]["cluster_id"], []).append(now)
    if body["action"] == "halt" and body["renews"] is None:
        for tag in body["scope"]["workload_tags"]:
            dev.rate.setdefault("halt:" + tag, []).append(now)
    still = dev._enforce()
    dev.outbox.append(dev.sign("receipt", {
        "order_id": oid, "device_key": dev.key, "counter": dev.backend.counter_read(),
        "applied_ms": now, "effective_ms": body["effective_ms"], "event": "applied",
        "enforcement_state": dev.enforcement(), "tags_still_running": sorted(still)}))
    return {"status": "applied", "order_id": oid, "tags_still_running": still}


def receive_order(dev: Device, pkg: dict) -> dict:
    try:
        status, msg = evaluate(dev, pkg)
    except Refusal as err:
        return _refuse(dev, pkg, err)
    if status == "pending":
        dev.pending[msg_id(msg)] = {"pkg": pkg, "msg": msg}
        return {"status": "pending", "order_id": msg_id(msg)}
    return _apply(dev, msg)


def _expire(dev: Device, now: int) -> None:
    for oid, body in list(dev.orders.items()):
        if now > body["expires_ms"]:
            del dev.orders[oid]
            dev._enforce()
            dev.outbox.append(dev.sign("receipt", {
                "order_id": oid, "device_key": dev.key, "counter": dev.backend.counter_read(),
                "applied_ms": now, "effective_ms": body["effective_ms"], "event": "expired",
                "enforcement_state": dev.enforcement(), "tags_still_running": []}))


def tick(dev: Device) -> list[dict]:
    """Self-checks, expiries, then pending orders whose time has come."""
    dev.self_check()
    results: list[dict] = []
    if dev.failed:
        return results
    _expire(dev, dev.t_work())
    for oid, item in list(dev.pending.items()):
        try:
            if not _check7(dev, item["msg"]["body"]):
                continue
            _check9(dev, item["msg"]["body"], item["pkg"])
            if oid in dev.applied or oid in dev.lifted:
                raise Refusal(11, "order already applied or lifted")
        except MALFORMED as exc:
            err = Refusal(9, f"malformed pending order: {type(exc).__name__}")
            dev.pending.pop(oid, None)
            results.append(_refuse(dev, item["pkg"], err))
            continue
        except Refusal as err:
            dev.pending.pop(oid, None)
            results.append(_refuse(dev, item["pkg"], err))
            continue
        results.append(_apply(dev, item["msg"]))
    return results
