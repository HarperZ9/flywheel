"""Tests for the visual-measurement packet builder + crucible bridge."""

from __future__ import annotations

from proof_surface.visual_measurement import (
    build_visual_measurement_packet,
    to_crucible_inputs,
    validate_visual_measurement_packet,
)

_ART = {
    "name": "swatch.png",
    "sha256": "a" * 64,
    "kind": "image",
    "width": 512,
    "height": 512,
}
_COLOR = {"color_space": "sRGB", "transfer": "sRGB", "white_point": "D65"}


def _metrics(value):
    return [
        {
            "metric": "delta_e_2000",
            "value": value,
            "unit": "dE",
            "target": 0.0,
            "tolerance": 2.0,
            "method": "build-color",
            "evidence": ["a" * 64],
        }
    ]


def _build(value):
    return build_visual_measurement_packet(
        artifact=_ART,
        color=_COLOR,
        metrics=_metrics(value),
        claim="The swatch measured within tolerance of the sRGB target.",
        scope="One image; sensorless; read-only.",
        packet_id="vm-1",
        display_caveats=["sensorless estimate; not sensor-measured"],
    )


def test_within_tolerance_metric_is_match():
    p = _build(1.8)
    assert validate_visual_measurement_packet(p) == []
    assert p["measurements"][0]["deviation"] == 1.8
    assert p["verdicts"]["per_metric"][0]["status"] == "MATCH"
    assert p["verdicts"]["overall"] == "MATCH"
    assert p["read_only"] is True


def test_out_of_tolerance_metric_is_drift():
    p = _build(5.0)
    assert validate_visual_measurement_packet(p) == []
    assert p["verdicts"]["per_metric"][0]["status"] == "DRIFT"
    assert p["verdicts"]["overall"] == "DRIFT"


def test_to_crucible_inputs_is_the_documented_contract():
    p = _build(1.8)
    thesis, measurements = to_crucible_inputs(p)
    assert thesis["disposition"] == "publishable"
    claim = thesis["claims"][0]
    assert claim["text"] and claim["falsification"]
    row = measurements["measurements"][0]
    assert row["claim"] == claim["text"]
    assert row["tolerance"] == 2.0
    assert row["deviation"] == 1.8
