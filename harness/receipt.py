"""receipt.py -- the record a stranger re-derives without trusting the author.

Field types and their validation live in receipt_fields.py; this module composes
fields into a claim and digests it. Two properties are the whole point:

1. TWO DIGESTS, because one cannot do both jobs.
   `subject_sha256` answers what was checked and stays VERDICT-FREE, so two
   verifiers who reach opposite conclusions about the same candidate still produce
   the same subject id and their disagreement can be located rather than merely
   noticed.
   `claim_sha256` binds the verdict, the objective, and the raw oracle output. It
   is what a signature covers and what a stranger re-derives.

2. `does_not_prove` is MECHANICALLY DERIVED from the receipt's own contents and is
   never empty. A receipt that reports only its proof is how a true explanation
   becomes a fake passport, and deriving it means nobody has to remember.

`SIGNED_OVER` is fixed here, per schema version, and is deliberately NOT a receipt
field. If a receipt could declare what its own signature covers, an attacker would
declare the narrowest possible coverage.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .receipt_fields import (
    Denominator, EvidenceKind, Tier, ReceiptError, canonical, no_floats,
)
from .verdict import Verdict, Attribution

SCHEMA = "flywheel.receipt/v2"

# What a signature covers. Fixed in code, never read from a receipt. This is a
# security property, not a configuration choice.
SIGNED_OVER = ("claim_sha256",)


@dataclass(frozen=True)
class Receipt:
    # --- subject: what was checked -------------------------------------------
    criterion_id: str
    criterion_version: int
    criterion_sha256: str
    family: str
    family_instance_id: str
    generator_id: str
    generator_seed: int
    candidate_sha256: str
    prompt_hash: str
    checker_module: str
    checker_source_sha256: str
    executes_candidate_code: bool
    oracle_qa_card_hash: str
    held_out_agreement: str                 # AGREE | DISAGREE | NOT_RUN
    evidence_kind: EvidenceKind
    tier: Tier
    # --- claim: what was concluded -------------------------------------------
    verdict: Verdict
    attribution: Attribution
    objective: str
    incumbent_objective: str
    incumbent_source: str
    coverage: dict
    raw_stdout_sha256: str
    analysis_script_sha256: str
    denominator: Denominator
    model_ref: str
    base_weights_digest: str
    harness_version: str
    # --- optional ------------------------------------------------------------
    input_tier_multiset: tuple = ()
    novelty_verdict: str = "UNKNOWN"         # REDISCOVERY | NOT_FOUND_IN_CORPUS
    unverifiable_reason: str = ""
    undecided_reason: str = ""
    extra_does_not_prove: tuple = ()

    def __post_init__(self) -> None:
        if self.denominator is None:
            raise ReceiptError("a receipt without a denominator is unpriceable")
        if not isinstance(self.denominator, Denominator):
            raise ReceiptError("denominator must be a Denominator")
        for name in ("objective", "incumbent_objective", "coverage",
                     "input_tier_multiset"):
            no_floats(getattr(self, name), name)

    # --- digests -------------------------------------------------------------

    def _subject(self) -> dict:
        return {
            "criterion_id": self.criterion_id,
            "criterion_version": self.criterion_version,
            "criterion_sha256": self.criterion_sha256,
            "family": self.family,
            "family_instance_id": self.family_instance_id,
            "generator_id": self.generator_id,
            "generator_seed": self.generator_seed,
            "candidate_sha256": self.candidate_sha256,
            "prompt_hash": self.prompt_hash,
            "checker_module": self.checker_module,
            "checker_source_sha256": self.checker_source_sha256,
            "executes_candidate_code": self.executes_candidate_code,
            "evidence_kind": self.evidence_kind.value,
            "tier": self.tier.value,
            "input_tier_multiset": list(self.input_tier_multiset),
            "schema": SCHEMA,
        }

    def _claim(self) -> dict:
        d = dict(self._subject())
        d.update({
            "verdict": self.verdict.value,
            "attribution": self.attribution.value,
            "objective": self.objective,
            "incumbent_objective": self.incumbent_objective,
            "incumbent_source": self.incumbent_source,
            "coverage": self.coverage,
            "raw_stdout_sha256": self.raw_stdout_sha256,
            "analysis_script_sha256": self.analysis_script_sha256,
            "oracle_qa_card_hash": self.oracle_qa_card_hash,
            "held_out_agreement": self.held_out_agreement,
            "denominator": self.denominator.to_dict(),
            "model_ref": self.model_ref,
            "base_weights_digest": self.base_weights_digest,
            "novelty_verdict": self.novelty_verdict,
            "unverifiable_reason": self.unverifiable_reason,
            "undecided_reason": self.undecided_reason,
        })
        return d

    def subject_sha256(self) -> str:
        """What was checked. Verdict-free on purpose."""
        return "sha256:" + hashlib.sha256(
            canonical(self._subject()).encode()).hexdigest()

    def claim_sha256(self) -> str:
        """What was concluded. This is what a signature covers."""
        return "sha256:" + hashlib.sha256(
            canonical(self._claim()).encode()).hexdigest()

    # --- the honesty field ---------------------------------------------------

    def does_not_prove(self) -> list[str]:
        """Derived from the receipt's own contents, so nobody has to remember."""
        out = ["NOT_PROVES_PUBLICATION_COMPLETENESS"]
        if not self.oracle_qa_card_hash:
            out.append("NOT_PROVES_VERIFIER_SOUNDNESS")
        if self.held_out_agreement != "AGREE":
            out.append("NOT_PROVES_RESISTANCE_TO_ORACLE_GAMING")
        if not self.coverage.get("predicate_exact", False):
            out.append("NOT_PROVES_EXACTNESS")
        if not self.coverage.get("search_space_enumerated", False):
            out.append("NOT_PROVES_COMPLETE_ENUMERATION")
        if self.novelty_verdict == "UNKNOWN":
            out.append("NOT_PROVES_NOVELTY")
        if self.executes_candidate_code:
            out.append("NOT_PROVES_CONTAINMENT")
        if not self.base_weights_digest:
            out.append("NOT_PROVES_WHICH_WEIGHTS")
        if self.denominator.filter_is_learned:
            out.append("NOT_PROVES_UNBIASED_TASK_SELECTION")
        if self.input_tier_multiset:
            out.append("TIER_LIMITED_BY_INPUT")
        out.extend(self.extra_does_not_prove)
        return out

    # --- wire form -----------------------------------------------------------

    def to_dict(self) -> dict:
        d = dict(self._claim())
        d["subject_sha256"] = self.subject_sha256()
        d["claim_sha256"] = self.claim_sha256()
        d["does_not_prove"] = self.does_not_prove()
        d["harness_version"] = self.harness_version
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Receipt:
        den = d["denominator"]
        return cls(
            criterion_id=d["criterion_id"],
            criterion_version=d["criterion_version"],
            criterion_sha256=d["criterion_sha256"],
            family=d["family"], family_instance_id=d["family_instance_id"],
            generator_id=d["generator_id"], generator_seed=d["generator_seed"],
            candidate_sha256=d["candidate_sha256"], prompt_hash=d["prompt_hash"],
            checker_module=d["checker_module"],
            checker_source_sha256=d["checker_source_sha256"],
            executes_candidate_code=d["executes_candidate_code"],
            oracle_qa_card_hash=d["oracle_qa_card_hash"],
            held_out_agreement=d["held_out_agreement"],
            evidence_kind=EvidenceKind(d["evidence_kind"]),
            tier=Tier(d["tier"]),
            verdict=Verdict(d["verdict"]),
            attribution=Attribution(d["attribution"]),
            objective=d["objective"],
            incumbent_objective=d["incumbent_objective"],
            incumbent_source=d["incumbent_source"],
            coverage=d["coverage"], raw_stdout_sha256=d["raw_stdout_sha256"],
            analysis_script_sha256=d["analysis_script_sha256"],
            denominator=Denominator(**den),
            model_ref=d["model_ref"],
            base_weights_digest=d["base_weights_digest"],
            harness_version=d["harness_version"],
            input_tier_multiset=tuple(d.get("input_tier_multiset", ())),
            novelty_verdict=d.get("novelty_verdict", "UNKNOWN"),
            unverifiable_reason=d.get("unverifiable_reason", ""),
            undecided_reason=d.get("undecided_reason", ""))
