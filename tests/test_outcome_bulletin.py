import json

import pytest

from harness.evidence_json import canonical_bytes
from harness.evidence_json import canonical_sha256
from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_grant_route import authorize_gateway_operation
from harness.gateway_operation import GatewayOperationError
from harness.journey_store import JourneyStore, MutationCommand
from harness.outcome_bulletin import (
    OutcomeBulletinError,
    build_gateway_grant_request,
    build_gateway_publish_envelope,
    build_preview,
    publish_preview,
)


INDEX_OUTCOME = {
    "schema": "flywheel.outcome-bulletin-request/v1",
    "title": "Index reliability checkpoint, 2026-09-07",
    "status": (
        "Index 2.11.0 is published; router durable jobs remain a "
        "pre-release integration surface."
    ),
    "room": "findings",
    "checked": [
        "GitHub release v2.11.0 is published for Index.",
        "PyPI package index-graph 2.11.0 is available.",
        "Clean-install smoke reported index 2.11.0.",
    ],
    "positive_controls": [
        "Synthetic router job lifecycle completed with a workspace map.",
        "Traversal-shaped job ids were rejected.",
    ],
    "held_blockers": [
        "Public CLI/MCP router-job wiring still waits on integration review.",
    ],
    "does_not_prove": [
        "Router durable jobs are released as public Index behavior.",
        "Private workspaces were scanned or posted.",
    ],
    "links": [
        {
            "label": "Index 2.11.0 release",
            "url": "https://github.com/HarperZ9/index/releases/tag/v2.11.0",
        },
        {
            "label": "index-graph 2.11.0 on PyPI",
            "url": "https://pypi.org/project/index-graph/2.11.0/",
        },
    ],
}


def test_preview_is_deterministic_public_bulletin_payload():
    """If rendering depends on dict order or private state, public review drifts."""
    first = build_preview(dict(INDEX_OUTCOME))
    second = build_preview(json.loads(json.dumps(INDEX_OUTCOME)))

    assert first == second
    assert first["schema"] == "flywheel.outcome-bulletin-preview/v1"
    assert first["target"] == {
        "lane": "bulletin",
        "tool": "board_write_post",
        "governance_tier": "T2",
    }
    assert first["post"] == {
        "room": "findings",
        "body": (
            "Index reliability checkpoint, 2026-09-07\n\n"
            "Status: Index 2.11.0 is published; router durable jobs remain a "
            "pre-release integration surface.\n\n"
            "Checked:\n"
            "- GitHub release v2.11.0 is published for Index.\n"
            "- PyPI package index-graph 2.11.0 is available.\n"
            "- Clean-install smoke reported index 2.11.0.\n\n"
            "Positive controls:\n"
            "- Synthetic router job lifecycle completed with a workspace map.\n"
            "- Traversal-shaped job ids were rejected.\n\n"
            "Held blockers:\n"
            "- Public CLI/MCP router-job wiring still waits on integration review.\n\n"
            "Does not prove:\n"
            "- Router durable jobs are released as public Index behavior.\n"
            "- Private workspaces were scanned or posted.\n\n"
            "Links:\n"
            "- Index 2.11.0 release: "
            "https://github.com/HarperZ9/index/releases/tag/v2.11.0\n"
            "- index-graph 2.11.0 on PyPI: "
            "https://pypi.org/project/index-graph/2.11.0/"
        ),
    }
    assert first["post_payload_sha256"] == canonical_sha256(first["post"])
    assert "journey_ref" not in json.dumps(first)


@pytest.mark.parametrize("field", [
    "journey_ref", "owner_ref", "grant_ref", "source_path", "raw_transcript",
])
def test_private_journey_fields_are_rejected_before_rendering(field):
    """Allowing private Journey fields would make projection a transcript leak."""
    outcome = dict(INDEX_OUTCOME)
    outcome[field] = "owner_" + "a" * 32

    with pytest.raises(OutcomeBulletinError) as failure:
        build_preview(outcome)

    assert failure.value.code == "UNSAFE_PUBLIC_OUTCOME"
    assert "owner_" not in str(failure.value)


def test_host_paths_and_unallowlisted_urls_are_rejected_without_echoing():
    """A public post must not depend on operator checkout paths or arbitrary URLs."""
    path_outcome = dict(INDEX_OUTCOME)
    path_outcome["checked"] = ["Receipt at C:/dev/private/state.json"]
    with pytest.raises(OutcomeBulletinError) as path_failure:
        build_preview(path_outcome)
    assert "C:/dev" not in str(path_failure.value)

    url_outcome = dict(INDEX_OUTCOME)
    url_outcome["links"] = [{"label": "other", "url": "https://example.com/x"}]
    with pytest.raises(OutcomeBulletinError) as url_failure:
        build_preview(url_outcome)
    assert "example.com" not in str(url_failure.value)


def test_gateway_grant_request_binds_the_preview_to_lane_call():
    """A grant for another lane or payload must fail canonical gateway binding."""
    preview = build_preview(INDEX_OUTCOME)
    request = build_gateway_grant_request(
        preview,
        journey_ref="jrn_" + "a" * 32,
        expected_event_head="b" * 64,
        client_request_id="index-outcome-20260907",
    )

    assert request["schema"] == "flywheel.gateway-operation/v1"
    assert request["operation"] == {
        "name": "bulletin",
        "tool": "board_write_post",
        "args": preview["post"],
        "governance_tier": "T2",
        "timeout": 20,
        "data_refs": [],
        "credential_refs": [],
    }
    assert set(request) == {
        "schema", "journey_ref", "expected_event_head",
        "client_request_id", "operation",
    }


