"""Tests for the visual-measurement Markdown report."""

from __future__ import annotations

from proof_surface.visual_measurement import (
    build_visual_measurement_packet,
    render_report,
)


def _packet(value=1.8):
    return build_visual_measurement_packet(
        artifact={
            "name": "swatch.png",
            "sha256": "a" * 64,
            "kind": "image",
            "width": 512,
            "height": 512,
        },
        color={"color_space": "sRGB", "transfer": "sRGB", "white_point": "D65"},
        metrics=[
            {
                "metric": "delta_e_2000",
                "value": value,
                "unit": "dE",
                "target": 0.0,
                "tolerance": 2.0,
                "method": "build-color",
                "evidence": ["a" * 64],
            }
        ],
        claim="The swatch measured within tolerance of the sRGB target.",
        scope="One image; sensorless; read-only.",
        packet_id="vm-1",
        display_caveats=["sensorless estimate; not sensor-measured"],
    )


def test_report_shows_verdict_metric_color_and_readonly_boundary():
    md = render_report(_packet())
    assert "MATCH" in md
    assert "delta_e_2000" in md
    assert "sRGB" in md
    assert "read-only" in md.lower()
    assert "sensorless estimate; not sensor-measured" in md


def test_report_is_a_nonempty_string():
    md = render_report(_packet())
    assert isinstance(md, str) and len(md) > 150
