"""Red-team outside-review attacks (part 1 of 2: seat rules, log forks, renewals, clock skew, location).

Every attack runs against the in-process simulation and must be defeated fail-closed.
"""

from __future__ import annotations

import inspect

from harness.fsp import flows
from harness.fsp.canon import fingerprint
from harness.fsp.crypto import ED25519, Ed25519Signer, envelope, sign_record
from harness.fsp.location import MEDIUM, Landmark, Responder, distance_m, region_check
from harness.fsp.proofs import make_bundle, verify_bundle
from harness.fsp.renewal import leaf_package
from harness.fsp.seats import Roster, default_seats, make_roster
from harness.fsp.shim import receive_order, tick
from harness.fsp.witness import cosig_message, is_split_view_proof

DAY = 86_400
HOUR_MS = 3_600_000
SITE = (47.60, -122.33)
FAR = (35.68, 139.69)


def _region():
    return [Landmark("lm-1", "party-1", (47.61, -122.20), 200_000),
            Landmark("lm-2", "party-2", (47.25, -122.44), 200_000),
            Landmark("lm-3", "party-1", (48.00, -122.00), 200_000)]


# 1. Seat sets: 4 of 7 that break the non-frontier rule or the removal rule


def test_holds_vote_signature_of_the_non_frontier_seat_does_not_satisfy_check_3(sim):
    """Four frontier-side seats sign; non-frontier vote-tagged sig must still fail check 3."""
    order, notice = sim.halt(signers=flows.NO_NONFRONTIER)
    order["sigs"].append(sign_record(sim.world.seats[2].signer, "vote", order["body"]))
    sim.world.publish(order)
    sim.world.cosign()
    assert receive_order(sim.dev, sim.pkg(order, notice))["check"] == 3


def test_fails_roster_accepts_a_frontier_host_seat_that_also_claims_non_frontier(sim):
    """Reject a roster with a seat flagged both frontier-host and non-frontier."""
    w = sim.world
    w.seats[0].non_frontier_state = True
    new = make_roster(w.seats, 2, w.seats[:4])
    ok, _why = Roster(w.roster_msg).accepts_successor(new, 4, 7)
    sim.dev.trust.roster = Roster(new)
    order, notice = sim.halt(signers=flows.NO_NONFRONTIER)
    res = receive_order(sim.dev, sim.pkg(order, notice))
    assert not ok, "a roster with a seat flagged both frontier-host and non-frontier was accepted"
    assert res["status"] == "refused" and res["check"] == 3


def test_fails_four_seats_can_remove_the_other_three_without_k_remove(sim):
    """A 4-seat coalition cannot drop 3 other seat keys without K_REMOVE and cause."""
    w = sim.world
    fresh = default_seats()
    successor_seats = w.seats[:4] + fresh[4:]
    new = make_roster(successor_seats, 2, w.seats[:4])
    ok, why = Roster(w.roster_msg).accepts_successor(new, 4, 7)
    assert not ok, f"4 seats removed 3 others with no K_REMOVE check ({why})"


# 2. A log fork shown to two devices


def _colluding_cosigs(world, cp, n=3):
    t = world.now_ms()
    return [{"alg": ED25519, "witness": wit.key, "timestamp_ms": t,
             "sig": wit.signer.sign(cosig_message(cp["body"], t)).hex()}
            for wit in world.witnesses[:n]]


def _show(dev, log, msg, world):
    idx = log.find(fingerprint("entry", msg))
    cp = log.checkpoint()
    from_size = dev.view.get(log.log_id, {}).get("size", 0)
    bundle = make_bundle(log, idx, cp, _colluding_cosigs(world, cp), from_size)
    res = verify_bundle(msg, bundle, world.policy, dev.view)
    assert res.ok, res.reason
    dev.view[log.log_id] = {**cp["body"], "cp": cp}


def _fork_views(sim, extra_on_twin: int):
    w = sim.world
    log = w.logs[0]
    twin = log.fork()
    a = envelope("note", {"branch": "public", "n": 0})
    log.submit(a)
    twin_msgs = [envelope("note", {"branch": "private", "n": i}) for i in range(1 + extra_on_twin)]
    for m in twin_msgs:
        twin.submit(m)
    _show(sim.devs[0], log, a, w)
    _show(sim.devs[1], twin, twin_msgs[-1], w)
    events = []
    for dev in sim.devs:
        events += w.desk.receive(dev.heartbeat(), w.now_ms())
    return log, events


def test_holds_same_size_fork_across_two_devices_is_flagged_by_gossip(sim):
    """Equal-size branches gossiped by two devices raise a split-view event."""
    _, events = _fork_views(sim, extra_on_twin=0)
    assert any(e["kind"].startswith("split_view") for e in events)


def test_fails_gossip_suspicion_is_not_a_self_contained_proof(sim):
    """Gossip emits a self-contained split-view proof verifiable by any third party."""
    log, events = _fork_views(sim, extra_on_twin=0)
    ev = next(e for e in events if e["kind"].startswith("split_view"))
    a, b = ev["evidence"].get("a"), ev["evidence"].get("b")
    assert a is not None and b is not None and is_split_view_proof(a, b, log.key)


