from __future__ import annotations

from coherence_membrane import (
    CompositeObservation,
    OBSERVED_AFTER,
    Status,
    build_external_graph,
    emet_receipt_observation,
    external_composite,
    external_report_observation,
    organ_receipt_bundle_observation,
    provenance_receipt_observations,
    raw_health_observation,
    raw_eye_observation,
)


def test_generic_external_report_is_witnessed_without_copying_raw_payload():
    report = {
        "organ": "example-organ",
        "subject": "example-subject",
        "summary": "example observed",
        "status": "observed",
        "secret_like_field": "do-not-copy",
        "data": {"safe": True},
    }

    obs = external_report_observation(report)

    assert obs.organ == "example-organ"
    assert obs.subject == "example-subject"
    assert obs.status is Status.PASS
    assert obs.data["safe"] is True
    assert obs.data["external_status"] == "observed"
    assert obs.data["report_sha256"].startswith("sha256:")
    assert "secret_like_field" not in obs.data
    assert obs.provenance.digest == obs.data["report_sha256"]


def test_raw_eye_watch_report_becomes_raw_eye_observation():
    report = {
        "samples": 3,
        "frame_present": True,
        "latest": {"luma_mean": 0.42, "fps": 60},
        "avg": {"luma_mean": 0.41, "gpu_ms": 5.5},
        "frame_metrics": {"width": 16, "height": 16, "quality_ok": True},
    }

    obs = raw_eye_observation(report, subject="RAW/live")

    assert obs.organ == "raw-eye"
    assert obs.subject == "RAW/live"
    assert obs.status is Status.PASS
    assert obs.summary == "raw eye report: frame present"
    assert obs.data["samples"] == 3
    assert obs.data["frame_present"] is True
    assert obs.data["latest_keys"] == ["fps", "luma_mean"]
    assert obs.data["avg_keys"] == ["gpu_ms", "luma_mean"]


def test_raw_health_receipt_becomes_compact_observation():
    receipt = {
        "receipt_version": "raw-health-v0",
        "organ": "eye.raw_rendering",
        "status": "pass",
        "summary": "RAW health pass",
        "runtime": {"verified": 7, "soft": 0, "attention": 0, "checks": []},
        "eyes": {
            "watch": {"samples": 1, "frame_present": True},
            "attribute": None,
        },
        "gpu_trace": {
            "status": "pass",
            "assertions": {"assertion_count": 1, "failure_count": 0},
        },
        "scope": "read-only",
        "commands": ["verify_runtime.verify", "raw_eyes.watch"],
    }

    obs = raw_health_observation(receipt, subject="RAW/live")

    assert obs.organ == "raw-health"
    assert obs.subject == "RAW/live"
    assert obs.status is Status.PASS
    assert obs.data["runtime_attention"] == 0
    assert obs.data["runtime_verified"] == 7
    assert obs.data["frame_present"] is True
    assert obs.data["gpu_trace_status"] == "pass"
    assert "checks" not in obs.data


def test_organ_receipt_bundle_becomes_compact_observation():
    bundle = {
        "organ_bundle_version": "0.1",
        "bundle_id": "orb-demo",
        "generated_at": "2026-06-19T09:10:00Z",
        "subject": "workspace-organ-health",
        "entries": [
            {
                "entry_id": "raw",
                "organ_id": "eye.raw_rendering",
                "receipt_kind": "raw-health",
                "status": "pass",
                "payload_sha256": "a" * 64,
                "summary": "RAW health pass",
            },
            {
                "entry_id": "gate",
                "organ_id": "gate.proof_surface",
                "receipt_kind": "proof-surface-gate",
                "status": "needs-human",
                "payload_sha256": "b" * 64,
                "summary": "Gate needs human attestation",
            },
        ],
        "edges": [{"from": "raw", "to": "gate", "relation": "gates"}],
    }

    obs = organ_receipt_bundle_observation(bundle)

    assert obs.organ == "organ-receipt-bundle"
    assert obs.subject == "workspace-organ-health"
    assert obs.status is Status.UNVERIFIED
    assert obs.data["bundle_id"] == "orb-demo"
    assert obs.data["entry_count"] == 2
    assert obs.data["edge_count"] == 1
    assert obs.data["organ_ids"] == ["eye.raw_rendering", "gate.proof_surface"]
    assert "entries" not in obs.data


def test_emet_receipt_preserves_closed_advisory_verdict():
    receipt = {
        "receipt_id": "emet-corroborate-demo",
        "verdict": "CORROBORATED",
        "witness": {"check": "corroborate", "self_sha256": "a" * 64},
        "subject": [{"name": "artifact.json", "digest": {"sha256": "b" * 64}}],
        "evidence": {"exit_code": 0, "stdout_verdict_line": "CORROBORATED"},
        "notes": "facts only",
    }

    obs = emet_receipt_observation(receipt)

    assert obs.organ == "emet"
    assert obs.subject == "artifact.json"
    assert obs.status is Status.PASS
    assert obs.data["verdict"] == "CORROBORATED"
    assert obs.data["check"] == "corroborate"
    assert obs.data["subject_count"] == 1
    assert "TRUSTED" not in obs.summary


def test_provenance_receipt_observations_convert_without_dependency():
    receipt = {
        "root": "sample",
        "observations": [
            {
                "sensor": "file-sensor",
                "subject": "README.md",
                "summary": "read file",
                "status": "pass",
                "provenance": {
                    "source": "README.md",
                    "digest": "sha256:" + "c" * 64,
                    "timestamp": "2026-06-19T00:00:00+00:00",
                    "confidence": "high",
                },
                "data": {"bytes": 12},
            }
        ],
        "decisions": [],
    }

    observations = provenance_receipt_observations(receipt)

    assert len(observations) == 1
    assert observations[0].organ == "provenance-sensorium:file-sensor"
    assert observations[0].subject == "README.md"
    assert observations[0].status is Status.PASS
    assert observations[0].data["receipt_root"] == "sample"


def test_external_composite_and_graph_bind_multiple_organs():
    raw = raw_eye_observation({"samples": 1, "frame_present": True})
    emet = emet_receipt_observation({"verdict": "MATCH", "subject": [{"name": "frame"}]})
    comp = external_composite([raw, emet], timestamp="2026-06-19T00:00:00+00:00")
    graph = build_external_graph(comp.components)
    manifest = graph.manifest()

    assert isinstance(comp, CompositeObservation)
    assert {obs.organ for obs in comp.components} == {"raw-eye", "emet"}
    assert graph.verify(pinned_manifest=manifest).verdict == "VALID"
    assert graph.has_confirming_look_ancestor(
        "external-observation-1",
        look_kind="observation",
        confirming_digests={raw.data["report_sha256"]},
    )
    assert OBSERVED_AFTER == "observed-after"
