"""The route on receipts (flywheel.routed-receipt/v2): which lane produced a result.

Success criteria:
- a routed receipt round-trips through its wire form, and the routed digest
  binds both the receipt's claim digest and the route;
- false-success control: relabeling a lane A result as lane H on the wire is
  refused (digest mismatch), and recomputing the digest after the relabel gives
  a different routed_claim_sha256, so a signature over the original fails;
- the wrapped receipt's own claim digest is unchanged by routing;
- lane A adds MACHINE_REDERIVED_AGAINST_CHECKER; an UNVERIFIABLE record adds
  NO_LANE_APPLIED_REASON_RECORDED;
- lane A is refused without an independent checker, for a judgment task, for a
  human-only class, and as the target of an escalation; inputs are exact.
"""
from __future__ import annotations

import pytest

from harness.receipt_fields import ReceiptError
from harness.receipt_route import (ROUTED_SIGNED_OVER, Route, RoutedReceipt,
                                   unverifiable_record)
from tests.receipt_factories import receipt

INPUTS = {"checker": "yes", "checker_id": "pytest:hidden", "cost": "low",
          "reversible": True, "judgment": False, "telos_tier": "T2",
          "human_only_class": False}


def route(lane="A", **kw):
    base = dict(lane=lane, policy_sha256="sha256:" + "1" * 64, policy_version="1",
                inputs=dict(INPUTS), declared_by="owner:test", reason="checker exists")
    base.update(kw)
    return Route(**base)


def test_round_trip():
    r = RoutedReceipt(receipt(), route())
    back = RoutedReceipt.from_dict(r.to_dict())
    assert back.routed_claim_sha256() == r.routed_claim_sha256()
    assert ROUTED_SIGNED_OVER == ("routed_claim_sha256",)


def test_routed_digest_binds_route_and_receipt():
    rec = receipt()
    a, h = RoutedReceipt(rec, route("A")), RoutedReceipt(rec, route("H"))
    assert a.routed_claim_sha256() != h.routed_claim_sha256()
    assert a.receipt.claim_sha256() == rec.claim_sha256()
    other = RoutedReceipt(receipt(objective="20"), route("A"))
    assert other.routed_claim_sha256() != a.routed_claim_sha256()


def test_control_relabeling_a_machine_result_as_signed_is_caught():
    a = RoutedReceipt(receipt(), route("A"))
    wire = a.to_dict()
    wire["route"]["lane"] = "H"
    with pytest.raises(ReceiptError):
        RoutedReceipt.from_dict(wire)
    relabeled = RoutedReceipt(receipt(), route("H"))
    assert relabeled.routed_claim_sha256() != a.routed_claim_sha256()


def test_lane_scope_is_derived():
    a = RoutedReceipt(receipt(), route("A")).scope()
    h = RoutedReceipt(receipt(), route("H")).scope()
    lane_a = "MACHINE_REDERIVED_AGAINST_CHECKER"
    assert lane_a in a and lane_a not in h
    assert a[:-1] == receipt().scope()


def test_a_v1_routed_receipt_still_reads_with_its_limits():
    from harness.receipt_route import ROUTED_SCHEMA_V1
    from harness.scope import LEGACY_SCOPE_KEY
    old = RoutedReceipt(receipt(), route("A"), schema=ROUTED_SCHEMA_V1)
    wire = old.to_dict()
    assert wire[LEGACY_SCOPE_KEY][-1] == "NOT_PROVES_HUMAN_SIGN_OFF"
    back = RoutedReceipt.from_dict(wire)
    assert back.routed_claim_sha256() == old.routed_claim_sha256()
    with pytest.raises(ReceiptError):
        RoutedReceipt.from_dict(dict(wire, scope=wire[LEGACY_SCOPE_KEY]))


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


def test_wire_refuses_unknown_schema_and_edited_limits():
    wire = RoutedReceipt(receipt(), route()).to_dict()
    with pytest.raises(ReceiptError):
        RoutedReceipt.from_dict(dict(wire, schema="flywheel.routed-receipt/v0"))
    with pytest.raises(ReceiptError):
        RoutedReceipt.from_dict(dict(wire, scope=wire["scope"][:-1]))


def test_unverifiable_record():
    rec = unverifiable_record("sha256:" + "d" * 64, route("UNVERIFIABLE", inputs=dict(
        INPUTS, checker="no")), "no checker and no signer")
    assert rec["scope"] == ["NO_LANE_APPLIED_REASON_RECORDED"]
    assert rec["schema"] == "flywheel.unverifiable-record/v2"
    assert rec["record_sha256"].startswith("sha256:")
    with pytest.raises(ReceiptError):
        unverifiable_record("sha256:x", route("H"), "reason")