def test_fails_fork_at_different_sizes_is_never_seen_by_gossip(sim):
    """Branches of sizes n+1 and n+2 with no consistency proof are caught as split views."""
    _, events = _fork_views(sim, extra_on_twin=1)
    assert any(e["kind"].startswith("split_view") for e in events)


# 3. Renewals replayed across devices, and renewal bounds


def test_holds_renewal_leaf_of_one_device_cannot_renew_another(sim):
    """Device B refuses device A's leaf package and mixed packages; replay to A fails."""
    w = sim.world
    a, b = sim.devs
    for d in sim.devs:
        d.outbox.append(d.heartbeat())
        w.deliver(d)
    ren = flows.issue_renewal(w, 2)
    pkg_a = leaf_package(ren["tree"], ren["order"], ren["members"], a.key)
    pkg_b = leaf_package(ren["tree"], ren["order"], ren["members"], b.key)
    mixed = {**pkg_a, "hb_fp": pkg_b["hb_fp"]}
    assert b.accept_renewal(ren["msg"], w.bundles(ren["msg"], b), pkg_a)[0] is False
    assert b.accept_renewal(ren["msg"], w.bundles(ren["msg"], b), mixed)[0] is False
    assert a.accept_renewal(ren["msg"], w.bundles(ren["msg"], a), pkg_a) == (True, "ok")
    again = a.accept_renewal(ren["msg"], w.bundles(ren["msg"], a), pkg_a)
    assert again == (False, "not a newer epoch")


def test_fails_device_accepts_a_renewal_valid_for_ten_years(sim):
    """Refuse a renewal whose validity span exceeds RENEWAL_VALIDITY."""
    w = sim.world
    for d in sim.devs:
        d.outbox.append(d.heartbeat())
        w.deliver(d)
    ren = flows.issue_renewal(w, 2, validity_s=3650 * DAY)
    ok, _ = flows.deliver_renewal(w, sim.dev, ren)
    assert not ok, "a renewal ten years long was accepted"


# 4. Clock skew beyond tolerance, replayed time and forward jumps


def test_holds_one_server_skewed_beyond_time_tol_is_outvoted_and_proven(sim):
    """One server skewed beyond TIME_TOL is outvoted and logged as time-malfeasance."""
    w = sim.world
    w.time_servers[0].offset_ms = 11_000
    ok, _ = sim.dev.accept_time(w.time_chain(sim.dev))
    assert ok
    assert abs(sim.dev.t_work() - w.now_ms()) <= w.params.time_tol * 1000
    assert "time-malfeasance" in [m["type"] for m in sim.dev.outbox]


def test_fails_replayed_time_chain_after_power_cycle_keeps_a_silent_device_running(sim):
    """Replaying a day-0 time chain after power cycles fails closed via device nonce and time floor."""
    w = sim.world
    recorded = w.time_chain()
    for _ in range(6):  # 6 x 60 h = 15 days
        sim.advance(60 * 3600)
        sim.backends[0].power_cycle()
        sim.dev.accept_time(recorded)
        tick(sim.dev)
    assert w.now_ms() - recorded[0]["reply"]["body"]["midpoint_ms"] > 10 * DAY * 1000
    assert sim.dev.failed is not None, "device still runs 15 days on a replayed day-0 chain"


def test_fails_colluding_quorum_jumps_eight_days_ahead_of_a_running_timer(sim):
    """A running monotonic timer refuses an 8-day forward jump from a colluding quorum."""
    w = sim.world
    sim.advance(60)
    for s in w.time_servers[:2]:
        s.offset_ms = 8 * 24 * HOUR_MS
    ok, _ = sim.dev.accept_time(w.time_chain(sim.dev))
    assert not ok and sim.dev.failed is None


# 5. Location: negative added delay and measurement binding


def test_fails_simulator_accepts_negative_added_delay_and_moves_a_far_device_near():
    """Negative added delay must raise ValueError and fail the region check."""
    dev = Ed25519Signer()
    region = _region()
    recs = []
    for lm in region:
        fibre = 2 * distance_m(lm.position, FAR) / MEDIUM
        try:
            recs.append(lm.measure(dev.public_hex(), Responder(dev, FAR), 1,
                                   added_delay_s=-(fibre + 0.0002) + 0.0005))
        except ValueError:
            recs.append(None)
    assert region_check(region, recs, 3)["pass"] is False


def test_fails_measurement_record_is_not_bound_to_the_device_checked_or_to_a_time():
    """Location measurement records carry measured_ms and region_check accepts device_key."""
    dev = Ed25519Signer()
    rec = _region()[0].measure(dev.public_hex(), Responder(dev, SITE), 1)
    params = inspect.signature(region_check).parameters
    assert "measured_ms" in rec["body"], "measurement record has no time"
    assert "device_key" in params, "region_check cannot say which device it checks"
