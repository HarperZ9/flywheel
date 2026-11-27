"""Red-team outside-review attacks (part 2 of 2: crafted orders, withholding, silence, chain breaks).

Completes the full 29-attack red-team suite alongside test_review_attacks_part1.py.
"""

from __future__ import annotations

import pytest

from harness.fsp import flows
from harness.fsp.backends.software import SoftwareSecureElement
from harness.fsp.canon import fingerprint
from harness.fsp.crypto import msg_id
from harness.fsp.shim import receive_order, tick

DAY = 86_400
HOUR_MS = 3_600_000


def _apply_halt(sim, **kw):
    order, notice = sim.halt(**kw)
    receive_order(sim.dev, sim.pkg(order, notice))
    sim.advance(sim.world.params.t_halt_notice + 1)
    out = tick(sim.dev)
    return order, out


# 6. Crafted orders that halt more than the named workload


def test_fails_throttle_to_level_zero_stops_every_workload_without_halt_rules(sim):
    """Throttle level 0 must be refused so throttles cannot masquerade as halts."""
    order = flows.build_order(sim.world, "throttle", "c1", level=0,
                              signers=flows.NO_NONFRONTIER)
    res = receive_order(sim.dev, sim.pkg(order))
    assert res["status"] == "refused", f"level-0 throttle {res['status']}, stopping all work"


@pytest.mark.parametrize("level", [None, "0", -50, 150])
def test_fails_out_of_range_throttle_level_is_not_refused_at_check_1(sim, level):
    """Invalid throttle levels must produce a check-1 refusal and never break heartbeats."""
    order = flows.build_order(sim.world, "throttle", "c1", level=level)
    try:
        res = receive_order(sim.dev, sim.pkg(order))
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"shim raised {type(exc).__name__} on level {level!r}")
    try:
        sim.dev.heartbeat()
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"device cannot heartbeat after level {level!r}: {type(exc).__name__}")
    assert res["status"] == "refused" and res["check"] == 1


@pytest.mark.parametrize("cite", ["other_tag_notice", "roster_entry"])
def test_fails_halt_notice_is_not_bound_to_the_halt_scope(sim, cite):
    """Check 10 must verify that the cited notice matches cluster, tags, seat sig, and expiry."""
    w = sim.world
    if cite == "other_tag_notice":
        notice, eff = sim.halt_notice(tags=[sim.tag_b])
    else:
        idx = w.logs[0].find(fingerprint("entry", w.roster_msg))
        notice = (w.roster_msg, w.logs[0].leaves[idx]["logged_ms"])
        eff = w.now_ms() + w.params.t_halt_notice * 1000
    order = flows.build_order(w, "halt", "c1", tags=[sim.tag, sim.tag_b], notice=notice,
                              effective_ms=eff, expires_ms=eff + HOUR_MS)
    res = receive_order(sim.dev, sim.pkg(order, notice))
    assert res["status"] == "refused" and res["check"] == 10, res


def test_fails_halt_renewal_naming_a_bogus_order_bypasses_rate_halt(sim):
    """Bogus renews field must fail check 9 instead of bypassing RATE_HALT."""
    for _ in range(2):
        _apply_halt(sim)
        sim.advance(3600 + 5)
        tick(sim.dev)
    order, notice = sim.halt(renews="00" * 32)
    res = receive_order(sim.dev, sim.pkg(order, notice))
    assert res.get("check") == 9, f"third halt of one tag in 30 days: {res['status']}"


def test_fails_halt_renewal_silently_ends_a_halt_on_other_tags(sim):
    """A renewal targeting alpha cannot silently end a live halt on beta."""
    w = sim.world
    eff = w.now_ms() + w.params.t_halt_notice * 1000
    notice = flows.post_notice(w, "c1", [sim.tag_b], eff, eff + 3 * HOUR_MS)
    eff = notice[1] + w.params.t_halt_notice * 1000
    halt_b = flows.build_order(w, "halt", "c1", tags=[sim.tag_b], notice=notice,
                               effective_ms=eff, expires_ms=eff + 3 * HOUR_MS)
    receive_order(sim.dev, sim.pkg(halt_b, notice))
    sim.advance(w.params.t_halt_notice + 1)
    tick(sim.dev)
    assert sim.tag_b in sim.dev.enforcement()["tags"]
    _apply_halt(sim, tags=[sim.tag], renews=msg_id(halt_b))
    assert sim.tag_b in sim.dev.enforcement()["tags"], "beta's halt ended with no lift"


