import json
from pathlib import Path

from proof_surface import work_record as wr
from proof_surface import validate_work_record

CONF = Path(__file__).resolve().parents[1] / "conformance" / "work-record" / "v0.1"


def _valid() -> dict:
    return json.loads(
        (CONF / "valid" / "minimal.record.json").read_text(encoding="utf-8")
    )


def test_minimal_valid_record_passes():
    assert validate_work_record(_valid()) == []


def test_forbidden_field_rejected_with_clear_message():
    data = _valid()
    data["federal_appointment"] = {"state": "embedded"}
    assert any("forbidden" in issue.message for issue in validate_work_record(data))


def test_every_prefire_key_is_forbidden():
    for key in wr.FORBIDDEN_FIELDS:
        data = _valid()
        data[key] = "x"
        issues = validate_work_record(data)
        assert any(
            issue.path == f"$.{key}" and "forbidden" in issue.message
            for issue in issues
        ), key


def test_forbidden_field_rejected_when_nested():
    data = _valid()
    data["cost"]["authorization_context_mode"] = "lossy_neutral_embedded_state"
    assert any(
        issue.path.endswith("authorization_context_mode")
        and "forbidden" in issue.message
        for issue in validate_work_record(data)
    )


def test_unknown_root_field_rejected():
    data = _valid()
    data["extra"] = 1
    assert validate_work_record(data)


def test_bad_outcome_enum_rejected():
    data = _valid()
    data["outcome"] = "authorized"
    assert any(issue.path == "$.outcome" for issue in validate_work_record(data))


def test_direction_must_be_output_only():
    data = _valid()
    data["direction"] = "bidirectional"
    assert any(issue.path == "$.direction" for issue in validate_work_record(data))


def test_missing_direction_rejected():
    data = _valid()
    del data["direction"]
    assert any(issue.path == "$.direction" for issue in validate_work_record(data))


def test_bad_sha256_rejected():
    data = _valid()
    data["inputs"][0]["sha256"] = "not-a-hash"
    assert any(issue.path.endswith("sha256") for issue in validate_work_record(data))


def test_conformance_fixtures_match_manifest():
    manifest = json.loads((CONF / "manifest.json").read_text(encoding="utf-8"))
    for fixture in manifest["fixtures"]:
        data = json.loads((CONF / fixture["path"]).read_text(encoding="utf-8"))
        issues = validate_work_record(data)
        if fixture["expected"] == "valid":
            assert issues == [], f"{fixture['path']} should be valid: {issues}"
        else:
            assert issues, f"{fixture['path']} should be invalid"
