"""Tests for Families 4+5: correlator, incident sheet, run BOM, partner assurance."""
from __future__ import annotations

import pytest

# --- correlator (Family 4) -----------------------------------------------

from harness.infra.correlator import (
    SCHEMA as CORR_SCHEMA,
    CorrelatedEvent,
    build_correlated_receipt,
    correlate,
)


def test_correlate_detects_external_publication():
    egress = [{
        "seal_hash": "a" * 64,
        "seal_body": {"destination": "evil.com", "port": 4444, "verdict": "UNKNOWN"},
    }]
    events = correlate(egress_events=egress, run_id="test")
    assert any(e.detection == "external-publication" for e in events)


def test_correlate_detects_repeated_probing():
    tool_calls = [{"tool": "run", "ok": "false", "source": "t1"},
                  {"tool": "run", "ok": "false", "source": "t2"},
                  {"tool": "run", "ok": "false", "source": "t3"}]
    events = correlate(tool_calls=tool_calls, run_id="test")
    assert any(e.detection == "repeated-boundary-probing" for e in events)


def test_correlate_detects_credential_access():
    tool_calls = [{"tool": "read_file", "args": "/secret/.env", "source": "t1"}]
    creds = [{"location": "/secret/.env", "secret_type": "aws_access_key"}]
    events = correlate(tool_calls=tool_calls, credential_findings=creds, run_id="t")
    assert any(e.detection == "credential-access" for e in events)


def test_correlated_receipt_sealed():
    event = CorrelatedEvent(run_id="t", detection="external-publication",
                            severity="high", destination="evil.com")
    r = build_correlated_receipt(event)
    assert r["schema"] == CORR_SCHEMA
    assert len(r["seal_hash"]) == 64


def test_correlate_detects_statistical_anomaly():
    """A spike in metric samples should trigger statistical anomaly detection."""
    # Normal baseline of 10 values around 50, then a spike to 200
    samples = [50.0, 48.0, 52.0, 49.0, 51.0, 50.0, 200.0]
    events = correlate(metric_samples={"CpuUsage": samples}, run_id="test")
    anomaly_events = [e for e in events if e.detection == "statistical-anomaly"]
    assert len(anomaly_events) >= 1
    assert "CpuUsage" in anomaly_events[0].detail


def test_correlate_detects_changepoint():
    """A clear mean shift should produce a changepoint detection."""
    samples = [1.0] * 20 + [50.0] * 20
    events = correlate(metric_samples={"NetworkConnectionRate": samples}, run_id="test")
    cp_events = [e for e in events if e.detection == "behavioral-changepoint"]
    assert len(cp_events) >= 1


# --- incident sheet (Family 4) -------------------------------------------

from harness.infra.incident_sheet import (
    IncidentSheet,
    from_correlated_event,
)


def test_incident_sheet_has_stable_id():
    sheet = IncidentSheet(incident_id="INC-test", detection_time="2026-08-01T00:00:00Z")
    assert sheet.incident_id == "INC-test"
    assert sheet.status == "detected"


def test_incident_sheet_links_related():
    sheet = IncidentSheet(incident_id="INC-1", detection_time="2026-08-01")
    sheet.link_related("INC-2")
    assert "INC-2" in sheet.related_incidents
    sheet.link_related("INC-1")
    assert "INC-1" not in sheet.related_incidents


def test_incident_sheet_status_transition():
    sheet = IncidentSheet(incident_id="INC-1", detection_time="2026-08-01")
    sheet.set_status("contained")
    assert sheet.status == "contained"
    with pytest.raises(ValueError):
        sheet.set_status("bogus")


def test_from_correlated_event():
    event = {"seal_hash": "b" * 64, "seal_body": {
        "timestamp": "2026-08-01T00:00:00Z",
        "severity": "critical",
        "run_id": "eval-001",
        "detail": "boundary crossing detected",
    }}
    sheet = from_correlated_event(event, commander="alice")
    assert sheet.incident_commander == "alice"
    assert sheet.severity == "critical"
    assert sheet.root_correlated_event == "b" * 64


# --- run BOM (Family 4) ---------------------------------------------------

from harness.infra.run_bom import (
    SCHEMA as BOM_SCHEMA,
    RunBOM,
    capture_system_prompt_hash,
    default_flywheel_bom,
)


def test_bom_has_schema():
    bom = RunBOM(run_id="test")
    assert bom.to_dict()["schema"] == BOM_SCHEMA


def test_bom_sealed():
    bom = RunBOM(run_id="test", model_name="claude-4.5")
    sealed = bom.sealed()
    assert "seal_hash" in sealed
    assert len(sealed["seal_hash"]) == 64


def test_capture_system_prompt_hash():
    h = capture_system_prompt_hash("you are a helpful assistant")
    assert len(h) == 64
    assert "helpful" not in h


def test_default_flywheel_bom():
    bom = default_flywheel_bom("eval-001")
    assert bom.run_id == "eval-001"
    assert bom.harness_version == "0.3.0"
    assert "read_file" in bom.tool_scopes


# --- partner assurance (Family 5) ----------------------------------------

from harness.infra.partner_assurance import (
    SCHEMA as PA_SCHEMA,
    PartnerAssurancePackage,
    default_package,
)


def test_partner_assurance_not_confirmed_initially():
    pkg = default_package(["PartyA", "PartyB"])
    assert pkg.all_confirmed() is False


def test_partner_assurance_confirmed_after_both():
    pkg = default_package(["PartyA", "PartyB"])
    pkg.confirm_network_state("PartyA")
    assert pkg.all_confirmed() is False
    pkg.confirm_network_state("PartyB")
    assert pkg.all_confirmed() is True


def test_partner_assurance_sealed():
    pkg = default_package(["A", "B"])
    s = pkg.sealed()
    assert s["schema"] == PA_SCHEMA
    assert len(s["seal_hash"]) == 64


def test_partner_assurance_has_stop_authority():
    pkg = default_package(["A", "B"])
    assert pkg.stop_authority_per_party["A"] is True
    assert pkg.stop_authority_per_party["B"] is True
