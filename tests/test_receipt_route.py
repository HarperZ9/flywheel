"""The route block on receipts (schema v5): which lane produced a result.

Success criteria:
- a v5 receipt round-trips through its wire form with the route intact, and the
  route is inside claim_sha256 but not subject_sha256;
- false-success control: relabeling a lane A receipt as lane H on the wire
  changes claim_sha256, so a signature over the original no longer covers it;
- a lane A receipt says NOT_PROVES_HUMAN_SIGN_OFF; an UNVERIFIABLE record says
  NOT_PROVES_ANY_CHECK_APPLIED;
- lane A is refused without an independent checker, for a judgment task, for a
  human-only class, and as the target of an escalation;
- v5 without a route, and v4 with one, are refused in both directions;
- v4 receipts keep their claim digest (no route field appears).
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from harness.receipt import ROUTED_SCHEMA, SCHEMA, Receipt
from harness.receipt_fields import ReceiptError
from harness.receipt_route import Route, unverifiable_record
from tests.receipt_factories import receipt

INPUTS = {"checker": "yes", "checker_id": "pytest:hidden", "cost": "low",
          "reversible": True, "judgment": False, "telos_tier": "T2",
          "human_only_class": False}


def route(lane="A", **kw):
    base = dict(lane=lane, policy_sha256="sha256:" + "1" * 64, policy_version="1",
                inputs=dict(INPUTS), declared_by="owner:test", reason="checker exists")
    base.update(kw)
    return Route(**base)


def routed(lane="A", **kw):
    return receipt(schema=ROUTED_SCHEMA, route=route(lane, **kw))


def test_v5_round_trips_with_the_route():
    r = routed()
    back = Receipt.from_dict(r.to_dict())
    assert back.route == r.route
    assert back.claim_sha256() == r.claim_sha256()


def test_route_is_in_the_claim_not_the_subject():
    a, h = routed("A"), routed("H")
    assert a.subject_sha256() == h.subject_sha256()
    assert a.claim_sha256() != h.claim_sha256()


def test_control_relabeling_a_machine_result_as_signed_breaks_the_claim():
    a = routed("A")
    wire = a.to_dict()
    wire["route"]["lane"] = "H"
    wire["does_not_prove"] = [x if x != "NOT_PROVES_HUMAN_SIGN_OFF" else "NOT_PROVES_SIGNER_KEY_ROLE"
                              for x in wire["does_not_prove"]]
    forged = Receipt.from_dict(wire)
    assert forged.claim_sha256() != a.claim_sha256()


def test_lane_limits_are_derived():
    assert "NOT_PROVES_HUMAN_SIGN_OFF" in routed("A").does_not_prove()
    assert "NOT_PROVES_HUMAN_SIGN_OFF" not in routed("H").does_not_prove()


@pytest.mark.parametrize("change", [{"checker": "partial"}, {"checker": "no"},
                                    {"judgment": True}, {"human_only_class": True}])
def test_lane_a_preconditions(change):
    with pytest.raises(ReceiptError):
        route("A", inputs=dict(INPUTS, **change))
    assert route("H", inputs=dict(INPUTS, **change)).lane == "H"


def test_escalation_cannot_land_in_lane_a():
    esc = {"lane": "A", "trigger": "budget", "at_attempt": 3, "trace_head_sha256": "x"}
    assert route("H", escalated_from=esc).escalated_from == esc
    with pytest.raises(ReceiptError):
        route("A", escalated_from=esc)


@pytest.mark.parametrize("inputs", [dict(INPUTS, extra=1),
                                    {k: v for k, v in INPUTS.items() if k != "judgment"},
                                    dict(INPUTS, reversible="yes"), dict(INPUTS, cost="free")])
def test_inputs_are_exact(inputs):
    with pytest.raises(ReceiptError):
        route("H", inputs=inputs)


def test_schema_and_route_must_agree():
    with pytest.raises(ReceiptError):
        receipt(schema=ROUTED_SCHEMA)
    with pytest.raises(ReceiptError):
        receipt(schema=SCHEMA, route=route())
    wire = receipt().to_dict()
    wire["route"] = route().to_dict()
    with pytest.raises(ReceiptError):
        Receipt.from_dict(wire)


def test_v4_claim_has_no_route_field():
    r = receipt()
    assert "route" not in r.to_dict()
    assert replace(r).claim_sha256() == r.claim_sha256()


def test_unverifiable_record():
    rec = unverifiable_record("sha256:" + "d" * 64, route("UNVERIFIABLE", inputs=dict(
        INPUTS, checker="no")), "no checker and no signer")
    assert rec["does_not_prove"] == ["NOT_PROVES_ANY_CHECK_APPLIED"]
    assert rec["record_sha256"].startswith("sha256:")
    with pytest.raises(ReceiptError):
        unverifiable_record("sha256:x", route("H"), "reason")
