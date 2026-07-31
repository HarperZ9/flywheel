"""contest.py -- the refuted party does not decide what gets recorded.

Every other mechanism here protects a reader from the author. This one protects a
reader from the author's DISCRETION, which is a different problem and the one the
landscape has no answer for. A refutation the author can quietly decline to record
is worthless. And a grievance channel that hands the complainant the criterion as
well as the voice just rebuilds the cage on the other side of the bench, so this
module does not adjudicate either.

Four properties:

  1. A contest is signed with the CONTESTER's key. The author cannot mint one, and
     holding the contester's public key does not let them forge one.
  2. It names the exact claim digest it disputes, so it cannot be vaguely about
     everything and then be pointed at whatever is convenient later.
  3. It enters the SAME append-only ledger as any receipt. At that point declining
     to publish it is a rollback, which a kept tree head detects. Silence stops
     being a private decision.
  4. Resolution APPENDS. A resolved contest is not closed or deleted; the open
     count and the resolution breakdown are published series.

A contest is not a verdict. Two parties disagreeing is a recorded fact, and this
module refuses to turn it into a resolution.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum

from .ed25519_verify import verify as _ed_verify, Ed25519Error
from .receipt_fields import canonical


class ContestError(ValueError):
    """A contest that could not be recorded honestly."""


class ContestReason(str, Enum):
    CHECKER_IS_WRONG = "CHECKER_IS_WRONG"
    CRITERION_IS_WRONG = "CRITERION_IS_WRONG"
    NOVELTY_DISPUTED = "NOVELTY_DISPUTED"
    SCOPE_EXCEEDED = "SCOPE_EXCEEDED"
    CANNOT_REPRODUCE = "CANNOT_REPRODUCE"
    DENOMINATOR_DISPUTED = "DENOMINATOR_DISPUTED"
    ATTRIBUTION_DISPUTED = "ATTRIBUTION_DISPUTED"


class RESOLUTIONS(str, Enum):
    UPHELD = "UPHELD"                    # the contest was right
    REJECTED = "REJECTED"                # the contest was wrong
    PARTIAL = "PARTIAL"                  # right about some of it
    UNRESOLVED_BY_AGREEMENT = "UNRESOLVED_BY_AGREEMENT"
    WITHDRAWN = "WITHDRAWN"              # by the contester


@dataclass
class Contest:
    disputed_claim_sha256: str
    reason: ContestReason
    statement: str
    contester_key_id: str
    contester_public_key: str            # hex
    sig_hex: str = ""

    def __post_init__(self) -> None:
        if not self.disputed_claim_sha256:
            raise ContestError(
                "a contest must name the exact claim it disputes; a contest about "
                "everything can be pointed at whatever is convenient later")
        if not isinstance(self.reason, ContestReason):
            try:
                object.__setattr__(self, "reason", ContestReason(self.reason))
            except ValueError:
                raise ContestError(
                    f"reason must be a typed ContestReason, got {self.reason!r}")
        if not self.statement or not self.statement.strip():
            raise ContestError("a contest must say something substantive")
        if not self.contester_key_id:
            raise ContestError(
                "a contest needs an identified key, so it can be rotated and so a "
                "reader knows whether two contests share an author")

    def signing_payload(self) -> str:
        """Exactly what the contester signs. Every field that could change the
        meaning of the dispute is inside it."""
        return canonical({
            "schema": "flywheel.contest/v1",
            "disputed_claim_sha256": self.disputed_claim_sha256,
            "reason": self.reason.value,
            "statement": self.statement,
            "contester_key_id": self.contester_key_id,
            "contester_public_key": self.contester_public_key,
        })

    def contest_id(self) -> str:
        return "sha256:" + hashlib.sha256(
            self.signing_payload().encode()).hexdigest()

    def attach_signature(self, signature: bytes) -> "Contest":
        if not isinstance(signature, (bytes, bytearray)) or len(signature) != 64:
            raise ContestError("an ed25519 signature is 64 bytes")
        return Contest(self.disputed_claim_sha256, self.reason, self.statement,
                       self.contester_key_id, self.contester_public_key,
                       bytes(signature).hex())

    def verify(self) -> tuple[bool, str]:
        """(ok, reason). Checked against the contester's OWN key, so the author
        cannot mint a contest and cannot forge one either."""
        if not self.sig_hex:
            return False, "unsigned"
        try:
            ok = _ed_verify(bytes.fromhex(self.contester_public_key),
                            self.signing_payload().encode(),
                            bytes.fromhex(self.sig_hex))
        except (Ed25519Error, ValueError):
            return False, "bad_signature"
        return (True, "ok") if ok else (False, "bad_signature")

    def to_dict(self) -> dict:
        return {"schema": "flywheel.contest/v1",
                "contest_id": self.contest_id(),
                "disputed_claim_sha256": self.disputed_claim_sha256,
                "reason": self.reason.value, "statement": self.statement,
                "contester_key_id": self.contester_key_id,
                "contester_public_key": self.contester_public_key,
                "sig": self.sig_hex}

    @classmethod
    def from_dict(cls, d: dict) -> "Contest":
        return cls(d["disputed_claim_sha256"], ContestReason(d["reason"]),
                   d["statement"], d["contester_key_id"],
                   d["contester_public_key"], d.get("sig", ""))


def open_contest(ledger, contest: Contest) -> dict:
    """Record a contest in the same log as the receipt it disputes.

    Returns the ledger entry. Its `key` is the contest id, which is what `resolve`
    takes. The id is not duplicated at the top level on purpose: it already lives
    inside the signed contest, and a value repeated inside a hashed body is a
    value that can disagree with itself.
    """
    ok, why = contest.verify()
    if not ok:
        raise ContestError(
            f"refusing to record an unverifiable contest ({why}); an unsigned or "
            "tampered contest would let anyone put words in a stranger's mouth")
    disputed = contest.disputed_claim_sha256
    if not any(r.get("key") == disputed
               for r in ledger.records(ledger.KIND_RECEIPT)):
        raise ContestError(
            f"no receipt with claim {disputed[:22]}... is in this log; a contest "
            "against nothing cannot be resolved and would sit open forever")
    return ledger.append_record(ledger.KIND_CONTEST, contest.contest_id(),
                                {"contest": contest.to_dict()})


def resolve(ledger, contest_id: str, resolution, note: str) -> dict:
    """Record how a contest came out. Appends; never edits the contest."""
    if not isinstance(resolution, RESOLUTIONS):
        try:
            resolution = RESOLUTIONS(resolution)
        except ValueError:
            raise ContestError(
                f"resolution must be one of {[r.value for r in RESOLUTIONS]}, "
                f"got {resolution!r}")
    if not note or not note.strip():
        raise ContestError(
            "a resolution must say why; an unexplained resolution is the "
            "discretion this channel exists to remove")
    if not any(r.get("key") == contest_id
               for r in ledger.records(ledger.KIND_CONTEST)):
        raise ContestError(f"no contest {contest_id[:22]}... in this log")
    for r in ledger.records(ledger.KIND_RESOLUTION):
        if r.get("resolution", {}).get("contest_id") == contest_id:
            raise ContestError(
                f"contest {contest_id[:22]}... is already resolved as "
                f"{r['resolution']['resolution']}. A second resolution would "
                "overwrite the first, and the record is append-only.")
    return ledger.append_record(
        ledger.KIND_RESOLUTION, f"{contest_id}#resolution",
        {"resolution": {"contest_id": contest_id,
                        "resolution": resolution.value, "note": note}})


SERIES_LIMITS = [
    "NOT_PROVES_ABSENCE_OF_UNCONTESTED_ERRORS: zero open contests means nobody "
    "has objected in writing, which is not the same as nothing being wrong. An "
    "unread record attracts no contests at all.",
    "NOT_PROVES_CONTEST_COMPLETENESS: this counts contests that reached the log. "
    "A contest nobody could send, or chose not to, is invisible here.",
]


def contest_series(ledger) -> dict:
    """The published series: open count, resolved count, and the breakdown.

    Published rather than queried, because a count the author can choose not to
    surface is a count the author controls.
    """
    contests = ledger.records(ledger.KIND_CONTEST)
    resolutions = ledger.records(ledger.KIND_RESOLUTION)
    resolved_ids = {r["resolution"]["contest_id"] for r in resolutions}
    by_resolution: dict = {}
    for r in resolutions:
        key = r["resolution"]["resolution"]
        by_resolution[key] = by_resolution.get(key, 0) + 1
    open_ids = [c["key"] for c in contests if c["key"] not in resolved_ids]
    return {"schema": "flywheel.contest-series/v1",
            "total": len(contests), "open": len(open_ids),
            "resolved": len(resolved_ids), "open_ids": open_ids,
            "by_resolution": by_resolution,
            "does_not_prove": SERIES_LIMITS}
