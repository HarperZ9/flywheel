"""Red team against P4, visible silence, and clone detection (SPEC.md sections 4, 7)."""

from __future__ import annotations

from harness.fsp import flows
from harness.fsp.backends.software import SoftwareSecureElement
from harness.fsp.device import Device
from harness.fsp.shim import tick


def test_silent_device_is_missed_at_three_intervals_not_before(sim):
    w = sim.world
    sim.advance(w.params.t_missed - 1)
    assert w.desk.scan_missed(w.now_ms()) == []
    sim.advance(1)
    events = w.desk.scan_missed(w.now_ms())
    assert {e["device_key"] for e in events} == {d.key for d in sim.devs}


def _run_until_closed(sim, quiet, talker, time_reachable: bool) -> tuple[int, list]:
    w = sim.world
    hours, members_seen = 0, []
    while quiet.failed is None:
        sim.advance(3600)
        hours += 1
        talker.accept_time(w.time_chain(talker))
        if time_reachable:
            quiet.accept_time(w.time_chain(quiet))
        if hours % (w.params.t_epoch // 3600) == 0:
            talker.outbox.append(talker.heartbeat())
            w.deliver(talker)
            ren = flows.issue_renewal(w, 1 + hours // 24)
            members_seen.append(quiet.key in ren["members"])
            flows.deliver_renewal(w, talker, ren)
        tick(quiet)
        tick(talker)
    assert talker.failed is None
    return hours, members_seen


def test_fully_offline_device_fails_closed_on_time_lapse_within_t_silent(sim):
    hours, _ = _run_until_closed(sim, *sim.devs, time_reachable=False)
    assert sim.devs[0].failed == "time_lapse"
    assert hours * 3600 <= sim.world.params.time_allowance + 3600


def test_device_that_only_hides_heartbeats_drops_from_roots_and_lapses(sim):
    hours, seen = _run_until_closed(sim, *sim.devs, time_reachable=True)
    assert sim.devs[0].failed == "renewal_lapse"
    assert seen[-1] is False and seen.count(True) <= 1
    assert hours * 3600 <= sim.world.params.t_silent


def test_lapse_warning_after_two_missed_roots(sim):
    w = sim.world
    quiet, talker = sim.devs
    warned = []
    for epoch in (2, 3):
        sim.advance(w.params.t_epoch + 1)
        talker.outbox.append(talker.heartbeat())
        w.deliver(talker)
        warned += flows.issue_renewal(w, epoch)["warn"]
    assert warned == [quiet.key]


def test_clone_proof_from_two_devices_sharing_one_key(sim):
    w = sim.world
    uds = b"\x07" * 32
    a = SoftwareSecureElement(w.fw, w.clock, uds=uds)
    b = SoftwareSecureElement(w.fw, w.clock, uds=uds)
    da = w.add_device(a, "c1")
    db = Device(b, w.params, w.trust(), "region-1")
    db.accept_time(w.time_chain(db))
    assert da.key == db.key
    da.outbox.append(da.heartbeat())
    db.outbox.append(db.heartbeat(profile="telemetry"))  # same counter, different content
    w.deliver(da)
    w.deliver(db)
    kinds = [e["kind"] for e in w.events]
    assert "clone_proof" in kinds
    assert da.key not in w.desk.good_standing(w.now_ms())


def test_counter_gap_is_a_soft_signal(sim):
    w = sim.world
    sim.dev.heartbeat()  # sent but never delivered
    sim.dev.outbox.append(sim.dev.heartbeat())
    w.deliver(sim.dev)
    assert "counter_gap" in [e["kind"] for e in w.events]


def test_forged_heartbeat_from_a_carrier_is_rejected(sim):
    w = sim.world
    hb = sim.dev.heartbeat()
    hb["body"]["tamper_state"] = "clear"
    hb["body"]["counter"] += 5
    events = w.desk.receive(hb, w.now_ms())
    assert events[0]["kind"] == "rejected_message"
