from scripts.run_forum_route_receipts import build_report, parse_bool


def test_parse_bool_accepts_unknown_as_none():
    assert parse_bool("true") is True
    assert parse_bool("false") is False
    assert parse_bool("unknown") is None


def test_build_report_records_route_text_without_calling_forum():
    report = build_report(routes=["Route the closed-loop benchmark work."])

    row = report["routes"][0]
    assert report["schema"] == "harness.forum-route-receipts/v1"
    assert report["dependency_posture"].startswith("metadata-only")
    assert report["summary"]["route_count"] == 1
    assert report["summary"]["observed_route_frames"] == 0
    assert row["observation_status"] == "route_text_only"
    assert row["observed"] is False
    assert row["provider_execution_observed"] is False
    assert row["endpoint_probe_observed"] is False


def test_build_report_records_observed_route_frame_metadata():
    report = build_report(
        routes=["Route the forum receipt slice."],
        observed_decided="project-telos",
        observed_confidence=0.5,
        observed_needs_escalation=False,
        observed_domain="model-foundry",
        observed_intent="validate",
        observed_posture="architect",
        observed_proof_lane="validate",
        observed_domain_lane="model-foundry",
        observed_human_contract="Answer as a systems architect.",
    )

    row = report["routes"][0]
    assert report["summary"]["observed_route_frames"] == 1
    assert report["summary"]["mean_observed_confidence"] == 0.5
    assert row["observation_status"] == "observed_route_frame"
    assert row["observed_decided"] == "project-telos"
    assert row["observed_needs_escalation"] is False
