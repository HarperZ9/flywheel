import json
from pathlib import Path

from proof_surface import validate_packet

CONF = Path(__file__).resolve().parents[1] / "conformance" / "proof-surface" / "v0.1"


def _valid() -> dict:
    return json.loads(
        (CONF / "valid" / "minimal.packet.json").read_text(encoding="utf-8")
    )


def test_valid_packet_passes():
    assert validate_packet(_valid()) == []


def test_unknown_root_field_rejected():
    data = _valid()
    data["unexpected"] = 1
    assert validate_packet(data)


def test_bad_check_status_rejected():
    data = _valid()
    data["checks"][0]["status"] = "approved"
    assert any(issue.path == "$.checks[0].status" for issue in validate_packet(data))


def test_empty_claims_rejected():
    data = _valid()
    data["claims"] = []
    assert any(issue.path == "$.claims" for issue in validate_packet(data))


def test_conformance_fixtures_match_manifest():
    manifest = json.loads((CONF / "manifest.json").read_text(encoding="utf-8"))
    for fixture in manifest["fixtures"]:
        data = json.loads((CONF / fixture["path"]).read_text(encoding="utf-8"))
        issues = validate_packet(data)
        if fixture["expected"] == "valid":
            assert issues == [], f"{fixture['path']} should be valid: {issues}"
        else:
            assert issues, f"{fixture['path']} should be invalid"