def test_gateway_grant_route_accepts_the_generated_lane_call_request(tmp_path):
    """Extra preview metadata in the grant body would make publication unwirable."""
    owner = "owner_" + "a" * 32
    journey = "jrn_" + "a" * 32
    created = JourneyStore(tmp_path).create(MutationCommand(
        owner, journey, None, "create-1", "intake",
        {"legacy_label": None, "goal": "Publish public finding",
         "intake": {}, "occurred_at": "2026-09-07T12:00:00Z"},
    ))
    preview = build_preview(INDEX_OUTCOME)
    request = build_gateway_grant_request(
        preview,
        journey_ref=journey,
        expected_event_head=created.event_head_sha256,
        client_request_id="index-outcome-20260907",
    )

    proposal, status = gateway_grant_post(
        "/api/gateway-grants/prepare/lane.call",
        canonical_bytes(request),
        owner_ref=owner,
        state_root=tmp_path,
        clock=lambda: "2026-09-07T12:00:00Z",
    )

    assert status == 200
    assert proposal["tool"] == "board_write_post"
    assert proposal["destination"] == {"kind": "lane", "ref": "bulletin"}
    assert proposal["scopes"] == ["exec", "network", "plugin"]


def test_gateway_publish_envelope_authorizes_one_exact_lane_call(tmp_path):
    """The final publication body must consume only the approved lane.call grant."""
    owner = "owner_" + "a" * 32
    journey = "jrn_" + "a" * 32
    created = JourneyStore(tmp_path).create(MutationCommand(
        owner, journey, None, "create-1", "intake",
        {"legacy_label": None, "goal": "Publish public finding",
         "intake": {}, "occurred_at": "2026-09-07T12:00:00Z"},
    ))
    preview = build_preview(INDEX_OUTCOME)
    request = build_gateway_grant_request(
        preview,
        journey_ref=journey,
        expected_event_head=created.event_head_sha256,
        client_request_id="index-outcome-20260907",
    )
    proposal, status = gateway_grant_post(
        "/api/gateway-grants/prepare/lane.call",
        canonical_bytes(request),
        owner_ref=owner,
        state_root=tmp_path,
        clock=lambda: "2026-09-07T12:00:00Z",
    )
    approval, approval_status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        canonical_bytes({"proposal_ref": proposal["proposal_ref"]}),
        owner_ref=owner,
        state_root=tmp_path,
        clock=lambda: "2026-09-07T12:00:00Z",
    )
    envelope = build_gateway_publish_envelope(
        preview,
        journey_ref=journey,
        expected_event_head=created.event_head_sha256,
        client_request_id="index-outcome-20260907",
        grant_ref=approval["grant_ref"],
    )

    assert status == approval_status == 200
    authorized = authorize_gateway_operation(
        "lane.call", canonical_bytes(envelope), owner_ref=owner,
        state_root=tmp_path, clock=lambda: "2026-09-07T12:00:00Z")
    assert authorized.tool == "board_write_post"
    assert dict(authorized.destination) == {"kind": "lane", "ref": "bulletin"}
    assert dict(authorized.operation)["args"] == preview["post"]
    with pytest.raises(GatewayOperationError):
        authorize_gateway_operation(
            "lane.call", canonical_bytes(envelope), owner_ref=owner,
            state_root=tmp_path, clock=lambda: "2026-09-07T12:00:00Z")


def test_publish_uses_t2_bulletin_write_and_verifies_readback():
    """A successful write is not accepted until the public read returns same text."""
    preview = build_preview(INDEX_OUTCOME)
    calls = []

    def publisher(lane, tool, args, *, timeout, governance_tier):
        calls.append((lane, tool, args, timeout, governance_tier))
        return {"ok": True, "post": {"id": "1788722917000-test"}}

    def readback(post_id):
        return {"ok": True, "post": {"id": post_id, **preview["post"]}}

    result = publish_preview(
        preview,
        grant_ref="gnt_" + "c" * 32,
        publisher=publisher,
        readback=readback,
    )

    assert calls == [(
        "bulletin", "board_write_post", preview["post"], 20, "T2",
    )]
    assert result["status"] == "posted_readback_match"
    assert result["post_id"] == "1788722917000-test"


def test_publish_without_signed_publisher_reports_no_live_write():
    """Defaulting to unsigned HTTP MCP would fail on the live Bulletin write tool."""
    preview = build_preview(INDEX_OUTCOME)

    result = publish_preview(preview, grant_ref="gnt_" + "c" * 32)

    assert result["status"] == "publish_unavailable"
    assert result["does_not_prove"] == ["a signed Bulletin write was attempted"]


def test_publish_reports_write_and_readback_failures_without_raw_echo():
    """Publication failures must not echo downstream text that may include secrets."""
    preview = build_preview(INDEX_OUTCOME)

    write_failed = publish_preview(
        preview,
        grant_ref="gnt_" + "c" * 32,
        publisher=lambda *_a, **_k: {"error": "token C:/dev/private"},
    )
    assert write_failed["status"] == "publish_failed"
    assert "private" not in json.dumps(write_failed)

    def publisher(*_a, **_k):
        return {"ok": True, "post": {"id": "1788722917000-test"}}

    drift = publish_preview(
        preview,
        grant_ref="gnt_" + "c" * 32,
        publisher=publisher,
        readback=lambda _id: {
            "ok": True,
            "post": {"id": "1788722917000-test", "room": "scratch", "body": "changed"},
        },
    )
    assert drift["status"] == "posted_readback_drift"
    assert drift["does_not_prove"] == ["public board readback matched the requested post"]
