"""receipt_route.py -- which lane a result went through, bound into the receipt's claim.

Two lanes produce results. Lane A is a machine re-derivation against a checker.
Lane H is a person who re-derived and signs. A third outcome, UNVERIFIABLE, is
written when neither applies. Without a route on the receipt, a machine
re-derivation and a person's sign-off look the same to a reader.

A RoutedReceipt (flywheel.routed-receipt/v2) wraps an existing receipt and binds
its claim digest and the route into one `routed_claim_sha256`, which is what a
signature over a routed result covers. The receipt itself, its schema and its
claim digest are unchanged, so every existing reader and pin keeps working, and
a route cannot be relabeled after signing without changing the routed digest.
Its `scope` is the receipt's scope plus the lane's: what the route establishes.
v1 records, which named the list by its older name, still read with their limits.

Lane A has preconditions the block itself enforces: an independent checker
exists, the task needs no judgment, and the task's class is not on the
human-only list. A task cannot reach Lane A by leaving those inputs out.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .receipt_fields import ReceiptError, canonical, no_floats
from .scope import LEGACY_SCOPE_KEY, SCOPE_KEY

LANES = ("A", "H", "UNVERIFIABLE")
INPUT_KEYS = frozenset(("checker", "checker_id", "cost", "reversible", "judgment",
                        "telos_tier", "human_only_class"))
ESCALATION_KEYS = frozenset(("lane", "trigger", "at_attempt", "trace_head_sha256"))
UNVERIFIABLE_SCHEMA_V1 = "flywheel.unverifiable-record/v1"
UNVERIFIABLE_SCHEMA = "flywheel.unverifiable-record/v2"
ROUTED_SCHEMA_V1 = "flywheel.routed-receipt/v1"
ROUTED_SCHEMA = "flywheel.routed-receipt/v2"
ROUTED_SCHEMAS = (ROUTED_SCHEMA_V1, ROUTED_SCHEMA)
ROUTED_SIGNED_OVER = ("routed_claim_sha256",)
LANE_SCOPE = {
    "A": ("MACHINE_REDERIVED_AGAINST_CHECKER",),
    # Signer key roles arrive with lane separation; until then a Lane H route
    # records the signer it names, and the scope stops there.
    "H": ("PERSON_SIGNED_ROUTE_NAMES_SIGNER",),
    "UNVERIFIABLE": ("NO_LANE_APPLIED_REASON_RECORDED",),
}
# v1 records keep their sealed list.
LANE_LIMITS_V1 = {
    "A": ("NOT_PROVES_HUMAN_SIGN_OFF",),
    "H": ("NOT_PROVES_SIGNER_KEY_ROLE",),
    "UNVERIFIABLE": ("NOT_PROVES_ANY_CHECK_APPLIED",),
}


def _check_inputs(inputs: dict) -> None:
    if not isinstance(inputs, dict) or set(inputs) != INPUT_KEYS:
        raise ReceiptError(f"route inputs must have exactly {sorted(INPUT_KEYS)}")
    if inputs["checker"] not in ("yes", "partial", "no"):
        raise ReceiptError("route inputs.checker must be yes, partial or no")
    if inputs["cost"] not in ("low", "medium", "high"):
        raise ReceiptError("route inputs.cost must be low, medium or high")
    for key in ("reversible", "judgment", "human_only_class"):
        if type(inputs[key]) is not bool:
            raise ReceiptError(f"route inputs.{key} must be a bool")
    for key in ("checker_id", "telos_tier"):
        if type(inputs[key]) is not str:
            raise ReceiptError(f"route inputs.{key} must be a string")


def _check_escalation(esc) -> None:
    if esc is None:
        return
    if not isinstance(esc, dict) or set(esc) != ESCALATION_KEYS or esc["lane"] != "A":
        raise ReceiptError("escalated_from must name lane A, trigger, at_attempt, "
                           "trace_head_sha256")
    if type(esc["at_attempt"]) is not int:
        raise ReceiptError("escalated_from.at_attempt must be an int")


@dataclass(frozen=True)
class Route:
    lane: str
    policy_sha256: str
    policy_version: str
    inputs: dict
    declared_by: str
    reason: str
    escalated_from: dict | None = field(default=None)

    def __post_init__(self) -> None:
        if self.lane not in LANES:
            raise ReceiptError(f"route lane must be one of {LANES}")
        for name in ("policy_sha256", "policy_version", "declared_by", "reason"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ReceiptError(f"route {name} must be a non-empty string")
        _check_inputs(self.inputs)
        _check_escalation(self.escalated_from)
        no_floats(self.inputs, "route.inputs")
        if self.lane == "A":
            if self.inputs["checker"] != "yes":
                raise ReceiptError("lane A needs an independent checker")
            if self.inputs["judgment"] or self.inputs["human_only_class"]:
                raise ReceiptError("a judgment or human-only task cannot route to lane A")
            if self.escalated_from is not None:
                raise ReceiptError("an escalation leaves lane A; it cannot land there")

    def to_dict(self) -> dict:
        return {"lane": self.lane, "policy_sha256": self.policy_sha256,
                "policy_version": self.policy_version, "inputs": dict(self.inputs),
                "declared_by": self.declared_by, "reason": self.reason,
                "escalated_from": (dict(self.escalated_from)
                                   if self.escalated_from is not None else None)}

    @classmethod
    def from_dict(cls, d) -> "Route":
        if not isinstance(d, dict):
            raise ReceiptError("route must be an object")
        return cls(**d)

    def scope(self, schema: str = ROUTED_SCHEMA) -> tuple:
        table = LANE_LIMITS_V1 if schema == ROUTED_SCHEMA_V1 else LANE_SCOPE
        return table[self.lane]


def unverifiable_record(subject_sha256: str, route: Route, reason: str) -> dict:
    """The record written when no lane applies, so nothing passes silently."""
    if route.lane != "UNVERIFIABLE":
        raise ReceiptError("an unverifiable record needs an UNVERIFIABLE route")
    if not reason:
        raise ReceiptError("an unverifiable record needs a reason")
    body = {"schema": UNVERIFIABLE_SCHEMA, "subject_sha256": subject_sha256,
            "route": route.to_dict(), "reason": reason,
            "scope": list(route.scope())}
    body["record_sha256"] = "sha256:" + hashlib.sha256(canonical(body).encode()).hexdigest()
    return body


def _digest(body: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical(body).encode()).hexdigest()


@dataclass(frozen=True)
class RoutedReceipt:
    """A receipt plus the lane that produced it, digested together."""
    receipt: object                 # harness.receipt.Receipt
    route: Route
    schema: str = ROUTED_SCHEMA

    def __post_init__(self):
        if not isinstance(self.route, Route):
            raise ReceiptError("a routed receipt needs a Route")
        if not callable(getattr(self.receipt, "claim_sha256", None)):
            raise ReceiptError("a routed receipt wraps a Receipt")
        if self.schema not in ROUTED_SCHEMAS:
            raise ReceiptError("refusing a routed receipt with an unknown schema")

    def routed_claim_sha256(self) -> str:
        return _digest({"schema": self.schema,
                        "receipt_claim_sha256": self.receipt.claim_sha256(),
                        "route": self.route.to_dict()})

    def scope(self) -> list:
        return list(self.receipt.scope()) + list(self.route.scope(self.schema))

    def scope_key(self) -> str:
        return LEGACY_SCOPE_KEY if self.schema == ROUTED_SCHEMA_V1 else SCOPE_KEY

    def to_dict(self) -> dict:
        return {"schema": self.schema, "receipt": self.receipt.to_dict(),
                "route": self.route.to_dict(),
                "routed_claim_sha256": self.routed_claim_sha256(),
                self.scope_key(): self.scope()}

    @classmethod
    def from_dict(cls, d: dict) -> "RoutedReceipt":
        from .receipt import Receipt
        if not isinstance(d, dict) or d.get("schema") not in ROUTED_SCHEMAS:
            raise ReceiptError("refusing a routed receipt with an unknown schema")
        out = cls(Receipt.from_dict(d["receipt"]), Route.from_dict(d.get("route")),
                  schema=d["schema"])
        if d.get("routed_claim_sha256") != out.routed_claim_sha256():
            raise ReceiptError("routed_claim_sha256 does not match the receipt and route")
        key = out.scope_key()
        if (SCOPE_KEY if key == LEGACY_SCOPE_KEY else LEGACY_SCOPE_KEY) in d:
            raise ReceiptError(f"{out.schema} names its list {key!r}")
        if d.get(key) != out.scope():
            raise ReceiptError(f"{key} does not match the receipt and route")
        return out
