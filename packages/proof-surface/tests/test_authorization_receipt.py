"""Tests for the authorization-receipt contract.

Mirrors the style of test_work_record.py exactly.  Every assertion is
meaningful; no "it didn't crash" tests.

Contract invariants exercised here:
  * Forbidden-field guard -- recursive, fail-closed, same set as work-record.
  * Required expiry -- expires_at is mandatory; authority must expire.
  * Default-deny scope -- empty allowed_actions authorizes nothing.
  * check_action helper -- out-of-scope denied, in-scope allowed, revoked denied,
    expired denied.
  * additionalProperties:false at root and every nested object.
  * Conformance manifest -- every fixture must match its declared expected result.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from proof_surface import authorization_receipt as ar
from proof_surface import validate_authorization_receipt
from proof_surface._strict_json import strict_json_load

CONF = (
    Path(__file__).resolve().parents[1]
    / "conformance"
    / "authorization-receipt"
    / "v0.1"
)
CONF_V2 = CONF.parent / "v0.2"
RAW_V2_INVALIDS = (
    "invalid/duplicate-revoked.receipt.json",
    "invalid/duplicate-action.receipt.json",
    "invalid/duplicate-target.receipt.json",
    "invalid/duplicate-max-actions.receipt.json",
    "invalid/duplicate-escaped-action.receipt.json",
    "invalid/nan-max-actions.receipt.json",
    "invalid/infinity-max-actions.receipt.json",
    "invalid/negative-infinity-max-actions.receipt.json",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _valid() -> dict:
    return json.loads(
        (CONF / "valid" / "minimal.receipt.json").read_text(encoding="utf-8")
    )


def _now_str(offset_seconds: int = 0) -> str:
    dt = datetime.now(tz=timezone.utc) + timedelta(seconds=offset_seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _receipt(
    *,
    actions: list[str] | None = None,
    targets: list[str] | None = None,
    revoked: bool = False,
    granted_offset: int = -3600,
    expires_offset: int = 3600,
) -> dict:
    """Build a minimal syntactically valid receipt for check_action tests."""
    return {
        "authorization_version": "0.1",
        "receipt_id": "ar-test-fixture",
        "kind": "authorization-grant",
        "principal": {"id": "user:alice@example.com"},
        "agent": {"id": "agent:test"},
        "intent": "Test fixture for check_action.",
        "scope": {
            "allowed_actions": actions if actions is not None else ["read_file"],
            "allowed_targets": targets if targets is not None else [],
        },
        "granted_at": _now_str(granted_offset),
        "expires_at": _now_str(expires_offset),
        "revoked": revoked,
    }


# ---------------------------------------------------------------------------
# Structural validation -- happy path
# ---------------------------------------------------------------------------


def test_minimal_valid_receipt_passes():
    assert validate_authorization_receipt(_valid()) == []


# ---------------------------------------------------------------------------
# Forbidden-field guard
# ---------------------------------------------------------------------------


def test_forbidden_field_rejected_at_root():
    data = _valid()
    data["federal_appointment"] = {"state": "embedded"}
    issues = validate_authorization_receipt(data)
    assert any("forbidden" in i.message for i in issues)


def test_every_prefire_key_is_forbidden():
    for key in ar.FORBIDDEN_FIELDS:
        data = _valid()
        data[key] = "x"
        issues = validate_authorization_receipt(data)
        assert any(i.path == f"$.{key}" and "forbidden" in i.message for i in issues), (
            f"key {key!r} not blocked"
        )


def test_forbidden_field_rejected_when_nested_in_scope():
    data = _valid()
    data["scope"]["authorization_context_mode"] = "consume_verified_native_state"
    issues = validate_authorization_receipt(data)
    assert any(
        i.path.endswith("authorization_context_mode") and "forbidden" in i.message
        for i in issues
    )


def test_forbidden_field_rejected_when_nested_in_principal():
    data = _valid()
    data["principal"]["prefire"] = True
    issues = validate_authorization_receipt(data)
    assert any(i.path.endswith("prefire") and "forbidden" in i.message for i in issues)


# ---------------------------------------------------------------------------
# Required-expiry enforcement
# ---------------------------------------------------------------------------


def test_missing_expires_at_rejected():
    data = _valid()
    del data["expires_at"]
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.expires_at" for i in issues)


def test_expires_at_before_granted_at_rejected():
    data = _valid()
    data["granted_at"] = "2026-06-17T10:00:00Z"
    data["expires_at"] = "2026-06-17T09:00:00Z"
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.expires_at" for i in issues)


def test_expires_at_equal_to_granted_at_rejected():
    data = _valid()
    data["granted_at"] = "2026-06-17T10:00:00Z"
    data["expires_at"] = "2026-06-17T10:00:00Z"
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.expires_at" for i in issues)


def test_expires_at_without_timezone_rejected():
    data = _valid()
    data["expires_at"] = "2026-06-17T23:59:59"
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.expires_at" for i in issues)


# ---------------------------------------------------------------------------
# additionalProperties:false enforcement
# ---------------------------------------------------------------------------


def test_unknown_root_field_rejected():
    data = _valid()
    data["extra_authority"] = "full_access"
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.extra_authority" for i in issues)


def test_unknown_scope_field_rejected():
    data = _valid()
    data["scope"]["wildcard"] = "*"
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.scope.wildcard" for i in issues)


def test_unknown_principal_field_rejected():
    data = _valid()
    data["principal"]["clearance_level"] = "top_secret"
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.principal.clearance_level" for i in issues)


def test_unknown_agent_field_rejected():
    data = _valid()
    data["agent"]["trusted"] = True
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.agent.trusted" for i in issues)


# ---------------------------------------------------------------------------
# Scope shape -- default-deny
# ---------------------------------------------------------------------------


def test_scope_allowed_actions_must_be_array():
    data = _valid()
    data["scope"]["allowed_actions"] = "read_file"
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.scope.allowed_actions" for i in issues)


def test_scope_allowed_targets_must_be_array():
    data = _valid()
    data["scope"]["allowed_targets"] = "any"
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.scope.allowed_targets" for i in issues)


def test_scope_max_actions_must_be_non_negative():
    data = _valid()
    data["scope"]["max_actions"] = -1
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.scope.max_actions" for i in issues)


def test_scope_max_actions_bool_rejected():
    data = _valid()
    data["scope"]["max_actions"] = True
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.scope.max_actions" for i in issues)


# ---------------------------------------------------------------------------
# Required-field checks
# ---------------------------------------------------------------------------


def test_missing_principal_id_rejected():
    data = _valid()
    del data["principal"]["id"]
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.principal.id" for i in issues)


def test_empty_principal_id_rejected():
    data = _valid()
    data["principal"]["id"] = "   "
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.principal.id" for i in issues)


def test_missing_agent_id_rejected():
    data = _valid()
    del data["agent"]["id"]
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.agent.id" for i in issues)


def test_missing_intent_rejected():
    data = _valid()
    del data["intent"]
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.intent" for i in issues)


def test_revoked_must_be_bool():
    data = _valid()
    data["revoked"] = "no"
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.revoked" for i in issues)


def test_kind_must_be_authorization_grant():
    data = _valid()
    data["kind"] = "authorization-suppression"
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.kind" for i in issues)


def test_authorization_version_const():
    data = _valid()
    data["authorization_version"] = "2.0"
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.authorization_version" for i in issues)


def test_notes_must_be_string_when_present():
    data = _valid()
    data["notes"] = 42
    issues = validate_authorization_receipt(data)
    assert any(i.path == "$.notes" for i in issues)


# ---------------------------------------------------------------------------
# check_action -- default-deny and positive-allow
# ---------------------------------------------------------------------------


def test_check_action_in_scope_allowed():
    receipt = _receipt(actions=["read_file"], targets=[])
    result = ar.check_action(receipt, "read_file", "some/path.txt")
    assert result is None, f"expected None (allowed), got {result}"


def test_check_action_out_of_scope_denied():
    receipt = _receipt(actions=["read_file"], targets=[])
    result = ar.check_action(receipt, "write_file", "some/path.txt")
    assert result is not None
    assert "not in allowed_actions" in result.message


def test_check_action_target_restricted_allowed():
    receipt = _receipt(
        actions=["read_file"], targets=["C:/dev/public/proof-surface/conformance/"]
    )
    result = ar.check_action(
        receipt, "read_file", "C:/dev/public/proof-surface/conformance/"
    )
    assert result is None


def test_check_action_target_restricted_denied():
    receipt = _receipt(
        actions=["read_file"], targets=["C:/dev/public/proof-surface/conformance/"]
    )
    result = ar.check_action(receipt, "read_file", "C:/dev/secret/")
    assert result is not None
    assert "not in allowed_targets" in result.message


def test_check_action_empty_allowed_actions_denies_everything():
    receipt = _receipt(actions=[], targets=[])
    result = ar.check_action(receipt, "read_file", "any/path")
    assert result is not None
    assert "no actions" in result.message or "default-deny" in result.message


def test_check_action_revoked_denies():
    receipt = _receipt(revoked=True)
    result = ar.check_action(receipt, "read_file", "any/path")
    assert result is not None
    assert "revoked" in result.message


def test_check_action_expired_denies():
    receipt = _receipt(granted_offset=-7200, expires_offset=-3600)
    result = ar.check_action(receipt, "read_file", "any/path")
    assert result is not None
    assert "expired" in result.message


def test_check_action_not_yet_active_denies():
    receipt = _receipt(granted_offset=3600, expires_offset=7200)
    result = ar.check_action(receipt, "read_file", "any/path")
    assert result is not None
    assert "not yet" in result.message


def test_check_action_invalid_receipt_denies():
    receipt = {"authorization_version": "0.1"}  # structurally broken
    result = ar.check_action(receipt, "read_file", "any/path")
    assert result is not None
    assert "invalid" in result.message


# ---------------------------------------------------------------------------
# Conformance manifest
# ---------------------------------------------------------------------------


def test_conformance_fixtures_match_manifest():
    manifest = json.loads((CONF / "manifest.json").read_text(encoding="utf-8"))
    for fixture in manifest["fixtures"]:
        data = json.loads((CONF / fixture["path"]).read_text(encoding="utf-8"))
        issues = validate_authorization_receipt(data)
        if fixture["expected"] == "valid":
            assert issues == [], f"{fixture['path']} should be valid: {issues}"
        else:
            assert issues, f"{fixture['path']} should be invalid but got no issues"


# ---------------------------------------------------------------------------
# Authorization receipt v0.2 inner contract
# ---------------------------------------------------------------------------


def _v2(relative_path: str = "valid/minimal.receipt.json") -> dict:
    data = strict_json_load(CONF_V2 / relative_path)
    assert isinstance(data, dict)
    return data


def _v2_now() -> datetime:
    return datetime(2026, 8, 2, 12, 2, tzinfo=timezone.utc)


def test_v0_2_minimal_receipt_passes() -> None:
    assert ar.validate_authorization_receipt_v2(_v2()) == []


def test_v0_2_unknown_field_rejected() -> None:
    issues = ar.validate_authorization_receipt_v2(
        _v2("invalid/unknown-root-field.receipt.json")
    )
    assert any(issue.path == "$.unexpected_authority" for issue in issues)


def test_v0_2_nonce_must_carry_at_least_128_bits() -> None:
    issues = ar.validate_authorization_receipt_v2(
        _v2("invalid/short-nonce.receipt.json")
    )
    assert any(
        issue.path == "$.nonce" and "128-bit" in issue.message
        for issue in issues
    )


def test_v0_2_requires_every_identity_scope_time_and_budget_field() -> None:
    required = {
        "authorization_version",
        "receipt_id",
        "kind",
        "nonce",
        "agent_id",
        "action",
        "target",
        "issued_at",
        "expires_at",
        "max_actions",
        "revoked",
    }
    for field in sorted(required):
        receipt = _v2()
        del receipt[field]
        issues = ar.validate_authorization_receipt_v2(receipt)
        assert any(issue.path == f"$.{field}" for issue in issues), field


def test_v0_2_schema_and_stdlib_validator_accept_the_same_valid_fixture() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "schemas"
        / "authorization-receipt-v0.2.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert list(jsonschema.Draft202012Validator(schema).iter_errors(_v2())) == []
    assert ar.validate_authorization_receipt_v2(_v2()) == []


def test_v0_2_schema_and_reference_validator_agree_on_all_manifest_vectors() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "schemas"
        / "authorization-receipt-v0.2.schema.json"
    )
    schema_validator = jsonschema.Draft202012Validator(
        json.loads(schema_path.read_text(encoding="utf-8"))
    )
    manifest = _v2("manifest.json")

    for fixture in manifest["fixtures"]:
        try:
            receipt = _v2(fixture["path"])
        except ValueError:
            assert fixture["expected"] == "invalid", fixture["path"]
            continue
        schema_valid = list(schema_validator.iter_errors(receipt)) == []
        reference_valid = ar.validate_authorization_receipt_v2(receipt) == []
        expected_valid = fixture["expected"] == "valid"
        assert schema_valid == reference_valid == expected_valid, fixture["path"]


def test_v0_2_schema_parity_negative_corpus() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "schemas"
        / "authorization-receipt-v0.2.schema.json"
    )
    schema_validator = jsonschema.Draft202012Validator(
        json.loads(schema_path.read_text(encoding="utf-8"))
    )
    manifest = _v2("manifest.json")
    corpus = _v2(manifest["schema_parity_corpus"])

    for case in corpus["cases"]:
        receipt = _v2(corpus["base"])
        receipt[case["field"]] = case["value"]
        schema_valid = list(schema_validator.iter_errors(receipt)) == []
        reference_valid = ar.validate_authorization_receipt_v2(receipt) == []
        assert case["expected"] == "invalid"
        assert schema_valid is False, case["case_id"]
        assert reference_valid is False, case["case_id"]


def test_v0_2_exact_agent_action_and_target_match() -> None:
    receipt = _v2()
    assert (
        ar.check_action_v2(
            receipt,
            "lane.call",
            "forum/forum_route",
            agent_id="agent:router-7",
            actions_used=0,
            now=_v2_now(),
        )
        is None
    )


def test_v0_2_agent_identity_is_exact() -> None:
    issue = ar.check_action_v2(
        _v2(),
        "lane.call",
        "forum/forum_route",
        agent_id="agent:router-70",
        actions_used=0,
        now=_v2_now(),
    )
    assert issue is not None
    assert issue.path == "$.agent_id"
    assert "agent_mismatch" in issue.message


def test_v0_2_action_scope_is_exact() -> None:
    issue = ar.check_action_v2(
        _v2(),
        "lane.calls",
        "forum/forum_route",
        agent_id="agent:router-7",
        actions_used=0,
        now=_v2_now(),
    )
    assert issue is not None
    assert issue.path == "$.action"
    assert "action_mismatch" in issue.message


def test_v0_2_target_scope_is_exact() -> None:
    issue = ar.check_action_v2(
        _v2(),
        "lane.call",
        "forum/forum_verify",
        agent_id="agent:router-7",
        actions_used=0,
        now=_v2_now(),
    )
    assert issue is not None
    assert issue.path == "$.target"
    assert "target_mismatch" in issue.message


def test_v0_2_action_budget_is_consumed() -> None:
    receipt = _v2()
    issue = ar.check_action_v2(
        receipt,
        "lane.call",
        "forum/forum_route",
        agent_id="agent:router-7",
        actions_used=1,
        now=_v2_now(),
    )
    assert receipt["max_actions"] == 1
    assert issue is not None
    assert issue.path == "$.max_actions"
    assert "action_budget_exhausted" in issue.message


def test_v0_2_invalid_runtime_action_count_fails_closed() -> None:
    for actions_used in (-1, True):
        issue = ar.check_action_v2(
            _v2(),
            "lane.call",
            "forum/forum_route",
            agent_id="agent:router-7",
            actions_used=actions_used,
            now=_v2_now(),
        )
        assert issue is not None
        assert "invalid_actions_used" in issue.message


def test_v0_2_revocation_and_time_window_deny() -> None:
    receipt = _v2()
    receipt["revoked"] = True
    issue = ar.check_action_v2(
        receipt,
        "lane.call",
        "forum/forum_route",
        agent_id="agent:router-7",
        actions_used=0,
        now=_v2_now(),
    )
    assert issue is not None and "revoked" in issue.message

    receipt = _v2()
    issue = ar.check_action_v2(
        receipt,
        "lane.call",
        "forum/forum_route",
        agent_id="agent:router-7",
        actions_used=0,
        now=datetime(2026, 8, 2, 12, 5, tzinfo=timezone.utc),
    )
    assert issue is not None and "expired" in issue.message


def test_v0_2_conformance_fixtures_match_manifest() -> None:
    manifest = _v2("manifest.json")
    for fixture in manifest["fixtures"]:
        try:
            receipt = _v2(fixture["path"])
        except ValueError:
            assert fixture["expected"] == "invalid", fixture["path"]
            continue
        issues = ar.validate_authorization_receipt_v2(receipt)
        if fixture["expected"] == "valid":
            assert issues == [], f"{fixture['path']} should be valid: {issues}"
        else:
            assert issues, f"{fixture['path']} should be invalid"


@pytest.mark.parametrize("relative_path", RAW_V2_INVALIDS)
def test_v0_2_raw_ambiguous_vectors_fail_strict_loading(relative_path: str) -> None:
    with pytest.raises(ValueError, match="strict loader"):
        strict_json_load(CONF_V2 / relative_path)


@pytest.mark.parametrize("relative_path", RAW_V2_INVALIDS)
def test_v0_2_file_validator_returns_typed_issue_for_ambiguous_json(
    relative_path: str,
) -> None:
    issues = ar.validate_authorization_receipt_v2_file(CONF_V2 / relative_path)
    assert len(issues) == 1
    assert issues[0].path == "$"
    assert "strict loader" in issues[0].message


def test_v0_1_legacy_fixture_bytes_and_behavior_are_pinned() -> None:
    manifest = _v2("manifest.json")
    legacy = CONF_V2 / manifest["migration"]["legacy_path"]
    legacy_bytes = legacy.read_bytes()

    assert (
        hashlib.sha256(legacy_bytes).hexdigest()
        == manifest["migration"]["legacy_sha256"]
    )
    assert ar.validate_authorization_receipt(json.loads(legacy_bytes)) == []
    assert ar.validate_authorization_receipt_v2(json.loads(legacy_bytes))


def test_v0_2_migration_fixture_is_explicit_and_valid() -> None:
    manifest = _v2("manifest.json")
    migrated = _v2(manifest["migration"]["migrated_path"])

    assert ar.validate_authorization_receipt_v2(migrated) == []
    assert manifest["migration"]["operator_supplied_fields"] == [
        "nonce",
        "action",
        "target",
    ]
