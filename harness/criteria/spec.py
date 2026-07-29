"""spec.py -- the criterion: what would count, decided before the attempt.

The cage this design exists to open is a judge who writes the criterion, profits
from the verdict, and blocks re-checking. Three mechanical answers:

  1. A criterion is a hash-pinned object a third party can read and fork, not
     config that can drift in place. It is frozen.
  2. An edit records its parent hash and its reason, so amending a criterion
     after a miss is visible AS an amendment rather than indistinguishable from
     a bug fix. The lineage chains.
  3. Two shapes are refused reward eligibility outright, in the criterion itself
     rather than in a reviewer's judgement:
       - a non-conjunctive decision rule, because votes propose and proofs
         dispose, and a vote that can mint a reward is a preference economy
         wearing a verifier's coat;
       - a domain no deterministic checker disposes. An interpretive domain is
         refused by name, because a poem has no kernel and a general assessor
         slides into quality judgement by default.

The domain fence is checked before the decision rule, so an interpretive
criterion with an impeccable rule still reports the domain as the reason. The
more fundamental refusal should be the one a reader sees.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict, replace
from enum import Enum

DIRECTIONS = ("maximize", "minimize")


class CriterionError(ValueError):
    """A criterion that cannot be trusted to mean the same thing twice."""


class DecisionRule(str, Enum):
    CONJUNCTIVE = "CONJUNCTIVE"      # every check must pass
    DISJUNCTIVE = "DISJUNCTIVE"      # any check passing suffices
    MAJORITY = "MAJORITY"            # a vote
    WEIGHTED = "WEIGHTED"            # a weighted vote


class Domain(str, Enum):
    CONSTRUCTIVE = "CONSTRUCTIVE"    # a certificate a checker validates exactly
    FORMAL = "FORMAL"                # a proof a kernel validates
    COMPUTATIONAL = "COMPUTATIONAL"  # an execution test
    EMPIRICAL = "EMPIRICAL"          # a measurement: informs, never rewards here
    INTERPRETIVE = "INTERPRETIVE"    # aesthetic or interpretive: never rewarded


# Domains a deterministic checker can dispose. Reward eligibility stops here.
DISPOSITIVE_DOMAINS = frozenset({
    Domain.CONSTRUCTIVE, Domain.FORMAL, Domain.COMPUTATIONAL,
})

# Fields an amendment may never touch: changing them makes it a different
# criterion wearing the same name, which is the retcon the lineage exists to
# prevent.
IMMUTABLE_ON_AMEND = ("criterion_id", "family")


@dataclass(frozen=True)
class Criterion:
    criterion_id: str
    version: int
    family: str
    generator_id: str
    generator_version: int
    seed_range: tuple[int, int]          # half-open, ascending
    objective_direction: str
    objective_normalization: str
    reward_mapping: dict
    incumbent_source: str
    scope_bounds: dict
    decision_rule: DecisionRule
    domain: Domain
    license_id: str
    parent_sha256: str = ""
    change_reason: str = ""

    def __post_init__(self) -> None:
        lo, hi = self.seed_range
        if hi <= lo:
            raise CriterionError(
                "seed_range must be a non-empty ascending half-open interval, "
                f"got {self.seed_range}")
        if self.objective_direction not in DIRECTIONS:
            raise CriterionError(
                f"objective_direction must be one of {DIRECTIONS}, "
                f"got {self.objective_direction!r}")
        if not self.criterion_id or not self.family:
            raise CriterionError("criterion_id and family are required")

    def _preimage(self) -> str:
        """Canonical JSON: sorted keys, tight separators. Two honest parties must
        not disagree because a dict happened to be built in a different order."""
        d = asdict(self)
        d["seed_range"] = list(self.seed_range)
        d["decision_rule"] = self.decision_rule.value
        d["domain"] = self.domain.value
        return json.dumps(d, sort_keys=True, separators=(",", ":"))

    def sha256(self) -> str:
        return "sha256:" + hashlib.sha256(self._preimage().encode()).hexdigest()

    def amend(self, reason: str, **changes) -> Criterion:
        """The successor criterion. Append-only: the parent hash and the reason
        ride along, so an edit after a miss is visible as an edit."""
        if not reason.strip():
            raise CriterionError("an amendment must record why")
        for k in IMMUTABLE_ON_AMEND:
            if k in changes and changes[k] != getattr(self, k):
                raise CriterionError(f"{k} cannot change in an amendment")
            changes.pop(k, None)
        return replace(self, version=self.version + 1,
                       parent_sha256=self.sha256(), change_reason=reason,
                       **changes)

    def reward_eligible(self) -> tuple[bool, str]:
        """Whether a verdict under this criterion may become a training reward.

        Returns (ok, reason). The reason is a stable code, not prose, because a
        registry refusal has to be machine-readable.
        """
        if self.domain is Domain.INTERPRETIVE:
            return False, "INTERPRETIVE_DOMAIN"
        if self.domain not in DISPOSITIVE_DOMAINS:
            return False, "NON_DISPOSITIVE_DOMAIN"
        if self.decision_rule is not DecisionRule.CONJUNCTIVE:
            return False, "NON_CONJUNCTIVE_RULE"
        return True, "ok"

    def to_dict(self) -> dict:
        """The wire form, carrying its own hash so a reader who never runs this
        code can still check what they were handed."""
        d = asdict(self)
        d["seed_range"] = list(self.seed_range)
        d["decision_rule"] = self.decision_rule.value
        d["domain"] = self.domain.value
        d["criterion_sha256"] = self.sha256()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Criterion:
        d = dict(d)
        d.pop("criterion_sha256", None)
        d["seed_range"] = tuple(d["seed_range"])
        d["decision_rule"] = DecisionRule(d["decision_rule"])
        d["domain"] = Domain(d["domain"])
        return cls(**d)
