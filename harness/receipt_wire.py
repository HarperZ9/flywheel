"""receipt_wire.py -- read a receipt from its wire form, refusing what it cannot vouch for.

Split from receipt.py to keep that module under the line gate. The reader checks
the schema first: a reader that ignores the version silently reinterprets fields
whose meaning changed between versions, and then reports a claim digest over a
different set of fields than the writer covered.
"""
from __future__ import annotations

from dataclasses import replace

from .receipt_fields import Budget, Denominator, EvidenceKind, GradedScore, ReceiptError, Tier
from .receipt_route import Route
from .verdict import Attribution, Verdict


def _extra(d: dict, schema: str, legacy: str) -> tuple:
    if schema == legacy and "extra_does_not_prove" in d:
        raise ReceiptError("v3 does not define extra_does_not_prove")
    extra = d.get("extra_does_not_prove", ()) if schema != legacy else ()
    if type(extra) not in (list, tuple) or any(type(item) is not str for item in extra):
        raise ReceiptError("extra_does_not_prove must be a list of strings")
    return tuple(extra)


def _route(d: dict, schema: str, routed: str):
    if schema != routed:
        if "route" in d:
            raise ReceiptError(f"{schema} does not define route")
        return None
    return Route.from_dict(d.get("route"))


def _fields(d: dict) -> dict:
    den, graded = d["denominator"], d.get("graded_score")
    return dict(
        criterion_id=d["criterion_id"], criterion_version=d["criterion_version"],
        criterion_sha256=d["criterion_sha256"], family=d["family"],
        family_instance_id=d["family_instance_id"], generator_id=d["generator_id"],
        generator_seed=d["generator_seed"], candidate_sha256=d["candidate_sha256"],
        prompt_hash=d["prompt_hash"], checker_module=d["checker_module"],
        checker_source_sha256=d["checker_source_sha256"],
        executes_candidate_code=d["executes_candidate_code"],
        oracle_qa_card_hash=d["oracle_qa_card_hash"],
        held_out_agreement=d["held_out_agreement"],
        evidence_kind=EvidenceKind(d["evidence_kind"]), tier=Tier(d["tier"]),
        verdict=Verdict(d["verdict"]), attribution=Attribution(d["attribution"]),
        objective=d["objective"], incumbent_objective=d["incumbent_objective"],
        incumbent_source=d["incumbent_source"], coverage=d["coverage"],
        raw_stdout_sha256=d["raw_stdout_sha256"],
        analysis_script_sha256=d["analysis_script_sha256"],
        denominator=Denominator(**den), budget=Budget(**d["budget"]),
        graded_score=GradedScore(**graded) if graded else None,
        model_ref=d["model_ref"], base_weights_digest=d["base_weights_digest"],
        harness_version=d["harness_version"],
        input_tier_multiset=tuple(d.get("input_tier_multiset", ())),
        novelty_verdict=d.get("novelty_verdict", "UNKNOWN"),
        unverifiable_reason=d.get("unverifiable_reason", ""),
        undecided_reason=d.get("undecided_reason", ""))


def receipt_from_dict(cls, d: dict):
    from .receipt import LEGACY_SCHEMA, ROUTED_SCHEMA, SUPPORTED_SCHEMAS
    schema = d.get("schema")
    if schema not in SUPPORTED_SCHEMAS:
        raise ReceiptError(f"refusing unsupported receipt schema {schema!r}")
    receipt = cls(**_fields(d), extra_does_not_prove=_extra(d, schema, LEGACY_SCHEMA),
                  schema=schema, route=_route(d, schema, ROUTED_SCHEMA))
    claimed_limits = d.get("does_not_prove")
    if schema == LEGACY_SCHEMA:
        base = receipt.does_not_prove()
        if (type(claimed_limits) is not list or claimed_limits[:len(base)] != base
                or any(type(item) is not str for item in claimed_limits)):
            raise ReceiptError("does_not_prove does not match legacy v3 limits")
        receipt = replace(receipt, extra_does_not_prove=tuple(claimed_limits[len(base):]))
    if claimed_limits != receipt.does_not_prove():
        raise ReceiptError("does_not_prove does not exactly match receipt limits")
    return receipt
