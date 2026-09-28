from __future__ import annotations

import copy
import json
from pathlib import Path

from harness.standards_registry import validate_profile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "standards" / "synthetic-administrative-profile.json"


def load_profile() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def assert_invalid(profile: dict, needle: str) -> dict:
    result = validate_profile(profile)
    assert result["verdict"] == "INVALID"
    assert any(needle in err["message"] for err in result["errors"])
    return result


def test_valid_discovery_profile_keeps_source_authority_gap() -> None:
    profile = load_profile()

    result = validate_profile(profile)

    assert result["schema"] == "flywheel.standards-profile-validation/v1"
    assert result["verdict"] == "VALID"
    assert result["errors"] == []
    assert {
        "code": "source_not_full_text_reviewed",
        "path": "$.provenance",
    } in result["gaps"]
    assert result["profile"] == {
        "profile_id": "synthetic-admin-assurance",
        "version": "2026.09",
        "requirements": 1,
    }
    assert "does not prove legal compliance" in result["does_not_prove"]


def test_unknown_keys_and_executable_fields_are_rejected() -> None:
    unknown = load_profile()
    unknown["authority_type"] = "law"
    assert_invalid(unknown, "unknown field")

    executable = load_profile()
    executable["requirements"][0]["command"] = "python unsafe.py"
    assert_invalid(executable, "executable field")


def test_wrong_scalar_types_include_booleans_as_integers() -> None:
    profile = load_profile()
    profile["owner"] = False
    assert_invalid(profile, "expected string")

    boolean_as_integer = load_profile()
    boolean_as_integer["requirements"][0]["review_required"] = 1
    assert_invalid(boolean_as_integer, "expected boolean")


def test_duplicate_requirement_ids_are_rejected() -> None:
    profile = load_profile()
    profile["requirements"].append(copy.deepcopy(profile["requirements"][0]))

    assert_invalid(profile, "duplicate requirement_id")


def test_malformed_dates_hashes_and_reversed_effective_range_fail() -> None:
    bad_date = load_profile()
    bad_date["effective"]["effective_from"] = "2026/09/16"
    assert_invalid(bad_date, "expected YYYY-MM-DD")

    bad_hash = load_profile()
    bad_hash["requirements"][0]["text_hash"] = "abc"
    assert_invalid(bad_hash, "expected sha256")

    reversed_range = load_profile()
    reversed_range["effective"]["effective_to"] = "2026-01-01"
    assert_invalid(reversed_range, "effective_to precedes effective_from")


def test_contradictory_source_fields_fail_without_blocking_discovery_nulls() -> None:
    discovery = load_profile()
    discovery["provenance"]["source_status"] = "discovered"
    discovery["provenance"]["source_sha256"] = None
    discovery["provenance"]["raw_source_hash_null_reason"] = "metadata only"
    assert validate_profile(discovery)["verdict"] == "VALID"

    reviewed_without_hash = load_profile()
    reviewed_without_hash["provenance"]["source_status"] = "full_text_reviewed"
    reviewed_without_hash["provenance"]["review_status"] = "reviewed"
    reviewed_without_hash["provenance"]["raw_source_hash_null_reason"] = "paywalled"
    assert_invalid(reviewed_without_hash, "reviewed source requires source_sha256")

    hash_and_null_reason = load_profile()
    hash_and_null_reason["provenance"]["source_sha256"] = "c" * 64
    assert_invalid(hash_and_null_reason, "source_sha256 conflicts")


def test_observed_or_reproduced_evidence_requires_artifact_identity() -> None:
    observed = load_profile()
    observed["requirements"][0]["evidence"]["status"] = "observed"
    observed["requirements"][0]["evidence"]["artifact_sha256"] = None
    assert_invalid(observed, "observed evidence requires artifact_sha256")

    reproduced = load_profile()
    reproduced["requirements"][0]["evidence"]["status"] = \
        "independently_reproduced"
    reproduced["requirements"][0]["evidence"]["artifact_sha256"] = None
    assert_invalid(reproduced, "observed evidence requires artifact_sha256")


def test_empty_profile_cannot_be_mistaken_for_assessment() -> None:
    result = validate_profile({})

    assert result["verdict"] == "INVALID"
    assert result["assessment"] == "not_assessed"
    assert result["profile"] is None
