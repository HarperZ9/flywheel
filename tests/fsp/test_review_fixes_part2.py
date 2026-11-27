"""Positive paths and false-alarm controls for red-team fixes (part 2 of 2: gossip, renewals, location, maintenance)."""

from __future__ import annotations

import copy

from harness.fsp import flows, maintenance
from harness.fsp.backends.software import SoftwareSecureElement
from harness.fsp.crypto import add_signature, envelope
from harness.fsp.location import Landmark, Responder, region_check
from harness.fsp.shim import receive_order, tick

HOUR_MS = 3_600_000
SITE = (47.60, -122.33)
CAUSE = "ab" * 32


def test_honest_log_growth_seen_at_two_sizes_raises_nothing(sim):
    w = sim.world
    a, b = sim.devs
    w.deliver(a)
    for level in (40, 60):
        order = flows.build_order(w, "throttle", "c1", level=level)
        receive_order(b, sim.pkg(order, dev=b))
        sim.advance(3601)
    events = []
    for dev in (a, b):
        events += w.desk.receive(dev.heartbeat(), w.now_ms())
    assert a.view["log-0"]["size"] != b.view["log-0"]["size"]
    assert not [e for e in events if e["kind"].startswith(("split_view", "gossip"))]


def test_forged_checkpoint_signature_in_gossip_is_unverifiable_not_proof(sim):
    hb_dev = sim.dev
    hb_dev.view["log-0"] = copy.deepcopy(hb_dev.view["log-0"])
    hb_dev.view["log-0"]["cp"]["sigs"][0]["sig"] = "00" * 64
    events = sim.world.desk.receive(hb_dev.heartbeat(), sim.world.now_ms())
    assert [e["kind"] for e in events] == ["gossip_unverifiable"]


def test_renewal_that_starts_in_the_future_is_refused(sim):
    w = sim.world
    for d in sim.devs:
        d.outbox.append(d.heartbeat())
        w.deliver(d)
    ren = flows.issue_renewal(w, 2)
    ren["msg"]["body"]["valid_from_ms"] += 3600_000
    ren["msg"]["body"]["valid_until_ms"] += 3600_000
    ok, _why = sim.dev.accept_renewal(ren["msg"], w.bundles(ren["msg"], sim.dev), None)
    assert not ok


def test_two_logs_of_one_operator_do_not_meet_logs_min(sim):
    w = sim.world
    for entry in sim.dev.trust.policy["logs"]:
        entry["operator"] = "one-operator"
    order = flows.build_order(w, "throttle", "c1", level=50)
    res = receive_order(sim.dev, sim.pkg(order))
    assert res["check"] == 4 and "operators" in res["reason"]


def _region(clock=None):
    return [Landmark("lm-1", "party-1", (47.61, -122.20), 200_000, clock),
            Landmark("lm-2", "party-2", (47.25, -122.44), 200_000, clock),
            Landmark("lm-3", "party-1", (48.00, -122.00), 200_000, clock)]


def test_record_of_one_device_does_not_pass_another_or_a_stale_check(sim):
    region = _region(sim.world.clock)
    a, b = sim.devs
    recs = [lm.measure(a.key, Responder(a.signer, SITE), 1) for lm in region]
    assert region_check(region, recs, 3, device_key=a.key)["verdict"] == "PASS"
    assert region_check(region, recs, 3, device_key=b.key)["verdict"] == "FAIL"
    sim.advance(7 * 3600)
    late = region_check(region, recs, 3, device_key=a.key, now_ms=sim.world.now_ms())
    assert late["verdict"] == "FAIL"
    assert a.note_location(recs) != "none" and a.heartbeat()["body"]["location"] != "none"


def test_region_below_landmarks_min_reads_unverifiable(sim):
    region = _region()[:2]
    recs = [lm.measure(sim.dev.key, Responder(sim.dev.signer, SITE), 1) for lm in region]
    assert region_check(region, recs, 3, device_key=sim.dev.key)["verdict"] == "UNVERIFIABLE"


def _window(sim, hours=2):
    w = sim.world
    msg = maintenance.window_msg(w.operator, "operator-1", [sim.dev.key], CAUSE, CAUSE,
                                 w.now_ms(), w.now_ms() + hours * HOUR_MS)
    w.publish(msg)
    w.cosign()
    return msg


def test_tamper_inside_a_logged_window_restores_with_inspection_and_no_vote(sim):
    w = sim.world
    msg = _window(sim)
    assert sim.dev.accept_maintenance(msg, w.bundles(msg, sim.dev)) == (True, "ok")
    sim.backends[0].trip_tamper()
    tick(sim.dev)
    assert sim.dev.failed == "maintenance_tamper"
    inspection = envelope("inspection", {"device_key": sim.dev.key, "result": "ok"},
                          [w.inspector])
    assert sim.dev.restore_after_maintenance(inspection)[1] == "tamper sensor still reads fired"
    sim.backends[0].clear_tamper_after_inspection()
    assert sim.dev.restore_after_maintenance(inspection) == (True, "ok")
    tick(sim.dev)
    assert sim.dev.failed is None


def test_tamper_outside_any_window_stays_a_hard_signal(sim):
    w = sim.world
    msg = _window(sim, hours=1)
    sim.dev.accept_maintenance(msg, w.bundles(msg, sim.dev))
    sim.advance(2 * 3600)
    sim.dev.accept_time(w.time_chain(sim.dev))
    sim.backends[0].trip_tamper()
    tick(sim.dev)
    assert sim.dev.failed == "tamper"


def test_window_longer_than_maint_window_or_past_maint_rate_is_refused(sim):
    w = sim.world
    long_win = _window(sim, hours=9)
    assert "MAINT_WINDOW" in sim.dev.accept_maintenance(long_win, w.bundles(long_win, sim.dev))[1]
    for _ in range(w.params.maint_rate):
        msg = _window(sim)
        assert sim.dev.accept_maintenance(msg, w.bundles(msg, sim.dev))[0]
    extra = _window(sim)
    assert "MAINT_RATE" in sim.dev.accept_maintenance(extra, w.bundles(extra, sim.dev))[1]


def test_unregistered_device_is_missed_from_registration(sim):
    w = sim.world
    quiet = w.add_device(SoftwareSecureElement(w.fw, w.clock), "c1")
    assert quiet.key not in {e["device_key"] for e in w.desk.scan_missed(w.now_ms())}


def test_desk_flags_a_heartbeat_that_does_not_chain(sim):
    w = sim.world
    first = sim.dev.heartbeat()
    w.desk.receive(first, w.now_ms())
    second = sim.dev.heartbeat()
    forged_chain = copy.deepcopy(second)
    forged_chain["body"]["prev_fp"] = "genesis"
    signer = sim.dev.signer
    forged_chain["sigs"] = []
    add_signature(forged_chain, signer)
    events = w.desk.receive(forged_chain, w.now_ms())
    assert [e["kind"] for e in events] == ["chain_break"]
    assert sim.dev.key not in w.desk.good_standing(w.now_ms())
