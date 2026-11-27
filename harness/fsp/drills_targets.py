"""Drills that measure the appendix targets in simulation.

Every number these drills produce is a property of the demo: simulated
devices, a simulated clock and cadences the drill sets. None is an estimate
for real hardware or fleets. The cadences are demo values and are reported.
"""

from __future__ import annotations

import heapq
import json
import random
import statistics
from pathlib import Path

from . import flows
from .backends.software import SoftwareSecureElement
from .recheck import daily_recheck, missing_receipts
from .shim import receive_order, tick
from .world import World

TICK_S, CARRY_S = 1, 10   # demo values: device self-check period, carrier forwarding period


def fleet(n: int, cluster: str = "c1", world: World | None = None):
    w = world or World()
    backends = [SoftwareSecureElement(w.fw, w.clock) for _ in range(n)]
    devs = [w.add_device(b, cluster) for b in backends]
    w.provision_cluster(cluster, devs)
    flows.bootstrap(w, devs)
    return w, backends, devs


def summary(values: list[float]) -> dict:
    vals = sorted(values)
    p95 = vals[min(len(vals) - 1, int(round(0.95 * (len(vals) - 1))))]
    return {"n": len(vals), "min": round(vals[0], 3), "median": round(statistics.median(vals), 3),
            "p95": round(p95, 3), "max": round(vals[-1], 3)}


def drill_tamper(n: int = 60, seed: int = 1) -> dict:
    rng = random.Random(seed)
    w, backends, devs = fleet(n)
    physical, device_side = [], []
    for backend, dev in zip(backends, devs):
        w.clock.advance(rng.uniform(0, CARRY_S))
        backend.trip_tamper()
        t_event = w.now_ms()
        w.clock.advance(rng.uniform(0, TICK_S))
        tick(dev)
        w.clock.advance(rng.uniform(0, CARRY_S))
        logged = w.deliver(dev)
        leaf = w.logs[0].leaves[logged[-1][1]["log-0"]]
        physical.append((leaf["logged_ms"] - t_event) / 1000)
        device_side.append((leaf["logged_ms"] - logged[-1][0]["body"]["at_ms"]) / 1000)
    rows = daily_recheck(w)
    others_ok = all(d.failed == "tamper" for d in devs)
    return {"drill": "time to detect tamper, online device",
            "event_to_log_s": summary(physical), "detection_to_log_s": summary(device_side),
            "within_1_min": sum(v <= 60 for v in physical), "of": n,
            "recheck": {v: sum(r["verdict"] == v for r in rows)
                        for v in ("MATCH", "DRIFT", "UNVERIFIABLE")},
            "each_device_failed_closed": others_ok,
            "cadences": {"device_self_check_s": TICK_S, "carrier_forward_s": CARRY_S}}


def _silent_trial(rng: random.Random, mode: str) -> dict:
    w, _b, devs = fleet(2)
    quiet, talker = devs
    w.clock.advance(rng.uniform(0, w.params.t_epoch))  # silence starts at a random phase
    talker.accept_time(w.time_chain(talker))
    quiet.accept_time(w.time_chain(quiet))
    quiet.outbox.append(quiet.heartbeat())
    w.deliver(quiet)
    start, epoch, missed_at = w.now_ms(), 2, None
    next_root = w.now_ms() + w.params.t_epoch * 1000
    while quiet.failed is None:
        w.clock.advance(600)
        talker.accept_time(w.time_chain(talker))
        if mode != "offline":
            quiet.accept_time(w.time_chain(quiet))
        for ev in w.desk.scan_missed(w.now_ms()):
            if ev["device_key"] == quiet.key and missed_at is None:
                missed_at = w.now_ms()
        if w.now_ms() >= next_root:
            talker.outbox.append(talker.heartbeat())
            w.deliver(talker)
            ren = flows.issue_renewal(w, epoch)
            epoch, next_root = epoch + 1, next_root + w.params.t_epoch * 1000
            flows.deliver_renewal(w, talker, ren)
            if mode == "inbound_open":
                flows.deliver_renewal(w, quiet, ren)
        tick(quiet)
    return {"hours_to_fail_closed": (w.now_ms() - start) / 3_600_000,
            "minutes_to_missed": None if missed_at is None else (missed_at - start) / 60_000,
            "reason": quiet.failed}


def drill_silent(trials: int = 6, seed: int = 2) -> dict:
    rng = random.Random(seed)
    out = {"drill": "longest a silent device keeps running", "step_s": 600, "modes": {}}
    for mode in ("offline", "time_only", "inbound_open"):
        runs = [_silent_trial(rng, mode) for _ in range(trials)]
        out["modes"][mode] = {
            "hours_to_fail_closed": summary([r["hours_to_fail_closed"] for r in runs]),
            "minutes_to_missed": summary([r["minutes_to_missed"] for r in runs]),
            "reasons": sorted({r["reason"] for r in runs})}
    return out


def drill_effect(n: int = 40, seed: int = 3) -> dict:
    rng = random.Random(seed)
    w, _b, devs = fleet(n)
    p = w.params
    offline = devs[-1]
    notice = flows.post_notice(w, "c1", ["ab" * 32], w.now_ms() + p.t_halt_notice * 1000,
                               w.now_ms() + 2 * 3_600_000)
    eff = notice[1] + p.t_halt_notice * 1000
    order = flows.build_order(w, "halt", "c1", tags=["ab" * 32], notice=notice,
                              effective_ms=eff, expires_ms=eff + 3_600_000)
    queue = [(w.now_ms() + int(rng.uniform(0, p.t_poll * 1000)), i) for i in range(n - 1)]
    heapq.heapify(queue)
    delays, fetched = [], set()
    while queue:
        t, i = heapq.heappop(queue)
        w.clock.advance(max(0, t - w.now_ms()) / 1000)
        dev, results = devs[i], []
        if i not in fetched:
            results.append(receive_order(dev, flows.package(w, order, dev, notice)))
            fetched.add(i)
        results += tick(dev)
        w.deliver(dev)
        if any(r["status"] == "applied" for r in results):
            delays.append((w.now_ms() - eff) / 60_000)
            continue
        heapq.heappush(queue, (t + p.t_poll * 1000, i))
    w.clock.advance(p.t_effect + 1)
    missing = missing_receipts(w, order, eff, w.now_ms())
    rows = daily_recheck(w)
    return {"drill": "time from a valid order to effect",
            "effective_to_receipt_min": summary(delays), "devices_in_scope": n,
            "offline_device_flagged_missing_receipt": missing == [offline.key],
            "receipts_backed_by_prior_logged_order": sum(r["verdict"] == "MATCH" for r in rows),
            "receipts": len(rows), "poll_period_s": p.t_poll,
            "notice_lead_s": p.t_halt_notice}


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=1), "utf-8")
