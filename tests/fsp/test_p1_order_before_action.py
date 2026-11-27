"""Red team against P1, order before action (SPEC.md sections 8.4 and 9).

Each test tries to get a device to act on an order that is not in LOGS_MIN
policy logs under K_WITNESS cosignatures, and asserts the refusal names the
right check.
"""

from __future__ import annotations

from harness.fsp import flows
from harness.fsp.canon import fingerprint
from harness.fsp.log import TransparencyLog
from harness.fsp.negative import weak_receive
from harness.fsp.recheck import daily_recheck
from harness.fsp.shim import receive_order, tick


def _throttle(sim, **kw):
    kw.setdefault("level", 50)
    return flows.build_order(sim.world, "throttle", "c1", **kw)


def test_valid_throttle_applies_and_is_backed_by_a_logged_order(sim):
    res = receive_order(sim.dev, sim.pkg(_throttle(sim)))
    assert res["status"] == "applied"
    assert sim.dev.enforcement()["state"] == "throttled"
    sim.world.deliver(sim.dev)
    rows = daily_recheck(sim.world)
    assert [r["verdict"] for r in rows] == ["MATCH"]


def test_unlogged_order_is_refused_at_check_4(sim):
    res = receive_order(sim.dev, sim.pkg(_throttle(sim, publish=False)))
    assert (res["status"], res["check"]) == ("refused", 4)
    assert sim.dev.enforcement()["state"] == "normal"


def test_order_in_only_one_log_is_refused(sim):
    order = _throttle(sim, logs=[sim.world.logs[0]])
    res = receive_order(sim.dev, sim.pkg(order))
    assert res["check"] == 4 and "1 of 2" in res["reason"]


def test_rogue_log_outside_the_policy_does_not_count(sim):
    w = sim.world
    rogue = [TransparencyLog(f"log-{j}", "JX", w.clock) for j in range(2)]  # same ids, new keys
    order = _throttle(sim, publish=False)
    pkg = sim.pkg(order)
    for log in rogue:
        log.submit(order)
        idx = log.find(fingerprint("entry", order))
        cp = log.checkpoint()
        pkg["bundles"].append({"log_id": log.log_id, "index": idx, "leaf": log.leaves[idx],
                               "checkpoint": cp, "cosigs": [], "consistency": [],
                               "inclusion": log.inclusion(idx, cp["body"]["size"]),
                               "from_size": 0})
    res = receive_order(sim.dev, pkg)
    assert res["check"] == 4 and "not signed by its log key" in res["reason"]


def test_too_few_witness_cosignatures_is_check_5(sim):
    pkg = sim.pkg(_throttle(sim))
    for b in pkg["bundles"]:
        b["cosigs"] = b["cosigs"][:2]
    assert receive_order(sim.dev, pkg)["check"] == 5


def test_one_witness_cosigning_three_times_counts_once(sim):
    pkg = sim.pkg(_throttle(sim))
    for b in pkg["bundles"]:
        b["cosigs"] = [b["cosigs"][0]] * 5
    assert receive_order(sim.dev, pkg)["check"] == 5


def test_forged_cosignature_is_not_counted(sim):
    pkg = sim.pkg(_throttle(sim))
    for b in pkg["bundles"]:
        for cs in b["cosigs"][:3]:
            cs["sig"] = "00" * 64
    assert receive_order(sim.dev, pkg)["check"] == 5


def test_leaf_swapped_for_another_message_is_refused(sim):
    order = _throttle(sim)
    other = _throttle(sim, level=10)
    pkg_other = sim.pkg(other)
    pkg = sim.pkg(order)
    pkg["bundles"] = pkg_other["bundles"]
    res = receive_order(sim.dev, pkg)
    assert res["check"] == 4 and "different message" in res["reason"]


def test_tampered_inclusion_proof_is_refused(sim):
    pkg = sim.pkg(_throttle(sim))
    for b in pkg["bundles"]:
        b["inclusion"][0] = "11" * 32
    assert receive_order(sim.dev, pkg)["check"] == 4


def test_equivocating_log_gets_no_witness_cosignatures(sim):
    """A private branch holding a secret order draws no honest cosignature (check 5)."""
    from harness.fsp.witness import Refused
    w = sim.world
    log = w.logs[0]
    twin = log.fork()
    order = _throttle(sim, publish=False)
    twin.submit(order)
    log.submit(_throttle(sim, level=90, publish=False))
    w.cosign()
    cp, cosigs, reasons = twin.checkpoint(), [], []
    for wit in w.witnesses:
        try:
            cosigs.append(wit.cosign(cp, log.key, []))
        except Refused as exc:
            reasons.append(exc.reason)
    assert cosigs == [] and set(reasons) == {"split view"}
    idx = twin.find(fingerprint("entry", order))
    size = cp["body"]["size"]
    bundle = {"log_id": log.log_id, "index": idx, "leaf": twin.leaves[idx], "checkpoint": cp,
              "cosigs": cosigs, "inclusion": twin.inclusion(idx, size), "consistency": [],
              "from_size": 0}
    res = receive_order(sim.dev, {**sim.pkg(order), "bundles": [bundle]})
    assert res["check"] == 5


def test_witness_refuses_split_view_and_the_pair_is_a_proof(sim):
    from harness.fsp.witness import Refused, is_split_view_proof
    w = sim.world
    log = w.logs[1]
    twin = log.fork()
    log.submit(_throttle(sim, publish=False))
    twin.submit(_throttle(sim, level=10, publish=False))
    witness = w.witnesses[0]
    old = witness.latest[log.log_id]["body"]["size"]
    witness.cosign(log.checkpoint(), log.key, log.consistency(old, log.size()))
    try:
        witness.cosign(twin.checkpoint(), log.key, [])
        raise AssertionError("witness cosigned a split view")
    except Refused as exc:
        assert exc.reason == "split view"
        assert is_split_view_proof(exc.proof["a"], exc.proof["b"], log.key)


def test_device_never_accepts_a_smaller_checkpoint(sim):
    order = _throttle(sim)
    stale = sim.pkg(order)
    for level in (70, 60):  # later entries move the device's view forward
        receive_order(sim.dev, sim.pkg(_throttle(sim, level=level)))
    res = receive_order(sim.dev, stale)
    assert res["check"] == 6 and "not consistent" in res["reason"]


def test_negative_control_weak_shim_is_caught_by_the_recheck(sim):
    """A shim that skips checks 4 to 6 accepts an unlogged order; the recheck reads DRIFT."""
    res = weak_receive(sim.dev, sim.pkg(_throttle(sim, publish=False)))
    assert res["status"] == "applied"
    sim.world.deliver(sim.dev)
    verdicts = [r["verdict"] for r in daily_recheck(sim.world)]
    assert "DRIFT" in verdicts


def test_pending_order_acts_only_after_effective_time(sim):
    order = _throttle(sim, effective_ms=sim.world.now_ms() + 60_000)
    assert receive_order(sim.dev, sim.pkg(order))["status"] == "pending"
    assert tick(sim.dev) == []
    sim.advance(61)
    assert tick(sim.dev)[0]["status"] == "applied"
