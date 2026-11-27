"""Red team against P2, no single party acts (SPEC.md sections 5, 7.3 and 8.3)."""

from __future__ import annotations

import copy

from harness.fsp import flows
from harness.fsp.crypto import Ed25519Signer, add_signature, sign_record, valid_signers
from harness.fsp.seats import Roster, default_seats, make_roster, roster_violations, vote
from harness.fsp.shim import receive_order


def test_three_of_seven_is_refused_at_check_2(sim):
    order = flows.build_order(sim.world, "throttle", "c1", level=50, signers=(2, 3, 4))
    res = receive_order(sim.dev, sim.pkg(order))
    assert (res["check"], res["reason"]) == (2, "3 of 4 required seat signatures")


def test_one_seat_signing_four_times_counts_once(sim):
    order = flows.build_order(sim.world, "throttle", "c1", level=50, signers=(2,),
                              publish=False)
    for _ in range(3):
        order["sigs"].append(copy.deepcopy(order["sigs"][0]))
    sim.world.publish(order)
    sim.world.cosign()
    assert receive_order(sim.dev, sim.pkg(order))["check"] == 2


def test_outsider_keys_do_not_count_toward_the_quorum(sim):
    order = flows.build_order(sim.world, "throttle", "c1", level=50, signers=(2,),
                              publish=False)
    for _ in range(4):
        add_signature(order, Ed25519Signer())
    sim.world.publish(order)
    sim.world.cosign()
    assert len(valid_signers(order)) == 5
    assert receive_order(sim.dev, sim.pkg(order))["check"] == 2


def test_halt_without_a_non_frontier_signer_is_refused_at_check_3(sim):
    order, notice = sim.halt(signers=flows.NO_NONFRONTIER)
    assert receive_order(sim.dev, sim.pkg(order, notice))["check"] == 3


def test_throttle_needs_no_non_frontier_signer(sim):
    order = flows.build_order(sim.world, "throttle", "c1", level=50,
                              signers=flows.NO_NONFRONTIER)
    assert receive_order(sim.dev, sim.pkg(order))["status"] == "applied"


def test_body_changed_after_signing_invalidates_every_signature(sim):
    order = flows.build_order(sim.world, "throttle", "c1", level=50, publish=False)
    order["body"]["level"] = 20        # in range, so check 1 passes and check 2 decides
    sim.world.publish(order)
    sim.world.cosign()
    assert receive_order(sim.dev, sim.pkg(order))["check"] == 2


def test_signature_on_another_message_type_does_not_verify_as_an_order(sim):
    """Domain tags: a seat's vote signature over the same body is not an order signature."""
    order = flows.build_order(sim.world, "throttle", "c1", level=50, signers=(2,),
                              publish=False)
    for i in (3, 4, 5):
        rec = sign_record(sim.world.seats[i].signer, "vote", order["body"])
        order["sigs"].append(rec)
    sim.world.publish(order)
    sim.world.cosign()
    assert receive_order(sim.dev, sim.pkg(order))["check"] == 2


def test_renewal_with_three_seats_is_refused(sim):
    w = sim.world
    ren = flows.issue_renewal(w, 2, signers=w.seats[:3])
    ok, reason = flows.deliver_renewal(w, sim.dev, ren)
    assert not ok and reason.startswith("3 of 4")


def test_blocking_a_renewal_needs_four_refusals():
    """With plain k-of-n, n - k + 1 seats must withhold to block (Finding S4)."""
    seats = default_seats()
    n, k = 7, 4
    assert n - k + 1 == 4
    for refusing in range(0, 8):
        remaining = n - refusing
        assert (remaining >= k) == (refusing < 4)
    assert len(seats) == n


def test_roster_change_needs_k_order_and_keeps_the_rules(sim):
    w = sim.world
    roster = Roster(w.roster_msg)
    new_seats = default_seats()
    three = make_roster(new_seats, 2, [])
    for s in w.seats[:3]:
        add_signature(three, s.signer)
    assert roster.accepts_successor(three, 4, 7)[0] is False
    bad = default_seats()
    bad[4].frontier_host_state = True  # a third frontier-host seat
    bad_msg = make_roster(bad, 2, [])
    for s in w.seats[:4]:
        add_signature(bad_msg, s.signer)
    ok, why = roster.accepts_successor(bad_msg, 4, 7)
    assert not ok and "frontier-host" in why
    # A successor that keeps every seat key needs only K_ORDER. Replacing keys is
    # a removal, which needs K_REMOVE (see test_removal_needs_k_remove_and_a_cause).
    good = make_roster(w.seats, 2, [])
    for s in w.seats[:4]:
        add_signature(good, s.signer)
    assert roster.accepts_successor(good, 4, 7) == (True, "ok")
    replaced = make_roster(new_seats, 2, [])
    for s in w.seats[:4]:
        add_signature(replaced, s.signer)
    ok, why = roster.accepts_successor(replaced, 4, 7)
    assert not ok and ("K_REMOVE" in why or "cause" in why)


def test_roster_rules_catch_each_violation():
    seats = [s.public() for s in default_seats()]
    assert roster_violations(seats, 7) == []
    dup = copy.deepcopy(seats)
    dup[1]["nationality"] = dup[0]["nationality"]
    assert "more than one seat-holder of one nationality" in roster_violations(dup, 7)
    none_nf = copy.deepcopy(seats)
    for s in none_nf:
        s["non_frontier_state"] = False
    assert any("no frontier" in p for p in roster_violations(none_nf, 7))


def test_votes_are_attributable(sim):
    seat = sim.world.seats[3]
    v = vote(seat, "ab" * 32, "no", "crit-1", "cd" * 32)
    assert valid_signers(v) == [seat.key] and v["body"]["choice"] == "no"
