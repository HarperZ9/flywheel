"""Positive paths and false-alarm controls for red-team fixes (part 1 of 2: halts and roster)."""

from __future__ import annotations

from harness.fsp import flows, roster_change
from harness.fsp.crypto import Ed25519Signer, envelope, msg_id
from harness.fsp.seats import Roster, default_seats, make_roster
from harness.fsp.shim import receive_order, tick

HOUR_MS = 3_600_000
CAUSE = "ab" * 32


def _applied_halt(sim, hours=3):
    w = sim.world
    eff = w.now_ms() + w.params.t_halt_notice * 1000
    notice = flows.post_notice(w, "c1", [sim.tag], eff, eff + hours * HOUR_MS)
    eff = notice[1] + w.params.t_halt_notice * 1000
    order = flows.build_order(w, "halt", "c1", tags=[sim.tag], notice=notice,
                              effective_ms=eff, expires_ms=eff + hours * HOUR_MS)
    receive_order(sim.dev, sim.pkg(order, notice))
    sim.advance(w.params.t_halt_notice + 1)
    tick(sim.dev)
    return order


def _renewal_of(sim, old, decision=None):
    w = sim.world
    eff = w.now_ms() + w.params.t_halt_notice * 1000
    notice = flows.post_notice(w, "c1", [sim.tag], eff, eff + 3 * HOUR_MS)
    eff = notice[1] + w.params.t_halt_notice * 1000
    order = flows.build_order(w, "halt", "c1", tags=[sim.tag], notice=notice, renews=msg_id(old),
                              effective_ms=eff, expires_ms=eff + 2 * HOUR_MS)
    pkg = sim.pkg(order, notice)
    if decision is not None:
        pkg["governance"], pkg["governance_bundles"] = decision, w.bundles(decision, sim.dev)
    return pkg


def test_halt_renewal_with_a_logged_governance_decision_goes_pending(sim):
    old = _applied_halt(sim)
    decision = flows.governance_renewal(sim.world, msg_id(old))
    assert receive_order(sim.dev, _renewal_of(sim, old, decision))["status"] == "pending"


def test_halt_renewal_without_a_decision_is_refused_at_check_9(sim):
    old = _applied_halt(sim)
    res = receive_order(sim.dev, _renewal_of(sim, old))
    assert res["check"] == 9 and "governance" in res["reason"]


def test_decision_for_another_order_does_not_renew(sim):
    old = _applied_halt(sim)
    decision = flows.governance_renewal(sim.world, "cd" * 32)
    res = receive_order(sim.dev, _renewal_of(sim, old, decision))
    assert res["check"] == 9 and "does not name this order" in res["reason"]


def test_lift_ends_a_pending_halt_and_the_halt_is_refused_afterwards(sim):
    order, notice = sim.halt()
    pkg = sim.pkg(order, notice)
    assert receive_order(sim.dev, pkg)["status"] == "pending"
    lift = flows.build_order(sim.world, "lift", "c1", lifts=msg_id(order))
    assert receive_order(sim.dev, sim.pkg(lift))["status"] == "applied"
    again = receive_order(sim.dev, sim.pkg(order, notice))
    assert again["check"] == 11 and "lift" in again["reason"]


def _successor(sim, seats, signers, **extra):
    del sim
    body = {"epoch": 2, "seats": [s.public() for s in seats], **extra}
    return envelope("roster", body, [s.signer for s in signers])


def test_removal_needs_k_remove_and_a_cause(sim):
    w = sim.world
    roster = Roster(w.roster_msg)
    fresh = default_seats()
    seats = w.seats[:6] + [fresh[6]]
    removed = w.seats[6].key
    no_cause = _successor(sim, seats, w.seats[:5])
    assert "cause" in roster.accepts_successor(no_cause, 4, 7)[1]
    four = _successor(sim, seats, w.seats[:4], removals={removed: CAUSE})
    assert "K_REMOVE" in roster.accepts_successor(four, 4, 7)[1]
    five = _successor(sim, seats, w.seats[:5], removals={removed: CAUSE})
    assert roster.accepts_successor(five, 4, 7) == (True, "ok")


def test_revocation_needs_a_request_a_proof_or_k_remove(sim):
    w = sim.world
    roster = Roster(w.roster_msg)
    public = [s.public() for s in w.seats]
    target = w.seats[6]
    grab = _successor(sim, w.seats, w.seats[:4],
                      revocations=[{"key": target.key, "basis": "compromise", "cause_fp": CAUSE}],
                      revoked=[{"key": target.key}])
    assert "K_REMOVE" in roster.accepts_successor(grab, 4, 7)[1]
    five = _successor(sim, w.seats, w.seats[:5],
                      revocations=[{"key": target.key, "basis": "compromise", "cause_fp": CAUSE}],
                      revoked=[{"key": target.key}])
    assert roster.accepts_successor(five, 4, 7) == (True, "ok")
    request = envelope("revocation-request", {"key": target.key}, [target.signer])
    own = envelope("roster", {"epoch": 2, "seats": public, "revoked": [{"key": target.key}],
                              "revocations": [{"key": target.key, "basis": "holder",
                                               "evidence": request}]}, [])
    assert roster.accepts_successor(own, 4, 7) == (True, "ok")
    in_force = Roster(own)
    assert target.key not in in_force.signers(envelope("x", {"y": 1}, [target.signer]))
    assert roster_change.breaches(in_force, 7) == [
        "6 of 7 seat keys active; a charter review opens"]
    forged = envelope("revocation-request", {"key": target.key}, [w.seats[0].signer])
    bad = envelope("roster", {"epoch": 2, "seats": public, "revoked": [{"key": target.key}],
                              "revocations": [{"key": target.key, "basis": "holder",
                                               "evidence": forged}]}, [])
    assert roster.accepts_successor(bad, 4, 7)[0] is False


def test_reenrolment_needs_the_recovery_key_and_no_seat(sim):
    w = sim.world
    target = w.seats[6]
    public = [s.public() for s in w.seats]
    request = envelope("revocation-request", {"key": target.key}, [target.signer])
    revoked = Roster(envelope("roster", {"epoch": 2, "seats": public,
                                         "revoked": [{"key": target.key}],
                                         "revocations": [{"key": target.key, "basis": "holder",
                                                          "evidence": request}]}, []))
    fresh = Ed25519Signer()
    seats = [{**p, "key": fresh.public_hex()} if p["key"] == target.key else p for p in public]
    body = {"epoch": 3, "seats": seats, "revoked": [],
            "reenrol": [{"old": target.key, "new": fresh.public_hex()}]}
    good = envelope("roster", body, [fresh, target.recovery])
    assert revoked.accepts_successor(good, 4, 7) == (True, "ok")
    by_seats = envelope("roster", body, [fresh, *[s.signer for s in w.seats[:5]]])
    assert "recovery key" in revoked.accepts_successor(by_seats, 4, 7)[1]


def test_device_adopts_a_roster_only_from_the_logs(sim):
    w = sim.world
    good = make_roster(w.seats, 2, w.seats[:4])
    assert sim.dev.adopt_roster(good, [])[0] is False
    w.publish(good)
    w.cosign()
    assert sim.dev.adopt_roster(good, w.bundles(good, sim.dev)) == (True, "ok")
