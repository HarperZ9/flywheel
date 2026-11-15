"""Tests for the `telos proof visual-measurement` CLI."""

from __future__ import annotations

import json

from proof_surface.visual_measurement import validate_visual_measurement_packet
from proof_surface.visual_measurement.cli import main

_INPUT = {
    "artifact": {
        "name": "swatch.png",
        "sha256": "a" * 64,
        "kind": "image",
        "width": 512,
        "height": 512,
    },
    "color": {"color_space": "sRGB", "transfer": "sRGB", "white_point": "D65"},
    "metrics": [
        {
            "metric": "delta_e_2000",
            "value": 1.8,
            "unit": "dE",
            "target": 0.0,
            "tolerance": 2.0,
            "method": "build-color",
            "evidence": ["a" * 64],
        }
    ],
    "display_caveats": ["sensorless estimate; not sensor-measured"],
}


def test_cli_emits_valid_packet_and_artifacts(tmp_path):
    inp = tmp_path / "in.json"
    inp.write_text(json.dumps(_INPUT), encoding="utf-8")
    out = tmp_path / "out"
    rc = main(
        [
            "--input",
            str(inp),
            "--claim",
            "The swatch measured within tolerance of sRGB.",
            "--scope",
            "One image; read-only.",
            "--packet-id",
            "vm-1",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    packet = json.loads((out / "packet.json").read_text(encoding="utf-8"))
    assert validate_visual_measurement_packet(packet) == []
    assert packet["verdicts"]["overall"] == "MATCH"
    assert (out / "report.md").exists()
    assert (out / "crucible-thesis.json").exists()
    assert (out / "crucible-measurements.json").exists()


def test_cli_returns_nonzero_when_input_missing(tmp_path):
    rc = main(
        [
            "--input",
            str(tmp_path / "nope.json"),
            "--claim",
            "c",
            "--scope",
            "s",
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert rc != 0
