"""rollout-receipt CLI + unified dispatcher routing."""

from __future__ import annotations

import json
from pathlib import Path

from proof_surface.cli import main as dispatch
from proof_surface.rollout_receipt.cli import main as cli_main

_HEX = "a" * 64

_SPEC = {
    "sources": [{"ref": "run:r-42", "sha256": _HEX}],
    "rollout": {
        "rollout_id": "r-42",
        "policy_ref": "policy:ppo-v3",
        "checkpoint_ref": "ckpt:step-12000",
        "verifier_ref": "verifier:unit-suite",
        "reward_digest": _HEX,
        "sandbox_receipt": "sandbox:run-9",
        "dataset_mutation_ref": "ds:append-77",
    },
    "reward": {"score": 0.87, "model_ref": "model:ppo-v3"},
    "verifier": {"verdict": "MATCH", "evidence": ["unit suite exit 0"]},
    "admission": {"decision": "allow", "reasons": []},
}


def _write_spec(tmp_path: Path) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(_SPEC), encoding="utf-8")
    return path


def test_cli_writes_artifacts_and_promotes(tmp_path):
    spec = _write_spec(tmp_path)
    out = tmp_path / "artifacts"
    rc = cli_main(
        [
            "--input",
            str(spec),
            "--claim",
            "verified",
            "--scope",
            "step",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    packet = json.loads((out / "packet.json").read_text(encoding="utf-8"))
    assert packet["promotion"]["decision"] == "promote"
    assert (out / "report.md").exists()
    assert (out / "bundle.json").exists()


def test_dispatcher_routes_rollout_receipt(tmp_path):
    spec = _write_spec(tmp_path)
    out = tmp_path / "artifacts"
    rc = dispatch(
        [
            "rollout-receipt",
            "--input",
            str(spec),
            "--claim",
            "verified",
            "--scope",
            "step",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    assert (out / "packet.json").exists()
