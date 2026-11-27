"""Conformance drills 2 and 5 to 11 of SPEC.md section 16.2, each with its pass condition."""

from __future__ import annotations

import random

from . import flows
from .backends.software import SoftwareSecureElement
from .canon import fingerprint
from .crypto import ED25519, Ed25519Signer
from .device import Device
from .drills_targets import fleet
from .location import Landmark, Responder, region_check
from .negative import weak_receive
from .recheck import daily_recheck
from .serving import ReportWatch, ServingStack
from .shim import receive_order, tick
from .signals import HUMAN, HW, PROG, TABLE, find_convergence, make_signal
from .timesrc import malfeasance
from .proofs import make_bundle
from .witness import Refused, cosig_message, is_split_view_proof


def negative_control() -> dict:
    w, _b, devs = fleet(1)
    order = flows.build_order(w, "throttle", "c1", level=50, publish=False)
    strong = receive_order(devs[0], flows.package(w, order, devs[0]))
    weak = weak_receive(devs[0], flows.package(w, order, devs[0]))
    w.deliver(devs[0])
    verdicts = [r["verdict"] for r in daily_recheck(w)]
    return {"drill": "2 negative control", "strong_shim": strong["status"],
            "weak_shim": weak["status"], "recheck": verdicts,
            "pass": strong["status"] == "refused" and "DRIFT" in verdicts}


def missed_report() -> dict:
    w, _b, _d = fleet(1)
    stack = ServingStack("stack-1", 3600)
    watch = ReportWatch(stack)
    watch.receive(stack.report(w.now_ms()), w.now_ms())
    w.clock.advance(3600)
    watch.receive(stack.report(w.now_ms()), w.now_ms())
    w.clock.advance(2 * 3600 + 1)  # the next scheduled report never comes
    event = watch.scan(w.now_ms())
    return {"drill": "5 missed serving-stack report", "signal": event and event["kind"],
            "pass": event is not None and event["kind"] == "missed_serving_report"}


def clone() -> dict:
    w, _b, _d = fleet(1)
    uds = b"\x09" * 32
    a = w.add_device(SoftwareSecureElement(w.fw, w.clock, uds=uds), "c1")
    b = Device(SoftwareSecureElement(w.fw, w.clock, uds=uds), w.params, w.trust(), "region-1")
    b.accept_time(w.time_chain(b))
    a.outbox.append(a.heartbeat())
    b.outbox.append(b.heartbeat(profile="telemetry"))
    w.deliver(a)
    w.deliver(b)
    proof = any(e["kind"] == "clone_proof" for e in w.events)
    ren = flows.issue_renewal(w, 2)
    return {"drill": "6 clone", "clone_proof": proof, "key_in_next_root": a.key in ren["members"],
            "pass": proof and a.key not in ren["members"]}


def _forced_cosigs(w, cp: dict, n: int) -> list[dict]:
    """Red-team: n compromised witnesses sign whatever they are shown."""
    now = w.now_ms()
    return [{"alg": ED25519, "witness": wit.key, "timestamp_ms": now,
             "sig": wit.signer.sign(cosig_message(cp["body"], now)).hex()}
            for wit in w.witnesses[:n]]


def split_view() -> dict:
    """One log equivocates. Honest witnesses refuse; with K_WITNESS compromised
    witnesses a device takes the private branch, the order still fails LOGS_MIN,
    and heartbeat gossip exposes the split with a self-contained proof."""
    w, _b, devs = fleet(2)
    log = w.logs[0]
    twin = log.fork()
    secret = flows.build_order(w, "throttle", "c1", level=10, publish=False)
    twin.submit(secret)
    public = flows.build_order(w, "throttle", "c1", level=90)  # all logs, cosigned
    cp_twin = twin.checkpoint()
    honest_refusals = 0
    for wit in w.witnesses:
        try:
            wit.cosign(cp_twin, log.key, [])
        except Refused:
            honest_refusals += 1
    receive_order(devs[0], flows.package(w, public, devs[0]))
    idx = twin.find(fingerprint("entry", secret))
    held = devs[1].view[log.log_id]["size"]
    bundle = make_bundle(twin, idx, cp_twin, _forced_cosigs(w, cp_twin, w.params.k_witness),
                         held)
    res = receive_order(devs[1], {**flows.package(w, secret, devs[1]), "bundles": [bundle]})
    for dev in devs:
        dev.outbox.append(dev.heartbeat())
        w.deliver(dev)
    flagged = [e for e in w.events if e["kind"] == "split_view_proof"]
    # The desk's own evidence: two checkpoints the log signed, taken from gossip.
    proof = any(is_split_view_proof(e["evidence"]["a"], e["evidence"]["b"], log.key)
                or e["evidence"]["consistency"] is not None for e in flagged)
    return {"drill": "7 split view", "honest_witness_refusals": honest_refusals,
            "device_acted_on_secret_order": res["status"] == "applied",
            "secret_order_refused_at_check": res.get("check"),
            "gossip_flagged": len(flagged), "desk_proof_from_signed_checkpoints": proof,
            "pass": honest_refusals == len(w.witnesses) and res["status"] == "refused"
            and bool(flagged) and proof}


