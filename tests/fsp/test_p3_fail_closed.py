"""Red team against P3, fail closed one device at a time (SPEC.md sections 6, 7, 12)."""

from __future__ import annotations

from harness.fsp import flows
from harness.fsp.canon import fingerprint
from harness.fsp.crypto import Ed25519Signer, envelope
from harness.fsp.shim import receive_order, tick

DAY = 86400


def _types(dev):
    return [m["type"] for m in dev.outbox]


def test_tamper_fails_that_device_closed_and_no_other(sim):
    sim.backends[0].trip_tamper()
    tick(sim.dev)
    tick(sim.devs[1])
    assert sim.dev.failed == "tamper" and "failclosed" in _types(sim.dev)
    assert sim.devs[1].failed is None
    assert sim.dev.enforcer.state["failed_closed"] is True


def test_unapproved_firmware_fails_attestation(sim):
    sim.backends[0].reflash("bb" * 32)
    tick(sim.dev)
    assert sim.dev.failed == "attestation"


def test_counter_rollback_fails_closed(sim):
    snap = sim.backends[0].snapshot()
    for _ in range(3):
        sim.dev.heartbeat()
    sim.backends[0].restore(snap)
    tick(sim.dev)
    assert sim.dev.failed == "counter_regression"


def test_counter_rollback_is_caught_at_boot_from_the_last_logged_heartbeat(sim):
    hb = sim.dev.heartbeat()
    sim.backends[0].restore({"counter": 0})
    sim.dev.high_water = 0  # a fresh boot forgets memory
    sim.dev.boot_check(hb)
    assert sim.dev.failed == "counter_regression"


def test_renewal_lapse_fails_closed_and_a_new_renewal_restores(sim):
    w = sim.world
    for _ in range(6):  # time stays reachable; only renewals stop arriving
        sim.advance(86400)
        sim.dev.accept_time(w.time_chain(sim.dev))
    sim.advance(w.params.renewal_validity - 6 * 86400 - 60)
    sim.dev.accept_time(w.time_chain(sim.dev))
    tick(sim.dev)
    assert sim.dev.failed is None
    sim.advance(120)
    tick(sim.dev)
    assert sim.dev.failed == "renewal_lapse"
    sim.dev.outbox.append(sim.dev.heartbeat())
    w.deliver(sim.dev)
    ren = flows.issue_renewal(w, 2)
    assert flows.deliver_renewal(w, sim.dev, ren) == (True, "ok")
    assert sim.dev.failed is None and "restored" in _types(sim.dev)


def test_no_time_quorum_for_72_hours_fails_closed(sim):
    sim.advance(72 * 3600 + 1)
    tick(sim.dev)
    assert sim.dev.failed == "time_lapse"
    assert sim.dev.accept_time(sim.world.time_chain(sim.dev))[0]
    assert sim.dev.failed is None


def test_power_cycle_cannot_stretch_a_renewal(sim):
    sim.backends[0].power_cycle()
    assert sim.dev.t_work() is None
    sim.advance(8 * DAY)
    assert sim.dev.accept_time(sim.world.time_chain(sim.dev))[0]
    tick(sim.dev)
    assert sim.dev.failed == "renewal_lapse"


def test_no_remote_message_can_fail_a_device_closed(sim):
    order, notice = sim.halt()
    receive_order(sim.dev, sim.pkg(order, notice))
    receive_order(sim.dev, {"order_bytes": b"{not json"})
    receive_order(sim.dev, {"order": envelope("failclosed", {"reason": "remote"})})
    sim.advance(sim.world.params.t_halt_notice + 1)
    tick(sim.dev)
    assert sim.dev.failed is None
    assert sim.dev.enforcement()["state"] == "halted"


def _inspection(w, dev):
    insp = envelope("inspection", {"device_key": dev.key, "finding": "sensor re-armed"},
                    [w.inspector])
    body = {"device_key": dev.key, "inspection_fp": fingerprint("inspection", insp["body"])}
    return insp, body


def test_hard_signal_restore_needs_inspection_and_k_restore(sim):
    w = sim.world
    sim.backends[0].trip_tamper()
    tick(sim.dev)
    insp, body = _inspection(w, sim.dev)
    three = envelope("restoration", body, [s.signer for s in w.seats[:3]])
    sim.backends[0].clear_tamper_after_inspection()
    assert sim.dev.restore_after_inspection(insp, three)[0] is False
    fake = envelope("inspection", insp["body"], [Ed25519Signer()])
    four = envelope("restoration", body, [s.signer for s in w.seats[:4]])
    assert sim.dev.restore_after_inspection(fake, four)[0] is False
    assert sim.dev.restore_after_inspection(insp, four) == (True, "ok")
    assert sim.dev.failed is None


def test_renewal_alone_cannot_clear_a_hard_signal(sim):
    w = sim.world
    sim.backends[0].trip_tamper()
    tick(sim.dev)
    sim.dev.outbox.append(sim.dev.heartbeat())
    w.deliver(sim.dev)
    ren = flows.issue_renewal(w, 2)
    assert sim.dev.key not in ren["members"]
    ok, _ = flows.deliver_renewal(w, sim.dev, ren)
    assert not ok and sim.dev.failed == "tamper"
