"""control-certificate CLI + unified dispatcher routing."""

from __future__ import annotations

import json
from pathlib import Path

from proof_surface.cli import main as dispatch
from proof_surface.control_certificate.cli import main as cli_main

_HEX = "a" * 64

_SPEC = {
    "sources": [{"ref": "dogfood:pass-0112", "sha256": _HEX}],
    "system": {
        "description": "inverted pendulum under LQR",
        "domain": "robotics",
        "regime": "simulation",
    },
    "certificate": {"kind": "lyapunov", "name": "V(x) = x^T P x"},
    "witnesses": [
        {
            "condition": "positive-definite",
            "residual": 0.0,
            "tolerance": 1e-9,
            "method": "min eigenvalue of P",
        },
        {
            "condition": "decrease",
            "residual": 3e-7,
            "tolerance": 1e-6,
            "method": "max dV/dt over sampled states",
        },
    ],
    "negative_fixture": {
        "description": "unstable double integrator",
        "condition": "decrease",
        "residual": 0.82,
        "tolerance": 1e-6,
        "violates_certificate": True,
    },
    "sim_to_real": {"hardware_validity_claim": False, "hardware_evidence": []},
    "trajectory": {"log_sha256": _HEX, "samples": 500},
}


def _write_spec(tmp_path: Path, spec: dict) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def test_cli_writes_artifacts_and_matches(tmp_path):
    spec = _write_spec(tmp_path, _SPEC)
    out = tmp_path / "artifacts"
    rc = cli_main(
        [
            "--input",
            str(spec),
            "--claim",
            "stable on the sampled region",
            "--scope",
            "one linearized plant",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    packet = json.loads((out / "packet.json").read_text(encoding="utf-8"))
    assert packet["verdicts"]["overall"] == "MATCH"
    assert packet["sim_to_real"]["hardware_validity_claim"] is False
    assert (out / "bundle.json").exists()


def test_cli_rejects_a_sim_hardware_overclaim(tmp_path):
    bad = json.loads(json.dumps(_SPEC))
    bad["sim_to_real"] = {"hardware_validity_claim": True, "hardware_evidence": []}
    spec = _write_spec(tmp_path, bad)
    rc = cli_main(
        [
            "--input",
            str(spec),
            "--claim",
            "c",
            "--scope",
            "s",
            "--out",
            str(tmp_path / "artifacts"),
        ]
    )
    assert rc == 1


def test_dispatcher_routes_control_certificate(tmp_path):
    spec = _write_spec(tmp_path, _SPEC)
    out = tmp_path / "artifacts"
    rc = dispatch(
        [
            "control-certificate",
            "--input",
            str(spec),
            "--claim",
            "c",
            "--scope",
            "s",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    assert (out / "packet.json").exists()
