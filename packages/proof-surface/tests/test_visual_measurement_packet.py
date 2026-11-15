"""Tests for the visual-measurement proof packet validator.

A read-only visual/color/display measurement packet: an artifact digest, declared
color assumptions, measured metrics with tolerances, honest display caveats, and a
re-derivable verdict. The non-mutation boundary is a structural invariant:
`read_only` must be true (this v0 packet never applies a LUT/ICC/DDC change).
"""

from __future__ import annotations

from proof_surface.visual_measurement import validate_visual_measurement_packet

_HEX = "a" * 64


def _valid() -> dict:
    return {
        "version": "visual-measurement-proof-packet/v0",
        "packet_id": "vm-1",
        "claim": "The rendered swatch measured within tolerance of the sRGB target.",
        "scope": "One image artifact; sensorless display estimate; read-only.",
        "artifact": {
            "name": "swatch.png",
            "sha256": _HEX,
            "kind": "image",
            "width": 1024,
            "height": 1024,
        },
        "color": {"color_space": "sRGB", "transfer": "sRGB", "white_point": "D65"},
        "read_only": True,
        "measurements": [
            {
                "metric": "delta_e_2000",
                "value": 1.8,
                "unit": "dE",
                "target": 0.0,
                "tolerance": 2.0,
                "deviation": 1.8,
                "method": "build-color",
                "evidence": [_HEX],
            }
        ],
        "display_caveats": ["sensorless estimate; not sensor-measured"],
        "verdicts": {
            "overall": "MATCH",
            "per_metric": [{"metric": "delta_e_2000", "status": "MATCH"}],
        },
        "uncertainty": [],
        "decision_summary": {
            "decision": "approve",
            "reason": "measured within tolerance of the targets",
            "confidence": "high",
            "missing_evidence": [],
            "next_action": "proceed",
        },
    }


def _paths(issues):
    return [i.path for i in issues]


def test_valid_packet_has_no_issues():
    assert validate_visual_measurement_packet(_valid()) == []


def test_unknown_root_field_rejected():
    d = _valid()
    d["surprise"] = 1
    assert any("surprise" in p for p in _paths(validate_visual_measurement_packet(d)))


def test_read_only_false_is_rejected_non_mutation_boundary():
    d = _valid()
    d["read_only"] = False
    assert any("read_only" in p for p in _paths(validate_visual_measurement_packet(d)))


def test_bad_artifact_digest_rejected():
    d = _valid()
    d["artifact"]["sha256"] = "nope"
    assert any(
        "artifact.sha256" in p for p in _paths(validate_visual_measurement_packet(d))
    )


def test_non_positive_tolerance_rejected():
    d = _valid()
    d["measurements"][0]["tolerance"] = 0
    assert any("tolerance" in p for p in _paths(validate_visual_measurement_packet(d)))


def test_metric_without_per_metric_verdict_is_flagged():
    d = _valid()
    d["verdicts"]["per_metric"] = []
    issues = validate_visual_measurement_packet(d)
    assert any("per_metric" in i.path and "delta_e_2000" in i.message for i in issues)


def test_unknown_overall_verdict_rejected():
    d = _valid()
    d["verdicts"]["overall"] = "PROBABLY"
    assert any("overall" in p for p in _paths(validate_visual_measurement_packet(d)))


def test_authority_language_rejected():
    d = _valid()
    d["claim"] = "This display is CERTIFIED accurate."
    assert validate_visual_measurement_packet(d) != []


def test_forbidden_field_rejected():
    d = _valid()
    d["color"]["prefire"] = {"x": 1}
    assert any("prefire" in p for p in _paths(validate_visual_measurement_packet(d)))
