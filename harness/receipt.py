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
2. `scope` is MECHANICALLY DERIVED from the receipt's own contents and is never
   empty: codes for the properties its fields establish (receipt_scope.py). A
   reader sees exactly what the receipt covers, and deriving it means nobody has
   to remember. v3 and v4 receipts carry the older list of `NOT_PROVES_*`
   codes and are read with that vocabulary.
`SIGNED_OVER` is fixed here, per schema version, and is deliberately NOT a receipt
field. If a receipt could declare what its own signature covers, an attacker would
declare the narrowest possible coverage.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

from .receipt_scope import derived_scope, legacy_limits
from .receipt_fields import (
    Budget, Denominator, EvidenceKind, GradedScore, Tier, ReceiptError,
    canonical, no_floats,
)
from .scope import LEGACY_SCOPE_KEY, SCOPE_KEY
from .verdict import Verdict, Attribution

LEGACY_SCHEMA = "flywheel.receipt/v3"
# v4 is the first schema whose claim preimage binds oracle-specific limits.
# v5 names that list `scope` and says what the receipt covers. v3 and v4 remain
# readable with their original preimage and vocabulary; schema names never get
# a second interpretation after publication.
V4_SCHEMA = "flywheel.receipt/v4"
SCHEMA = "flywheel.receipt/v5"
SUPPORTED_SCHEMAS = frozenset((LEGACY_SCHEMA, V4_SCHEMA, SCHEMA))
_LEGACY_VOCABULARY = frozenset((LEGACY_SCHEMA, V4_SCHEMA))
_EXTRA_KEY = {V4_SCHEMA: "extra_" + LEGACY_SCOPE_KEY, SCHEMA: "extra_scope"}

# What a signature covers. Fixed in code, never read from a receipt. This is a
# security property, not a configuration choice.
SIGNED_OVER = ("claim_sha256",)


def subject_fields(*, criterion_id, criterion_version, criterion_sha256, family,
                   family_instance_id, generator_id, generator_seed,
                   candidate_sha256, prompt_hash, checker_module,
                   checker_source_sha256, executes_candidate_code, evidence_kind,
                   tier, input_tier_multiset=(), schema=SCHEMA) -> dict:
    """What was checked, as a plain mapping. THE one definition of the subject.

    `Receipt._subject` calls this rather than restating it, so the standalone
    digest below cannot drift from the one a receipt reports. Two copies of this
    dict would eventually disagree, and the disagreement would look like a real
    verification failure.
    """
    return {
        "criterion_id": criterion_id, "criterion_version": criterion_version,
        "criterion_sha256": criterion_sha256, "family": family,
        "family_instance_id": family_instance_id, "generator_id": generator_id,
        "generator_seed": generator_seed, "candidate_sha256": candidate_sha256,
        "prompt_hash": prompt_hash, "checker_module": checker_module,
        "checker_source_sha256": checker_source_sha256,
        "executes_candidate_code": executes_candidate_code,
        "evidence_kind": getattr(evidence_kind, "value", evidence_kind),
        "tier": getattr(tier, "value", tier),
        "input_tier_multiset": list(input_tier_multiset), "schema": schema,
    }


