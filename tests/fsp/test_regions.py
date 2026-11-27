"""The regional rule and the corrected convergence rule (review of 25 September 2026).

CHARTER.md Article 3(g) and (h) cap the seat-holders from any one region at
MAX_PER_REGION and require that any K_ORDER seats span at least
MIN_SIGNER_REGIONS regions (both placeholders). Devices refuse an order or a
renewal whose signers span fewer regions, and a roster change must meet the
same span. SPEC.md Finding S17 drops the rule that let a hard signal count
toward convergence. Everything runs in the in-process simulation; nothing
touches a network, another process or the TPM.
"""

from __future__ import annotations

from harness.fsp import flows
from harness.fsp.crypto import Ed25519Signer, add_signature
from harness.fsp.seats import Roster, default_seats, make_roster, roster_violations, weakest_span
from harness.fsp.shim import receive_order
from harness.fsp.signals import find_convergence, make_signal

HOUR = 3_600_000
CLUSTERED = ["r1", "r1", "r2", "r2", "r3", "r3", "r4"]   # 2 per region, weakest span 2


def _public(seats):
    return [s.public() for s in seats]


def _clustered_roster(world, epoch=2):
    for seat, region in zip(world.seats, CLUSTERED):
        seat.region = region
    return make_roster(world.seats, epoch, world.seats[:4])


def test_default_roster_spans_three_regions_for_any_four_signers():
    seats = _public(default_seats())
    assert weakest_span(seats, 4) == 3
    assert not any("region" in p for p in roster_violations(seats, 7))


def test_three_seat_holders_from_one_region_break_the_cap():
    seats = default_seats()
    seats[1].region = seats[2].region = "r1"      # r1 now holds seats 0, 1, 2 and 6
    problems = roster_violations(_public(seats), 7)
    assert any("more than 2 seat-holders from one region" in p for p in problems)


def test_roster_where_four_seats_span_two_regions_is_rejected():
    """Two per region is within the cap, but four signers from two regions could
    then fill a quorum. The span rule rejects that roster."""
    seats = default_seats()
    for seat, region in zip(seats, CLUSTERED):
        seat.region = region
    problems = roster_violations(_public(seats), 7)
    assert any("could sign from only 2 regions" in p for p in problems)


def test_seat_with_no_region_is_rejected():
    seats = _public(default_seats())
    seats[3]["region"] = ""
    assert "a seat-holder with no region" in roster_violations(seats, 7)


def test_order_signed_from_two_regions_is_refused_at_check_2(sim):
    """A roster that slipped past the rule still cannot carry a two-region quorum:
    the device counts regions at check 2."""
    w = sim.world
    sim.dev.trust.roster = Roster(_clustered_roster(w))
    order = flows.build_order(w, "throttle", "c1", level=50, signers=(0, 1, 2, 3))
    res = receive_order(sim.dev, sim.pkg(order))
    assert res["status"] == "refused" and res["check"] == 2
    assert "regions" in res["reason"]


def test_order_signed_from_three_regions_passes_check_2(sim):
    w = sim.world
    sim.dev.trust.roster = Roster(_clustered_roster(w))
    order = flows.build_order(w, "throttle", "c1", level=50, signers=(0, 2, 4, 5))
    res = receive_order(sim.dev, sim.pkg(order))
    assert res.get("check") != 2


def test_renewal_signed_from_two_regions_is_refused(sim):
    w = sim.world
    sim.dev.trust.roster = Roster(_clustered_roster(w))
    ren = flows.issue_renewal(w, 2, signers=w.seats[:4])
    ok, reason = flows.deliver_renewal(w, sim.dev, ren)
    assert not ok and "regions" in reason


def test_roster_change_signed_from_two_regions_is_not_accepted(sim):
    w = sim.world
    in_force = Roster(_clustered_roster(w, epoch=2))
    successor = make_roster(default_seats(), 3, [])
    for i in (0, 1, 2, 3):                          # r1, r1, r2, r2 in the roster in force
        add_signature(successor, w.seats[i].signer)
    ok, why = in_force.accepts_successor(successor, 4, 7)
    assert not ok and "signers span 2 of 3" in why
    # Keep the same seat keys: dropping a key is a removal and needs K_REMOVE
    # (roster_change.py), which this test does not exercise.
    for seat, fresh in zip(w.seats, default_seats()):
        seat.region = fresh.region
    wide = make_roster(w.seats, 3, [])
    for i in (0, 2, 4, 6):                          # r1, r2, r3, r4
        add_signature(wide, w.seats[i].signer)
    assert in_force.accepts_successor(wide, 4, 7) == (True, "ok")


def test_hard_signal_no_longer_counts_toward_convergence():
    """SPEC.md 14.10: an attacker at a site can set off a tamper sensor. Before
    the fix, that tamper event plus one program signal formed a convergence set
    for a cluster throttle. The appendix says one hard signal stops nothing else."""
    s = Ed25519Signer()
    entries = []
    for kind, t in (("tamper", 0), ("program_tripwire", HOUR)):
        sig = make_signal(s, kind, "c1", t, {"k": kind})
        entries.append({"logged_ms": t, "body": sig["body"], "counted": True, "ref": kind})
    assert find_convergence(entries, "c1", 86400) is None
    extra = make_signal(s, "network_egress", "c1", 2 * HOUR, {"k": "egress"})
    entries.append({"logged_ms": 2 * HOUR, "body": extra["body"], "counted": True, "ref": "egress"})
    assert find_convergence(entries, "c1", 86400) is not None
