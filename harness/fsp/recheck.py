"""The daily comparison of device actions with the log (SPEC.md section 13.4).

Anyone holding the logs can run this offline. Each row reads MATCH, DRIFT or
UNVERIFIABLE. An enforcement receipt with no prior logged, quorum-signed
order behind it in at least LOGS_MIN logs is DRIFT and a breach of
LOGGED_ORDERS. A fail-closed event logged later than T_FAILCLOSED_LOG after
it happened is DRIFT.
"""

from __future__ import annotations

from .alerts import clock_verdict
from .canon import fingerprint
from .crypto import msg_id
from .seats import Roster
from .signals import find_convergence
from .world import World


def _order_index(log, order_id: str) -> tuple[int, dict] | None:
    for i, leaf in enumerate(log.leaves):
        entry = leaf["entry"]
        if entry["type"] == "order" and msg_id(entry) == order_id:
            return i, entry
    return None


def _receipt_row(world: World, roster: Roster, i: int, body: dict) -> dict:
    p = world.params
    oid = body["order_id"]
    found = _order_index(world.logs[0], oid)
    row = {"subject": f"receipt {oid[:12]}", "field": "prior logged order"}
    if found is None or found[0] >= i:
        return {**row, "verdict": "DRIFT", "reason": "no order logged before the receipt"}
    order = found[1]
    logs_with = sum(1 for lg in world.logs if lg.find(fingerprint("entry", order)) is not None)
    if len(roster.signers(order)) < p.k_order:
        return {**row, "verdict": "DRIFT", "reason": "logged order lacks K_ORDER signatures"}
    if logs_with < p.logs_min:
        return {**row, "verdict": "DRIFT", "reason": f"order in {logs_with} logs"}
    return {**row, "verdict": "MATCH", "reason": f"order at index {found[0]}, in {logs_with} logs"}


def _failclosed_row(world: World, leaf: dict) -> dict:
    body = leaf["entry"]["body"]
    row = {"subject": f"fail-closed {body['device_key'][:12]} {body['reason']}",
           "field": "logged within T_FAILCLOSED_LOG"}
    if body["at_ms"] is None:
        return {**row, "verdict": "UNVERIFIABLE", "reason": "device had no working time"}
    verdict = clock_verdict(body["at_ms"], leaf["logged_ms"], world.params.t_failclosed_log,
                            world.params.time_tol)
    mapped = {"MET": "MATCH", "MISSED": "DRIFT"}.get(verdict, "UNVERIFIABLE")
    return {**row, "verdict": mapped, "reason": f"{leaf['logged_ms'] - body['at_ms']} ms"}


def daily_recheck(world: World) -> list[dict]:
    roster = Roster(world.roster_msg)
    rows = []
    for i, leaf in enumerate(world.logs[0].leaves):
        entry = leaf["entry"]
        if entry["type"] == "receipt" and entry["body"]["event"] == "applied":
            rows.append(_receipt_row(world, roster, i, entry["body"]))
        elif entry["type"] == "failclosed":
            rows.append(_failclosed_row(world, leaf))
    return rows


def recheck_convergence(world: World, recorded: dict | None, cluster_id: str,
                        admitted: list[dict]) -> dict:
    """Recompute a recorded convergence decision from logged signals."""
    again = find_convergence(admitted, cluster_id, world.params.t_converge)
    same = (again is None and recorded is None) or (
        again is not None and recorded is not None and again["evidence"] == recorded["evidence"])
    return {"subject": f"convergence {cluster_id}", "field": "convergence decision",
            "verdict": "MATCH" if same else "DRIFT",
            "reason": "recomputed from logged signals"}


def missing_receipts(world: World, order: dict, effective_ms: int, now_ms: int) -> list[str]:
    """Devices in scope with no applied receipt logged within T_EFFECT (a soft signal)."""
    if now_ms - effective_ms <= world.params.t_effect * 1000:
        return []
    oid = msg_id(order)
    keys = set(world.clusters[order["body"]["scope"]["cluster_id"]]["device_keys"])
    seen = {lf["entry"]["body"]["device_key"] for _i, lf in world.logs[0].entries_of("receipt")
            if lf["entry"]["body"]["order_id"] == oid
            and lf["logged_ms"] <= effective_ms + world.params.t_effect * 1000}
    return sorted(keys - seen)
