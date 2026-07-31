"""Shared receipt fixtures for the ledger and contest suites.

Six test files each carried a near-identical copy of these factories, so adding
one required field to the receipt schema meant six edits, and two of those files
crossed the line-count gate on the way through. The duplication was the defect.
The factories live here now, and a caller overrides only what its test is about.

Defaults are the ones the ledger and contest suites already used, so moving a
file onto this helper changes no digest: fully enumerated coverage, a
deterministic gate as the model reference, and an empty weights digest.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.receipt import Receipt                                  # noqa: E402
from harness.receipt_fields import (                                 # noqa: E402
    Budget, Denominator, EvidenceKind, Tier)
from harness.verdict import Verdict, Attribution                     # noqa: E402

COMPLETE_COVERAGE = {"predicate_exact": True, "search_space_enumerated": True,
                     "enumerated_fraction": "1", "stop_reason": "complete",
                     "guarantee_weakens_above": None}


def den(**kw) -> Denominator:
    base = dict(attempts=8, group_size=4, oracle_calls_consumed=9, hits=1,
                undecided=0, unverifiable=0, parse_failures=0, timeouts=0,
                tokens_in=120, tokens_out=512, cache_hit_tokens=0,
                tasks_proposed=4, tasks_filtered_out=0, retries=0,
                oracle_feedback_visible=False, filter_id="learn.difficulty.v1",
                filter_hash="sha256:" + "f" * 64, filter_is_learned=False)
    base.update(kw)
    return Denominator(**base)


def budget(**kw) -> Budget:
    base = dict(wall_seconds_limit=600, tokens_limit=4096, retries_limit=2,
                exhausted=False)
    base.update(kw)
    return Budget(**base)


def receipt(**kw) -> Receipt:
    base = dict(
        criterion_id="zarankiewicz.z_2_2", criterion_version=1,
        criterion_sha256="sha256:" + "c" * 64, family="zarankiewicz",
        family_instance_id="z-7", generator_id="g.v1", generator_seed=7,
        candidate_sha256="sha256:" + "d" * 64, prompt_hash="sha256:" + "e" * 64,
        checker_module="harness.certificates.zarankiewicz",
        checker_source_sha256="sha256:" + "a" * 64,
        executes_candidate_code=False, oracle_qa_card_hash="deadbeefdeadbeef",
        held_out_agreement="AGREE", evidence_kind=EvidenceKind.CONSTRUCTIVE,
        tier=Tier.CONSTRUCTION_CERTIFICATE, verdict=Verdict.PASS,
        attribution=Attribution.CANDIDATE, objective="21",
        incumbent_objective="21", incumbent_source="operator_search",
        coverage=dict(COMPLETE_COVERAGE), raw_stdout_sha256="b" * 64,
        analysis_script_sha256="sha256:" + "9" * 64,
        model_ref="gate:deterministic", base_weights_digest="",
        harness_version="phase1c")
    base.setdefault("denominator", den())
    base.setdefault("budget", budget())
    base.update(kw)
    return Receipt(**base)
