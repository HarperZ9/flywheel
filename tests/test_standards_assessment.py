from __future__ import annotations

import copy
import json
from pathlib import Path

from harness.standards_assessment import assess_profile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "standards" / "synthetic-administrative-profile.json"


def load_profile() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def context(**extra: object) -> dict:
    base: dict[str, object] = {
        "subject_id": "synthetic-office-workflow",
        "jurisdiction": "SYNTHETIC",
        "operator_role": "operator",
        "covered_use": "administrative_review",
    }
    base.update(extra)
    return base


def first_requirement(result: dict) -> dict:
    return result["requirements"][0]


def test_applicable_requirement_preserves_source_and_evidence_gaps() -> None:
    result = assess_profile(load_profile(), context(), as_of="2026-09-16")
    requirement = first_requirement(result)

    assert result["schema"] == "flywheel.standards-assessment/v1"
    assert result["profile"] == {
        "profile_id": "synthetic-admin-assurance",
        "version": "2026.09",
    }
    assert requirement["applicability"] == "applies"
    assert requirement["mapping"]["valid"] is True
    assert requirement["evidence"]["status"] == "partial"
    assert result["source"]["status"] == "discovered"
    assert "source_not_full_text_reviewed" in result["gaps"]
    assert "partial_evidence" in requirement["gaps"]
    assert "does not prove legal compliance" in result["does_not_prove"]


def test_missing_selector_fact_needs_review_not_exemption() -> None:
    missing_role = context()
    del missing_role["operator_role"]

    result = assess_profile(load_profile(), missing_role, as_of="2026-09-16")

    assert first_requirement(result)["applicability"] == "needs_review"
    assert first_requirement(result)["reasons"] == [{
        "selector": "operator_role",
        "expected": ["operator"],
        "supplied": None,
        "reason": "missing_fact",
    }]


def test_wrong_role_and_jurisdiction_exclude_with_cited_fact() -> None:
    role_result = assess_profile(
        load_profile(), context(operator_role="vendor"), as_of="2026-09-16")
    assert first_requirement(role_result)["applicability"] == \
        "does_not_apply_with_reason"
    assert first_requirement(role_result)["reasons"][0]["selector"] == \
        "operator_role"
    assert first_requirement(role_result)["reasons"][0]["supplied"] == "vendor"

    jurisdiction_result = assess_profile(
        load_profile(), context(jurisdiction="OTHER"), as_of="2026-09-16")
    assert first_requirement(jurisdiction_result)["applicability"] == \
        "does_not_apply_with_reason"
    assert first_requirement(jurisdiction_result)["reasons"][0]["selector"] == \
        "jurisdiction"
    assert first_requirement(jurisdiction_result)["reasons"][0]["supplied"] == \
        "OTHER"


def test_unrecognized_control_keeps_mapping_from_becoming_valid() -> None:
    profile = load_profile()
    profile["requirements"][0]["maps_to_controls"] = ["tadr:T9:imaginary"]

    result = assess_profile(profile, context(), as_of="2026-09-16")

    requirement = first_requirement(result)
    assert requirement["applicability"] == "applies"
    assert requirement["mapping"] == {
        "valid": False,
        "unrecognized_controls": ["tadr:T9:imaginary"],
    }
    assert "unrecognized_control_mapping" in requirement["gaps"]


def test_caller_control_catalog_strings_do_not_validate_invented_controls() -> None:
    profile = load_profile()
    profile["requirements"][0]["maps_to_controls"] = ["tadr:T9:invented"]

    result = assess_profile(
        profile,
        context(control_catalog=["tadr:T9:invented"]),
        as_of="2026-09-16",
    )

    requirement = first_requirement(result)
    assert requirement["applicability"] == "applies"
    assert requirement["mapping"]["valid"] is False
    assert requirement["mapping"]["unrecognized_controls"] == [
        "tadr:T9:invented"]
    assert "unrecognized_control_mapping" in requirement["gaps"]


def test_source_intervals_and_supersession_stay_distinct_from_applicability() -> None:
    future = assess_profile(load_profile(), context(), as_of="2026-09-15")
    assert first_requirement(future)["applicability"] == \
        "does_not_apply_with_reason"
    assert first_requirement(future)["reasons"][0]["reason"] == \
        "not_yet_effective"

    superseded_unreviewed = load_profile()
    superseded_unreviewed["provenance"]["source_status"] = "superseded"
    superseded_unreviewed["effective"]["superseded_by"] = ["synthetic-admin-2027"]
    superseded_unreviewed["instrument"]["binding_review_status"] = "not_reviewed"
    result = assess_profile(
        superseded_unreviewed, context(), as_of="2026-09-16")
    assert first_requirement(result)["applicability"] == "needs_review"
    assert result["source"]["status"] == "superseded"
    assert "binding_review_required_for_superseded_source" in result["gaps"]

    pinned = copy.deepcopy(superseded_unreviewed)
    pinned["instrument"]["binding_basis"] = "contract_clause"
    pinned["instrument"]["binding_review_status"] = "accepted_pinned_basis"
    pinned_result = assess_profile(pinned, context(), as_of="2026-09-16")
    assert pinned_result["verdict"] == "NEEDS_REVIEW"
    assert first_requirement(pinned_result)["applicability"] == "applies"
    assert pinned_result["source"]["status"] == "superseded"
    assert "binding_review_not_independently_verified" in \
        pinned_result["gaps"]
    assert "binding_review_not_independently_verified" in \
        first_requirement(pinned_result)["gaps"]


def test_reported_pinned_basis_does_not_make_superseded_source_reviewable() -> None:
    profile = load_profile()
    profile["provenance"]["source_status"] = "full_text_reviewed"
    profile["provenance"]["review_status"] = "reviewed"
    profile["provenance"]["source_sha256"] = "c" * 64
    profile["provenance"]["raw_source_hash_null_reason"] = None
    profile["effective"]["superseded_by"] = ["synthetic-admin-2027"]
    profile["instrument"]["binding_basis"] = "contract_clause"
    profile["instrument"]["binding_review_status"] = "accepted_pinned_basis"
    profile["requirements"][0]["evidence"]["status"] = "observed"

    result = assess_profile(profile, context(), as_of="2026-09-16")

    assert result["verdict"] == "NEEDS_REVIEW"
    assert first_requirement(result)["applicability"] == "applies"
    assert "binding_review_not_independently_verified" in result["gaps"]
    assert result["source"]["verification"] == \
        "caller_reported_not_independently_verified"


def test_conflicting_facts_produce_conflict_record() -> None:
    result = assess_profile(
        load_profile(),
        context(conflicting_facts=[{"selector": "jurisdiction"}]),
        as_of="2026-09-16",
    )

    assert first_requirement(result)["applicability"] == "conflict"
    assert result["conflicts"] == [{"selector": "jurisdiction"}]


def test_irrelevant_political_labels_do_not_change_core_results() -> None:
    left = assess_profile(
        load_profile(),
        context(political_label="party-a", national_label="state-a"),
        as_of="2026-09-16",
    )
    right = assess_profile(
        load_profile(),
        context(political_label="party-b", national_label="state-b"),
        as_of="2026-09-16",
    )

    assert left == right