def subject_digest(**fields) -> str:
    """The subject digest without a claim wrapped around it.

    The primary endpoint asserts one SUBJECT per certificate body and reads
    nothing on the claim side. Demanding a denominator and a budget just to read
    that digest would force a caller to invent numbers it does not have, and
    invented numbers inside a receipt are worse than no receipt at all.
    """
    return "sha256:" + hashlib.sha256(
        canonical(subject_fields(**fields)).encode()).hexdigest()


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
    budget: Budget
    model_ref: str
    base_weights_digest: str
    harness_version: str
    # --- optional ------------------------------------------------------------
    # Present only when the oracle grades rather than binarises. It travels
    # ALONGSIDE the verdict and never stands in for it.
    graded_score: GradedScore | None = None
    input_tier_multiset: tuple = ()
    novelty_verdict: str = "UNKNOWN"         # REDISCOVERY | NOT_FOUND_IN_CORPUS
    unverifiable_reason: str = ""
    undecided_reason: str = ""
    extra_scope: tuple = ()
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        if self.denominator is None:
            raise ReceiptError("a receipt without a denominator is unpriceable")
        if not isinstance(self.denominator, Denominator):
            raise ReceiptError("denominator must be a Denominator")
        if not isinstance(self.budget, Budget):
            raise ReceiptError(
                "budget must be a Budget; use Budget.undeclared() to state that "
                "no ceiling was recorded, so an absence cannot pass as a zero")
        if self.graded_score is not None and not isinstance(self.graded_score,
                                                            GradedScore):
            raise ReceiptError("graded_score must be a GradedScore or None")
        if self.schema not in SUPPORTED_SCHEMAS:
            raise ReceiptError(f"unsupported receipt schema {self.schema!r}")
        for name in ("objective", "incumbent_objective", "coverage",
                     "input_tier_multiset"):
            no_floats(getattr(self, name), name)

    # --- digests -------------------------------------------------------------

    def _subject(self) -> dict:
        return subject_fields(
            criterion_id=self.criterion_id,
            criterion_version=self.criterion_version,
            criterion_sha256=self.criterion_sha256, family=self.family,
            family_instance_id=self.family_instance_id,
            generator_id=self.generator_id, generator_seed=self.generator_seed,
            candidate_sha256=self.candidate_sha256, prompt_hash=self.prompt_hash,
            checker_module=self.checker_module,
            checker_source_sha256=self.checker_source_sha256,
            executes_candidate_code=self.executes_candidate_code,
            evidence_kind=self.evidence_kind, tier=self.tier,
            input_tier_multiset=self.input_tier_multiset, schema=self.schema)

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
            "budget": self.budget.to_dict(),
            "graded_score": (self.graded_score.to_dict()
                             if self.graded_score is not None else None),
            "model_ref": self.model_ref,
            "base_weights_digest": self.base_weights_digest,
            "novelty_verdict": self.novelty_verdict,
            "unverifiable_reason": self.unverifiable_reason,
            "undecided_reason": self.undecided_reason,
        })
        if self.schema in _EXTRA_KEY:
            d[_EXTRA_KEY[self.schema]] = list(self.extra_scope)
        return d

    def subject_sha256(self) -> str:
        """What was checked. Verdict-free on purpose."""
        return "sha256:" + hashlib.sha256(
            canonical(self._subject()).encode()).hexdigest()

    def claim_sha256(self) -> str:
        """What was concluded. This is what a signature covers."""
        return "sha256:" + hashlib.sha256(
            canonical(self._claim()).encode()).hexdigest()

    # --- scope ----------------------------------------------------------------

    def scope(self) -> list[str]:
        """Derived from the receipt's own contents, so nobody has to remember.

        v5 lists what the receipt covers; v3 and v4 keep the list they sealed."""
        if self.schema in _LEGACY_VOCABULARY:
            return legacy_limits(self)
        return derived_scope(self)

    def scope_key(self) -> str:
        """The wire name of the scope list for this receipt's schema."""
        return LEGACY_SCOPE_KEY if self.schema in _LEGACY_VOCABULARY else SCOPE_KEY

    # --- wire form -----------------------------------------------------------

    def to_dict(self) -> dict:
        d = dict(self._claim())
        d["subject_sha256"] = self.subject_sha256()
        d["claim_sha256"] = self.claim_sha256()
        d[self.scope_key()] = self.scope()
        d["harness_version"] = self.harness_version
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Receipt:
        # A reader that ignores the version silently reinterprets fields whose
        # meaning changed between them, and then reports a claim digest over a
        # different set of fields than the writer covered.
        schema = d.get("schema")
        if schema not in SUPPORTED_SCHEMAS:
            raise ReceiptError(f"refusing unsupported receipt schema {schema!r}")
        den = d["denominator"]
        graded = d.get("graded_score")
        extra_key = _EXTRA_KEY.get(schema)
        for key in ("extra_" + LEGACY_SCOPE_KEY, "extra_scope"):
            if key in d and key != extra_key:
                raise ReceiptError(f"{schema} does not define {key}")
        extra = d.get(extra_key, ()) if extra_key else ()
        if type(extra) not in (list, tuple) or any(type(item) is not str for item in extra):
            raise ReceiptError(f"{extra_key} must be a list of strings")
        receipt = cls(
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
            budget=Budget(**d["budget"]),
            graded_score=GradedScore(**graded) if graded else None,
            model_ref=d["model_ref"],
            base_weights_digest=d["base_weights_digest"],
            harness_version=d["harness_version"],
            input_tier_multiset=tuple(d.get("input_tier_multiset", ())),
            novelty_verdict=d.get("novelty_verdict", "UNKNOWN"),
            unverifiable_reason=d.get("unverifiable_reason", ""),
            undecided_reason=d.get("undecided_reason", ""),
            extra_scope=tuple(extra), schema=schema)
        key = receipt.scope_key()
        other = SCOPE_KEY if key == LEGACY_SCOPE_KEY else LEGACY_SCOPE_KEY
        if other in d:
            raise ReceiptError(f"{schema} carries {other!r}; its list is {key!r}")
        claimed = d.get(key)
        if schema == LEGACY_SCHEMA:
            base = receipt.scope()
            if (type(claimed) is not list or claimed[:len(base)] != base
                    or any(type(item) is not str for item in claimed)):
                raise ReceiptError(f"{key} does not match legacy v3 limits")
            receipt = replace(receipt, extra_scope=tuple(claimed[len(base):]))
        if claimed != receipt.scope():
            raise ReceiptError(f"{key} does not exactly match the receipt's derived {key}")
        return receipt
