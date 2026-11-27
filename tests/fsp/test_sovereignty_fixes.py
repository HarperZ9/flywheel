"""Fixes from the sovereignty and industry reviews of 25 September 2026.

Each test states the rule it checks and the dispute it answers. Everything runs
in the in-process simulation; nothing touches a network, another process or
the TPM.
"""

from __future__ import annotations

import pytest

from harness.fsp.seats import Roster, default_seats, make_roster, roster_violations
from harness.fsp.shim import tick


def _public(seats):
    return [s.public() for s in seats]


# --- Reserved seats and flag consistency (CHARTER.md Article 3(c); GOVERNMENTS G6/G14)

def test_default_demo_roster_meets_every_seat_rule():
    assert roster_violations(_public(default_seats()), 7) == []


def test_seat_flagged_both_frontier_host_and_non_frontier_is_rejected():
    seats = default_seats()
    seats[0].non_frontier_state = True
    problems = roster_violations(_public(seats), 7)
    assert any("both frontier-host and non-frontier" in p for p in problems)


def test_reserved_seats_filled_by_frontier_host_nationals_are_rejected():
    """A national of a frontier-host economy that is not high-income no longer
    fills a reserved seat. Here the only not-high-income holders besides one are
    frontier-host nationals, so fewer than two reserved seats remain."""
    seats = default_seats()
    for s in seats:
        s.non_high_income = False
    seats[0].non_high_income = True      # frontier-host, not high-income
    seats[1].non_high_income = True      # frontier-host, not high-income
    seats[2].non_high_income = True      # the one valid reserved seat
    problems = roster_violations(_public(seats), 7)
    assert any("reserved" in p for p in problems)


def test_successor_roster_with_both_flags_is_not_accepted(sim):
    w = sim.world
    w.seats[0].non_frontier_state = True
    new = make_roster(w.seats, 2, w.seats[:4])
    ok, why = Roster(w.roster_msg).accepts_successor(new, 4, 7)
    assert not ok and "both frontier-host and non-frontier" in why


# --- Append-only reference set (SPEC.md 3.2 rule R1; VENDORS Finding V11)

def test_reference_set_refuses_removal(sim):
    with pytest.raises(TypeError):
        sim.dev.trust.reference_fw.discard(sim.world.fw)
    with pytest.raises(TypeError):
        sim.dev.trust.reference_fw -= {sim.world.fw}


def test_withdrawn_measurement_does_not_fail_a_device_that_installed_it(sim):
    """Whoever edits the set cannot fail every device running a listed build:
    the device checks against the set in force when its firmware was installed."""
    sim.dev.trust.reference_fw = set()   # the whole set replaced by an empty one
    tick(sim.dev)
    assert sim.dev.failed is None


def test_unlisted_new_firmware_still_fails_attestation(sim):
    sim.backends[0].reflash("bb" * 32)
    tick(sim.dev)
    assert sim.dev.failed == "attestation"


def test_listed_firmware_update_is_accepted_and_becomes_the_installed_build(sim):
    new_fw = "cc" * 32
    sim.dev.trust.reference_fw.add(new_fw)
    sim.backends[0].reflash(new_fw)
    tick(sim.dev)
    assert sim.dev.failed is None and sim.dev.installed_fw == new_fw