def clock_skew() -> dict:
    w, _b, devs = fleet(1)
    w.time_servers[1].offset_ms = 3_600_000
    chain = w.time_chain(devs[0])
    proof = malfeasance(chain, devs[0].trust.time_keys) is not None
    before = devs[0].t_work()
    devs[0].accept_time(chain)
    after = devs[0].t_work()
    for server in w.time_servers:
        server.offset_ms = -3_600_000
    moved_back, _ = devs[0].accept_time(w.time_chain(devs[0]))
    return {"drill": "8 clock skew", "malfeasance_proof": proof,
            "time_moved_backward": moved_back, "pass": proof and not moved_back
            and after >= before}


def added_delay() -> dict:
    w, _b, devs = fleet(1)
    region = [Landmark("lm-1", "p1", (47.61, -122.20), 200_000),
              Landmark("lm-2", "p2", (47.25, -122.44), 200_000),
              Landmark("lm-3", "p1", (48.00, -122.00), 200_000)]
    dev = devs[0]
    recs = [lm.measure(dev.key, Responder(dev.signer, (47.6, -122.33)), 1, added_delay_s=0.02)
            for lm in region]
    check = region_check(region, recs, w.params.landmarks_min, device_key=dev.key)
    dev.note_location(recs)
    tick(dev)
    return {"drill": "9 added delay", "region_verdict": check["verdict"],
            "device_failed": dev.failed, "heartbeat_location_set": dev.location_fp != "none",
            "pass": check["verdict"] == "FAIL" and dev.failed is None
            and dev.location_fp != "none"}


def convergence(trials: int = 2000, seed: int = 5) -> dict:
    rng = random.Random(seed)
    src = Ed25519Signer()
    by_family = {f: [k for k, v in TABLE.items() if v[0] == "soft" and v[1] == f]
                 for f in (HW, PROG, HUMAN)}
    single, mixed = 0, 0
    for _ in range(trials):
        fam = rng.choice(list(by_family))
        entries = []
        for i in range(rng.randint(2, 6)):
            t = rng.randint(0, 48 * 3_600_000)
            sig = make_signal(src, rng.choice(by_family[fam]), "c1", t, {"i": i})
            entries.append({"logged_ms": t, "body": sig["body"], "counted": True, "ref": i})
        single += find_convergence(entries, "c1", 86400) is not None
        other = rng.choice([f for f in by_family if f != fam])
        t = entries[0]["logged_ms"] + rng.randint(0, 23 * 3_600_000)
        extra = make_signal(src, rng.choice(by_family[other]), "c1", t, {"x": 1})
        entries.append({"logged_ms": t, "body": extra["body"], "counted": True, "ref": "x"})
        mixed += find_convergence(entries, "c1", 86400) is not None
    return {"drill": "10 convergence", "single_family_sets": single, "two_family_sets": mixed,
            "trials": trials, "pass": single == 0 and mixed == trials}


def expiry() -> dict:
    w, _b, devs = fleet(1)
    dev = devs[0]
    tag = "cd" * 32
    notice = flows.post_notice(w, "c1", [tag], w.now_ms(), w.now_ms() + 7200_000)
    eff = notice[1] + w.params.t_halt_notice * 1000
    order = flows.build_order(w, "halt", "c1", tags=[tag], notice=notice, effective_ms=eff,
                              expires_ms=eff + 3_600_000)
    receive_order(dev, flows.package(w, order, dev, notice))
    w.clock.advance(w.params.t_halt_notice + 1)
    tick(dev)
    halted = dev.enforcement()["state"] == "halted"
    w.clock.advance(3601)
    tick(dev)
    events = [m["body"]["event"] for m in dev.outbox if m["type"] == "receipt"]
    return {"drill": "11 expiry", "halted_then": halted, "receipts": events,
            "pass": halted and events == ["applied", "expired"]
            and dev.enforcement()["state"] == "normal"}


ALL = [negative_control, missed_report, clone, split_view, clock_skew, added_delay,
       convergence, expiry]
