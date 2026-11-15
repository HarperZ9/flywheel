"""Calibration boundary: a read-only color surface may not claim a physical calibration.

Harvest of dogfood pass 0081 (visual-truth proof-packet refresh): `read_only=true`
stops mutation, but nothing stopped the packet *text* from claiming a display was
physically calibrated. The structured `calibration_boundary` makes the anti-overclaim
machine-checkable -- a physical_calibration_claim must disclose hardware measurement,
an instrument, mutation evidence, AND a non-read-only packet, or it is rejected.
"""

from __future__ import annotations

from proof_surface.visual_measurement import (
    build_visual_measurement_packet,
    validate_visual_measurement_packet,
)

_HEX = "a" * 64


def _packet(calibration_boundary=None, read_only=True):
    packet = build_visual_measurement_packet(
        artifact={"name": "chart.png", "sha256": _HEX, "kind": "image"},
        color={"color_space": "sRGB", "transfer": "sRGB"},
        metrics=[
            {
                "metric": "deltaE",
                "value": 1.0,
                "unit": "dE",
                "target": 1.0,
                "tolerance": 2.0,
            }
        ],
        claim="colors within tolerance",
        scope="one chart",
        packet_id="vm-cal",
        calibration_boundary=calibration_boundary,
    )
    packet["read_only"] = read_only
    return packet


def test_builder_defaults_to_an_honest_read_only_boundary():
    packet = _packet()
    cb = packet["calibration_boundary"]
    assert cb["hardware_measurement_used"] is False
    assert cb["physical_calibration_claim"] is False
    assert validate_visual_measurement_packet(packet) == []


def test_physical_calibration_claim_on_a_read_only_packet_is_rejected():
    # The core overclaim: "I calibrated your display" without ever mutating it.
    packet = _packet(
        calibration_boundary={
            "hardware_measurement_used": False,
            "physical_calibration_claim": True,
        }
    )
    issues = validate_visual_measurement_packet(packet)
    assert any("calibration_boundary" in i.path for i in issues)


def test_physical_calibration_claim_needs_full_hardware_disclosure():
    # Even claiming hardware_measurement_used is not enough on a read-only packet:
    # a real calibration mutates the display, so read_only must be false too.
    packet = _packet(
        calibration_boundary={
            "hardware_measurement_used": True,
            "physical_calibration_claim": True,
            "instrument": "i1 Display Pro",
            "mutation_evidence": ["DDC brightness set", "LUT written"],
        },
        read_only=True,
    )
    assert any(
        "calibration_boundary" in i.path
        for i in validate_visual_measurement_packet(packet)
    )


def test_calibration_boundary_flags_must_be_boolean():
    packet = _packet(
        calibration_boundary={
            "hardware_measurement_used": "no",
            "physical_calibration_claim": False,
        }
    )
    assert any(
        i.path == "$.calibration_boundary.hardware_measurement_used"
        for i in validate_visual_measurement_packet(packet)
    )


def test_calibration_boundary_is_optional():
    packet = _packet()
    del packet["calibration_boundary"]
    assert validate_visual_measurement_packet(packet) == []
