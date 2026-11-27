"""Red team against the time rule (SPEC.md section 6, threat row 14.7)."""

from __future__ import annotations

import copy

from harness.fsp.shim import tick
from harness.fsp.timesrc import TimeServer, chain_links_valid, form_quorum, malfeasance, query_chain
from harness.fsp.world import SimClock

HOUR_MS = 3_600_000


def _servers(clock, parties=("p0", "p1", "p2")):
    return [TimeServer(f"ts-{i}", p, f"J{i}", clock) for i, p in enumerate(parties)]


def _keys(servers):
    return {s.server_id: s.key for s in servers}, {s.server_id: s.party for s in servers}


def test_one_fast_liar_yields_a_proof_and_does_not_move_the_quorum():
    clock = SimClock()
    servers = _servers(clock)
    servers[1].offset_ms = HOUR_MS
    keys, parties = _keys(servers)
    chain = query_chain(servers)
    proof = malfeasance(chain, keys)
    assert proof is not None and "ts-1" in (proof["earlier"], proof["later"])
    q = form_quorum(chain, keys, parties, 2, 10)
    assert q is not None and "ts-1" not in q.servers
    assert abs(q.t_ms - int(clock() * 1000)) < 1000


def test_one_slow_liar_yields_a_proof():
    clock = SimClock()
    servers = _servers(clock)
    servers[2].offset_ms = -HOUR_MS
    keys, _ = _keys(servers)
    assert malfeasance(query_chain(servers), keys) is not None


def test_two_servers_of_one_party_cannot_form_a_quorum_alone():
    clock = SimClock()
    servers = _servers(clock, parties=("p0", "p0", "p2"))
    servers[2].offset_ms = HOUR_MS
    keys, parties = _keys(servers)
    assert form_quorum(query_chain(servers), keys, parties, 2, 10) is None


def test_reordered_chain_breaks_the_links():
    clock = SimClock()
    servers = _servers(clock)
    keys, parties = _keys(servers)
    chain = query_chain(servers)
    swapped = copy.deepcopy(chain)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    assert chain_links_valid(chain, keys) and not chain_links_valid(swapped, keys)
    assert form_quorum(swapped, keys, parties, 2, 10) is None


def test_device_never_moves_time_backward(sim):
    w = sim.world
    for s in w.time_servers:
        s.offset_ms = -HOUR_MS
    ok, reason = sim.dev.accept_time(w.time_chain(sim.dev))
    assert not ok and "backward" in reason


def test_colluding_quorum_cannot_jump_a_running_timer_forward(sim):
    """Row 14.7, as revised after the outside review: while the boot id holds,
    the device refuses a quorum more than TIME_TOL plus DRIFT_PPM of elapsed time
    ahead of its own timer, and reports the refused chain as signed evidence."""
    w = sim.world
    for s in w.time_servers[:2]:
        s.offset_ms = 8 * 24 * HOUR_MS
    ok, reason = sim.dev.accept_time(w.time_chain(sim.dev))
    assert not ok and "ahead of the running timer" in reason
    kinds = [m["body"].get("kind") for m in sim.dev.outbox if m["type"] == "time-malfeasance"]
    assert "forward_jump" in kinds and "chained" in kinds


def test_colluding_quorum_after_a_boot_moves_time_forward_but_leaves_a_proof(sim):
    """The limit that remains (row 14.7): after a power cycle the device has no
    running timer to compare with, so K_TIME colluding servers can move time
    forward. The honest server's reply makes the shift a chained proof."""
    w = sim.world
    sim.backends[0].power_cycle()
    for s in w.time_servers[:2]:
        s.offset_ms = 8 * 24 * HOUR_MS
    ok, _ = sim.dev.accept_time(w.time_chain(sim.dev))
    assert ok
    kinds = [m["body"].get("kind") for m in sim.dev.outbox if m["type"] == "time-malfeasance"]
    assert "chained" in kinds


def test_chain_not_started_by_the_device_is_refused(sim):
    ok, reason = sim.dev.accept_time(sim.world.time_chain())
    assert not ok and "nonce" in reason


def test_replayed_device_chain_is_refused_after_a_power_cycle(sim):
    """Finding S13: a chain the device accepted once cannot be replayed to it, and
    a fresh colluding quorum below the stored floor is refused after boot."""
    w = sim.world
    recorded = w.time_chain(sim.dev)
    assert sim.dev.accept_time(recorded)[0]
    sim.advance(60 * 3600)
    tick(sim.dev)                                  # raises the stored floor
    sim.backends[0].power_cycle()
    ok, reason = sim.dev.accept_time(recorded)
    assert not ok and "nonce" in reason
    for s in w.time_servers:
        s.offset_ms = -59 * HOUR_MS                # every server claims day 0
    ok, reason = sim.dev.accept_time(w.time_chain(sim.dev))
    assert not ok and "floor" in reason


def test_nonce_from_before_a_boot_is_refused(sim):
    w = sim.world
    chain = w.time_chain(sim.dev)
    sim.backends[0].power_cycle()
    ok, reason = sim.dev.accept_time(chain)
    assert not ok and "before the last boot" in reason


def test_quorum_members_sit_within_time_tol_of_each_other():
    """Finding P17: replies 8 s below and 8 s above a middle reply are 16 s apart,
    more than TIME_TOL (10 s), so no set of three forms."""
    clock = SimClock()
    servers = _servers(clock)
    servers[0].offset_ms, servers[2].offset_ms = -8_000, 8_000
    keys, parties = _keys(servers)
    q = form_quorum(query_chain(servers), keys, parties, 3, 10)
    assert q is None
