"""Seat keys, the roster and votes (SPEC.md sections 2 and 5).

Seven seat keys sign as a plain list of attributable signatures, counted one
per key in the style of The Update Framework. The roster carries each
holder's published flags: nationality, whether the holder is a national of
a state that hosts frontier development, whether of a state with no
frontier development, whether of an economy that is not high-income, and the
holder's region. The regional rule (CHARTER.md Article 3(g) and (h)) caps the
seat-holders from any one region and requires that any K_ORDER seats span at
least MIN_SIGNER_REGIONS regions, so no bloc of neighbouring states fills a
quorum from one region. Region labels here are demo placeholders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from . import roster_change
from .crypto import Ed25519Signer, envelope, valid_signers


@dataclass
class Seat:
    index: int
    nationality: str
    frontier_host_state: bool
    non_frontier_state: bool
    non_high_income: bool
    region: str
    signer: Ed25519Signer = field(default_factory=Ed25519Signer)
    # The recovery key in separate custody (CHARTER.md Article 9(c) and (f)).
    recovery: Ed25519Signer = field(default_factory=Ed25519Signer)

    @property
    def key(self) -> str:
        return self.signer.public_hex()

    def public(self) -> dict:
        return {"key": self.key, "alg": self.signer.alg, "nationality": self.nationality,
                "frontier_host_state": self.frontier_host_state,
                "non_frontier_state": self.non_frontier_state,
                "non_high_income": self.non_high_income, "region": self.region,
                "recovery_key": self.recovery.public_hex()}


def default_seats() -> list[Seat]:
    """Seven demo seat-holders. Nationalities and regions are placeholders.

    Six regions, one of them holding two seats, so any four seats span at
    least three regions.
    """
    spec = [("A", True, False, False, "r1"), ("B", True, False, False, "r2"),
            ("C", False, True, True, "r3"), ("D", False, True, True, "r4"),
            ("E", False, False, False, "r5"), ("F", False, True, True, "r6"),
            ("G", False, False, True, "r1")]
    return [Seat(i, f"state-{n}", fh, nf, nhi, rg)
            for i, (n, fh, nf, nhi, rg) in enumerate(spec)]


def weakest_span(seats: list[dict], k: int) -> int:
    """The fewest regions any k seats of the roster can span."""
    if len(seats) < k:
        return 0
    return min(len({s.get("region") for s in group}) for group in combinations(seats, k))


def roster_violations(seats: list[dict], n_seats: int, max_per_region: int = 2,
                      min_signer_regions: int = 3, k_order: int = 4) -> list[str]:
    """The appendix's seat rules and the charter's regional rule, checked mechanically."""
    problems = []
    if len(seats) != n_seats:
        problems.append(f"{len(seats)} seats, expected {n_seats}")
    nations = [s["nationality"] for s in seats]
    if len(set(nations)) != len(nations):
        problems.append("more than one seat-holder of one nationality")
    if sum(s["frontier_host_state"] for s in seats) > 2:
        problems.append("more than two frontier-host seat-holders")
    both = [s["nationality"] for s in seats if s["frontier_host_state"] and s["non_frontier_state"]]
    if both:
        problems.append("a seat-holder flagged both frontier-host and non-frontier: " + ", ".join(both))
    # Reserved seats (CHARTER.md Article 3(c)): not high-income AND not frontier-host,
    # so a national of a frontier-host economy that is not high-income never fills one.
    reserved = [s for s in seats if s["non_high_income"] and not s["frontier_host_state"]]
    if len(reserved) < 2:
        problems.append("fewer than two reserved seat-holders from economies that are "
                        "not high-income and not frontier-host")
    if not any(s["non_frontier_state"] for s in seats):
        problems.append("no seat-holder from a state with no frontier development")
    if len({s["key"] for s in seats}) != len(seats):
        problems.append("a key appears twice")
    regions = [s.get("region") for s in seats]
    if not all(regions):
        problems.append("a seat-holder with no region")
        return problems
    if max(regions.count(r) for r in set(regions)) > max_per_region:
        problems.append(f"more than {max_per_region} seat-holders from one region")
    span = weakest_span(seats, k_order)
    if span < min_signer_regions:
        problems.append(f"{k_order} seats could sign from only {span} regions; "
                        f"at least {min_signer_regions} required")
    return problems


def make_roster(seats: list[Seat], epoch: int, signers: list[Seat]) -> dict:
    body = {"epoch": epoch, "seats": [s.public() for s in seats]}
    return envelope("roster", body, [s.signer for s in signers])


class Roster:
    """The roster in force, as a device or auditor holds it."""

    def __init__(self, msg: dict) -> None:
        self.msg = msg
        self.epoch = msg["body"]["epoch"]
        self.seats = {s["key"]: s for s in msg["body"]["seats"]}
        self.revoked = roster_change.revoked_keys(msg["body"])

    def signers(self, msg: dict) -> list[str]:
        """Seat keys whose signature verifies; a revoked key never counts."""
        return [k for k in valid_signers(msg) if k in self.seats and k not in self.revoked]

    def signer_regions(self, msg: dict) -> set[str]:
        return {self.seats[k].get("region") for k in self.signers(msg)}

    def non_frontier_signers(self, msg: dict) -> list[str]:
        # A seat flagged both ways counts as frontier-host: the device never lets an
        # inconsistent roster entry satisfy the halt-signer rule (check 3).
        return [k for k in self.signers(msg) if self.seats[k]["non_frontier_state"]
                and not self.seats[k]["frontier_host_state"]]

    def accepts_successor(self, new_msg: dict, k_order: int, n_seats: int,
                          min_signer_regions: int = 3,
                          max_per_region: int = 2, *, k_remove: int = 5) -> tuple[bool, str]:
        """A roster change needs K_ORDER current seats from enough regions and keeps the rules.

        Removal, revocation and re-enrolment follow roster_change.py and
        CHARTER.md Article 9: a dropped key needs K_REMOVE other seats and a
        logged cause; a revocation needs the holder's request, a proof or
        K_REMOVE; a re-enrolment needs the recovery key and no seat.
        """
        if new_msg.get("type") != "roster" or new_msg["body"]["epoch"] <= self.epoch:
            return False, "not a newer roster"
        if roster_change.classify(self, new_msg) == "ordinary":
            got = len(self.signers(new_msg))
            if got < k_order:
                return False, f"{got} of {k_order} current seats signed the roster change"
            span = len(self.signer_regions(new_msg))
            if span < min_signer_regions:
                return False, f"signers span {span} of {min_signer_regions} required regions"
        problems = roster_violations(new_msg["body"]["seats"], n_seats, max_per_region,
                                     min_signer_regions, k_order)
        if problems:
            return False, "; ".join(problems)
        why = roster_change.check(self, new_msg, k_remove=k_remove)
        return (False, why) if why is not None else (True, "ok")


def vote(seat: Seat, subject_fp: str, choice: str, criterion_id: str, reason_fp: str) -> dict:
    if choice not in ("yes", "no", "abstain"):
        raise ValueError("choice must be yes, no or abstain")
    body = {"subject_fp": subject_fp, "choice": choice, "criterion_id": criterion_id,
            "reason_fp": reason_fp, "seat": seat.key}
    return envelope("vote", body, [seat.signer])