def test_fails_lift_during_the_notice_period_does_not_cancel_the_pending_halt(sim):
    """A lift issued during the notice lead cancels the pending halt permanently."""
    order, notice = sim.halt()
    assert receive_order(sim.dev, sim.pkg(order, notice))["status"] == "pending"
    lift = flows.build_order(sim.world, "lift", "c1", lifts=msg_id(order))
    assert receive_order(sim.dev, sim.pkg(lift))["status"] == "applied"
    sim.advance(sim.world.params.t_halt_notice + 1)
    tick(sim.dev)
    assert sim.tag not in sim.dev.enforcement()["tags"], "lifted halt applied anyway"


def test_fails_malformed_bundle_raises_instead_of_a_signed_refusal(sim):
    """Stripping required fields from 2 of 3 bundles yields a signed check-4 refusal."""
    order = flows.build_order(sim.world, "throttle", "c1", level=50)
    pkg = sim.pkg(order)
    for bundle in pkg["bundles"][:2]:
        del bundle["checkpoint"]
    pkg["bundles"][2]["cosigs"] = "not a list of objects"
    try:
        res = receive_order(sim.dev, pkg)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"shim raised {type(exc).__name__} on a malformed bundle")
    assert res["status"] == "refused" and res["check"] == 4
    assert sim.dev.outbox[-1]["type"] == "refusal"


# 7. Denial by withholding renewals


def _heartbeats(sim):
    for d in sim.devs:
        d.outbox.append(d.heartbeat())
        sim.world.deliver(d)


def test_holds_three_seats_withholding_cannot_block_a_renewal(sim):
    """Three withholding seats cannot block a 4-of-7 renewal root."""
    w = sim.world
    _heartbeats(sim)
    ren = flows.issue_renewal(w, 2, signers=w.seats[3:])
    assert flows.deliver_renewal(w, sim.dev, ren) == (True, "ok")


def test_holds_documented_limit_four_withholding_seats_lapse_the_fleet(sim):
    """Four withholding seats block renewal so devices lapse cleanly at valid_until."""
    w = sim.world
    for epoch in range(2, 9):
        sim.advance(DAY)
        _heartbeats(sim)
        ren = flows.issue_renewal(w, epoch, signers=w.seats[4:])
        assert flows.deliver_renewal(w, sim.dev, ren)[0] is False
        for d in sim.devs:
            d.accept_time(w.time_chain(d))
            tick(d)
        assert all(d.failed is None for d in sim.devs)
    sim.advance(60)
    for d in sim.devs:
        tick(d)
    assert all(d.failed == "renewal_lapse" for d in sim.devs)


def test_fails_withholding_seats_are_never_logged_as_silent(sim):
    """Withholding seats are logged in a seat-silence entry after T_REFUSE."""
    w = sim.world
    _heartbeats(sim)
    start = {lg.log_id: lg.size() for lg in w.logs}
    ren = flows.issue_renewal(w, 2, signers=w.seats[3:])
    sim.advance(w.params.t_refuse + 1)
    _heartbeats(sim)
    w.cosign()
    silent = {s.key for s in w.seats[:3]}
    named = False
    for lg in w.logs:
        for leaf in lg.leaves[start[lg.log_id]:]:
            if leaf["entry"] is ren["msg"]:
                continue
            text = repr(leaf["entry"])
            named = named or any(k in text for k in silent)
    assert named, "no log entry names the three silent seats after T_REFUSE"


# 8. Silence and chain continuity


def test_fails_registered_device_that_never_heartbeats_is_never_missed(sim):
    """A registered device that never sends a heartbeat is flagged missed after T_MISSED."""
    w = sim.world
    quiet = w.add_device(SoftwareSecureElement(w.fw, w.clock), "c1")
    sim.advance(w.params.t_missed + 1)
    events = w.desk.scan_missed(w.now_ms())
    assert quiet.key in {e["device_key"] for e in events}


def test_fails_broken_heartbeat_chain_is_not_a_hard_signal_at_boot(sim):
    """A rolled-back heartbeat chain head with intact counter fails closed at boot_check."""
    dev = sim.dev
    dev.heartbeat()
    stale = dev.prev_fp
    last = dev.heartbeat()
    dev.prev_fp = stale
    dev.boot_check(last)
    assert dev.failed is not None
