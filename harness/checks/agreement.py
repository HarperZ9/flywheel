"""agreement.py -- model agreement recorded beside a check, never as a verdict.

When several models were asked whether a result is right, their answers are
evidence worth keeping, but they are not a check: the measured false-accept
rate of majority agreement on the false-accept corpus is in
docs/features/checks.md. So agreement rides along as a signal with
`accepts: False` fixed, and `attach` never changes a receipt's verdict.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .receipt import CheckReceipt

SCHEMA = "flywheel.agreement-signal/v1"
NOTE = ("Model agreement is recorded as a signal. It never accepts a result; "
        "only the deterministic checks set the verdict.")


@dataclass(frozen=True)
class AgreementSignal:
    voters: tuple
    votes: tuple
    majority_says: str
    template_sha256: str
    accepts: bool = False
    schema: str = SCHEMA
    note: str = NOTE

    def to_dict(self) -> dict:
        return asdict(self)


def signal(voters: list, votes: list, template_sha256: str) -> AgreementSignal:
    """The panel's answers; majority_says is CORRECT, WRONG or SPLIT."""
    correct = sum(v == "CORRECT" for v in votes)
    wrong = sum(v == "WRONG" for v in votes)
    says = ("CORRECT" if correct * 2 > len(votes) else
            "WRONG" if wrong * 2 > len(votes) else "SPLIT")
    return AgreementSignal(voters=tuple(voters), votes=tuple(votes), majority_says=says,
                           template_sha256=template_sha256)


def attach(receipt: CheckReceipt, agreement: AgreementSignal) -> dict:
    """The receipt as a dict with the signal beside it; the verdict is the check's."""
    out = receipt.to_dict()
    out["signals"] = {"agreement": agreement.to_dict()}
    return out
