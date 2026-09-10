"""Plaintext Bulletin approval names an origin before any external action."""
from copy import deepcopy

import pytest

from harness.gateway_operation import canonicalize_operation, GatewayOperationError
from harness.outcome_bulletin import build_preview, build_gateway_grant_request

ORIGIN = "https://bulletin.zaindharper.workers.dev"


def operation(origin=ORIGIN):
    return {"name": "bulletin", "tool": "board_write_post",
            "args": {"room": "findings", "body": "Synthetic origin control"},
            "governance_tier": "T2", "timeout": 20,
            "bulletin_base_url": origin, "data_refs": [], "credential_refs": []}


def outcome():
    return {"schema": "flywheel.outcome-bulletin-request/v1", "title": "Control",
            "status": "Synthetic", "does_not_prove": ["a live post"],
            "links": [{"label": "Source", "url": "https://github.com/HarperZ9/flywheel"}]}


def test_plain_operation_destination_and_digest_bind_explicit_origin():
    first = canonicalize_operation("lane.call", operation())
    second = canonicalize_operation("lane.call", operation("https://example.invalid"))
    assert dict(first.destination) == {"kind": "lane", "ref": "bulletin",
                                       "bulletin_base_url": ORIGIN}
    assert first.operation_sha256 != second.operation_sha256
    assert first.arguments_sha256 != second.arguments_sha256


def test_legacy_unbound_operation_is_not_silently_upgraded():
    legacy = operation()
    del legacy["bulletin_base_url"]
    with pytest.raises(GatewayOperationError, match="BULLETIN_ORIGIN_REQUIRED"):
        canonicalize_operation("lane.call", legacy)


@pytest.mark.parametrize("origin", [None, "", True, " https://example.invalid",
    "https://example.invalid\n", "https://user:pass@example.invalid",
    "https://example.invalid/path", "https://example.invalid?", "https://example.invalid#",
    "https://example.invalid:bad", "https://example.invalid:0", "https://example.invalid:65536",
    "https://example.invalid:", "https://example.invalid\\x", "https://exa%6dple.invalid",
    "http://example.invalid", "ftp://example.invalid", "https://example.invalid.",
    "https://EXAMPLE.invalid", "https://example.invalid/", "https://example.invalid:443"])
def test_operation_rejects_malformed_or_noncanonical_origin(origin):
    with pytest.raises(GatewayOperationError):
        canonicalize_operation("lane.call", operation(origin))


def test_projection_refuses_unsupported_ip_literal_instead_of_reinterpreting_host():
    with pytest.raises(ValueError, match="BULLETIN_ORIGIN_INVALID"):
        build_preview(outcome(), bulletin_base_url="https://[v1.example]")


def test_preview_and_grant_explicitly_carry_selected_origin(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_BULLETIN_BASE_URL", "https://unapproved.invalid")
    preview = build_preview(outcome())
    assert preview["target"]["bulletin_base_url"] == ORIGIN
    selected = build_preview(outcome(), bulletin_base_url="https://EXAMPLE.invalid:443/")
    assert selected["target"]["bulletin_base_url"] == "https://example.invalid"
    request = build_gateway_grant_request(selected, journey_ref="jrn_" + "a" * 32,
        expected_event_head="b" * 64, client_request_id="origin-control")
    assert request["operation"]["bulletin_base_url"] == "https://example.invalid"
    legacy = deepcopy(preview)
    del legacy["target"]["bulletin_base_url"]
    with pytest.raises((GatewayOperationError, ValueError)):
        build_gateway_grant_request(legacy, journey_ref="jrn_" + "a" * 32,
            expected_event_head="b" * 64, client_request_id="origin-control")


@pytest.mark.parametrize("tool", ["board_read_posts", "board_publish_media_post"])
def test_other_bulletin_routes_retain_their_contract(tool):
    other = operation()
    other["tool"] = tool
    del other["bulletin_base_url"]
    assert dict(canonicalize_operation("lane.call", other).destination) == {
        "kind": "lane", "ref": "bulletin"}
    other["bulletin_base_url"] = ORIGIN
    with pytest.raises(GatewayOperationError):
        canonicalize_operation("lane.call", other)


def test_origin_field_cannot_be_smuggled_into_an_unrelated_lane():
    other = operation()
    other["name"] = "index"
    with pytest.raises(GatewayOperationError):
        canonicalize_operation("lane.call", other)


@pytest.mark.parametrize("code,status", [("BULLETIN_ORIGIN_REQUIRED", 422),
    ("BULLETIN_ORIGIN_INVALID", 422), ("BULLETIN_ORIGIN_MISMATCH", 409)])
def test_origin_errors_are_explicit_non_echoing_public_failures(code, status):
    from harness.gateway_grant_errors import gateway_error_response
    result, http = gateway_error_response(GatewayOperationError(code))
    assert http == status
    assert result["error"]["code"] == code


def test_cli_origin_override_and_invalid_origin_are_reviewable(tmp_path, capsys):
    import json
    from harness.outcome_bulletin_cli import main
    source = tmp_path / "public.json"
    source.write_text(json.dumps(outcome()), encoding="utf-8")
    assert main(["preview", "--outcome", str(source), "--bulletin-base-url",
                 "https://EXAMPLE.invalid/"]) == 0
    assert json.loads(capsys.readouterr().out)["target"]["bulletin_base_url"] == "https://example.invalid"
    assert main(["preview", "--outcome", str(source), "--bulletin-base-url",
                 "https://user:private@example.invalid"]) == 2
    raw = capsys.readouterr().out
    assert "user" not in raw and "private" not in raw and "example.invalid" not in raw
    assert json.loads(raw)["error"]["code"] == "BULLETIN_ORIGIN_INVALID"
