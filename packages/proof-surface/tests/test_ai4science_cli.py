"""ai4science CLI + unified dispatcher routing."""

from __future__ import annotations

import json
from pathlib import Path

from proof_surface.ai4science.cli import main as cli_main
from proof_surface.cli import main as dispatch

_HEX = "a" * 64

_SPEC = {
    "sources": [{"ref": "arxiv:2408.06292", "sha256": _HEX}],
    "domain": "biology",
    "scientific_claim": "compound X binds target Y",
    "agent_actions": [{"action": "design assay", "tool": "benchling"}],
    "protocol": {
        "protocol_ref": "proto:1",
        "workflow_runtime": "nextflow",
        "reproducible": True,
    },
    "measurement": {
        "measured": True,
        "measurement_ref": "meas:1",
        "value": 0.4,
        "unit": "uM",
    },
    "reproduction": {"status": "INDEPENDENTLY_REPRODUCED"},
    "reviewer_objections": [],
    "negative_result": False,
}


def _write_spec(tmp_path: Path) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(_SPEC), encoding="utf-8")
    return path


def test_cli_writes_artifacts_and_reproduces(tmp_path):
    spec = _write_spec(tmp_path)
    out = tmp_path / "artifacts"
    rc = cli_main(
        [
            "--input",
            str(spec),
            "--claim",
            "reproduced",
            "--scope",
            "assay",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    packet = json.loads((out / "packet.json").read_text(encoding="utf-8"))
    assert packet["promotion"] == "REPRODUCED"
    assert (out / "bundle.json").exists()


def test_dispatcher_routes_ai4science(tmp_path):
    spec = _write_spec(tmp_path)
    out = tmp_path / "artifacts"
    rc = dispatch(
        [
            "ai4science",
            "--input",
            str(spec),
            "--claim",
            "r",
            "--scope",
            "s",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    assert (out / "packet.json").exists()
