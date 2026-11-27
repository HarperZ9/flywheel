"""Red team against order rules: expiry, notice, rate, scope, replay (SPEC.md 8, 12)."""

from __future__ import annotations

from harness.fsp import flows
from harness.fsp.canon import canon
from harness.fsp.crypto import envelope
from harness.fsp.shim import receive_order, tick

DAY_MS = 86_400_000


def _apply_halt(sim, **kw):
    order, notice = sim.halt(**kw)
    res = receive_order(sim.dev, sim.pkg(order, notice))
    sim.advance(sim.world.params.t_halt_notice + 1)
    out = tick(sim.dev)
    return order, notice, res, out


def test_halt_expires_on_its_own_with_a_receipt(sim):
    order, _, _, out = _apply_halt(sim)
    assert out[0]["status"] == "applied"
    sim.advance(3600 + 5)
    tick(sim.dev)
    assert sim.dev.enforcement()["state"] == "normal"
    events = [m["body"].get("event") for m in sim.dev.outbox if m["type"] == "receipt"]
    assert events == ["applied", "expired"]


def test_expiry_beyond_t_halt_max_is_refused(sim):
    order, notice = sim.halt(expires_ms=sim.world.now_ms() + 8 * DAY_MS)
    res = receive_order(sim.dev, sim.pkg(order, notice))
    assert res["check"] == 7 and "T_HALT_MAX" in res["reason"]


def test_halt_without_notice_is_refused(sim):
    order = flows.build_order(sim.world, "halt", "c1", tags=[sim.tag],
                              effective_ms=sim.world.now_ms() + 7_200_000)
    assert receive_order(sim.dev, sim.pkg(order))["check"] == 10


def test_halt_with_too_short_a_notice_lead_is_refused(sim):
    notice, _ = sim.halt_notice()
    order = flows.build_order(sim.world, "halt", "c1", tags=[sim.tag], notice=notice,
                              effective_ms=notice[1] + 60_000)
    res = receive_order(sim.dev, sim.pkg(order, notice))
    assert res["check"] == 10 and "T_HALT_NOTICE" in res["reason"]


def test_notice_logged_after_the_order_is_refused(sim):
    w = sim.world
    eff = w.now_ms() + 2 * 3_600_000
    body = {"cluster_id": "c1", "workload_tags": [sim.tag], "criterion_id": "crit-1",
            "planned_effective_ms": eff, "expires_ms": eff + 3_600_000,
            "appeal_route": "panel-1", "status": "proposed"}
    notice_msg = envelope("dependent-notice", body, [w.seats[2].signer])
    order = flows.build_order(w, "halt", "c1", tags=[sim.tag], notice=(notice_msg, w.now_ms()),
                              effective_ms=eff)
    w.publish(notice_msg)
    w.cosign()
    res = receive_order(sim.dev, sim.pkg(order, (notice_msg, w.now_ms())))
    assert res["check"] == 10 and "not before the order" in res["reason"]


def test_third_halt_of_one_tag_in_30_days_is_rate_limited(sim):
    for _ in range(2):
        _apply_halt(sim)
        sim.advance(3600 + 5)
        tick(sim.dev)
    order, notice = sim.halt()
    assert receive_order(sim.dev, sim.pkg(order, notice))["check"] == 9


def test_logged_appeal_decision_allows_an_extra_halt(sim):
    w = sim.world
    for _ in range(2):
        _apply_halt(sim)
        sim.advance(3600 + 5)
        tick(sim.dev)
    appeal = envelope("appeal-decision", {"allows_extra_halt_for": [sim.tag]}, w.panel[:2])
    w.publish(appeal)
    w.cosign()
    order, notice = sim.halt()
    pkg = sim.pkg(order, notice)
    pkg["appeal"], pkg["appeal_bundles"] = appeal, w.bundles(appeal, sim.dev)
    assert receive_order(sim.dev, pkg)["status"] == "pending"


def test_throttle_change_within_the_hour_is_refused_but_lift_is_not(sim):
    first = flows.build_order(sim.world, "throttle", "c1", level=50)
    assert receive_order(sim.dev, sim.pkg(first))["status"] == "applied"
    second = flows.build_order(sim.world, "throttle", "c1", level=20)
    assert receive_order(sim.dev, sim.pkg(second))["check"] == 9
    lift = flows.build_order(sim.world, "lift", "c1", lifts=envelope_id(first))
    assert receive_order(sim.dev, sim.pkg(lift))["status"] == "applied"
    assert sim.dev.enforcement()["state"] == "normal"


def envelope_id(msg):
    from harness.fsp.crypto import msg_id
    return msg_id(msg)


def test_device_outside_the_order_scope_refuses(sim):
    from harness.fsp.backends.software import SoftwareSecureElement
    w = sim.world
    outsider = w.add_device(SoftwareSecureElement(w.fw, w.clock), "c2")
    outsider.trust.cluster = w.clusters["c1"]
    order = flows.build_order(w, "throttle", "c1", level=50)
    pkg = flows.package(w, order, outsider)
    assert receive_order(outsider, pkg)["check"] == 8


def test_non_canonical_bytes_are_refused_at_check_1(sim):
    order = flows.build_order(sim.world, "throttle", "c1", level=50)
    raw = canon(order).replace(b'{"body"', b'{ "body"', 1)
    pkg = sim.pkg(order)
    pkg["order_bytes"] = raw
    assert receive_order(sim.dev, pkg)["check"] == 1


def test_order_with_a_float_level_is_refused_at_check_1(sim):
    order = flows.build_order(sim.world, "throttle", "c1", level=50, publish=False)
    order["body"]["level"] = 0.5
    assert receive_order(sim.dev, {"order": order})["check"] == 1
