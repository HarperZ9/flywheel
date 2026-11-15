"""eval-attempt CLI + unified dispatcher routing."""

from __future__ import annotations

import json
from pathlib import Path

from proof_surface.cli import main as dispatch
from proof_surface.eval_attempt.cli import main as cli_main

_HEX = "a" * 64

_SPEC = {
    "sources": [{"ref": "run:att-1", "sha256": _HEX}],
    "benchmark": {
        "benchmark_ref": "arc-agi-2",
        "task_id": "task-007",
        "authority_receipt": "arcprize:eval-set-v2",
    },
    "attempt": {
        "attempt_id": "att-1",
        "prompt_ref": "prompt:abc",
        "model_ref": "model:opus",
        "tool_use": [{"tool": "python"}],
        "replay_ref": "replay:xyz",
    },
    "result": {"outcome": "correct", "score": 1.0},
    "boundaries": {"had_ground_truth": False, "had_internet": False, "had_tools": True},
}


def _write_spec(tmp_path: Path) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(_SPEC), encoding="utf-8")
    return path


def test_cli_writes_artifacts_and_matches(tmp_path):
    spec = _write_spec(tmp_path)
    out = tmp_path / "artifacts"
    rc = cli_main(
        [
            "--input",
            str(spec),
            "--claim",
            "solved",
            "--scope",
            "task",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    packet = json.loads((out / "packet.json").read_text(encoding="utf-8"))
    assert packet["verdicts"]["overall"] == "MATCH"
    assert (out / "bundle.json").exists()


def test_dispatcher_routes_eval_attempt(tmp_path):
    spec = _write_spec(tmp_path)
    out = tmp_path / "artifacts"
    rc = dispatch(
        [
            "eval-attempt",
            "--input",
            str(spec),
            "--claim",
            "solved",
            "--scope",
            "t",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    assert (out / "packet.json").exists()
