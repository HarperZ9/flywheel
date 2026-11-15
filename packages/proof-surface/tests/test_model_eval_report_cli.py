"""Tests for the model-eval report + `telos proof model-eval` CLI (+ dispatch)."""

from __future__ import annotations

import json

from proof_surface.cli import main as dispatch_main
from proof_surface.model_eval import (
    build_model_eval_packet,
    render_report,
    validate_model_eval_packet,
)
from proof_surface.model_eval.cli import main

_HEX = "a" * 64
_INPUT = {
    "model": {"id": "claude-opus-4-8", "provider": "hosted", "config_hash": _HEX},
    "eval_set": {"name": "arithmetic-bench", "ref": "datasets/arith@v1", "size": 500},
    "objective": {"name": "accuracy-gate", "summary": "promote iff accuracy >= 0.90"},
    "metrics": [
        {
            "metric": "accuracy",
            "value": 0.94,
            "target": 0.90,
            "direction": "maximize",
            "tolerance": 0.01,
            "unit": "ratio",
            "method": "exact-match",
            "evidence": [_HEX],
        }
    ],
    "uncertainty": ["single eval suite; distribution shift not tested"],
}


def _packet():
    return build_model_eval_packet(
        model=_INPUT["model"],
        eval_set=_INPUT["eval_set"],
        objective=_INPUT["objective"],
        metrics=_INPUT["metrics"],
        claim="model met the accuracy objective",
        scope="offline eval",
        packet_id="me-1",
    )


def test_report_shows_decision_verdict_model_and_metric():
    md = render_report(_packet())
    assert "PROMOTE" in md
    assert "MATCH" in md
    assert "claude-opus-4-8" in md
    assert "accuracy" in md


def test_cli_emits_valid_packet_and_artifacts(tmp_path):
    inp = tmp_path / "in.json"
    inp.write_text(json.dumps(_INPUT), encoding="utf-8")
    out = tmp_path / "out"
    rc = main(
        [
            "--input",
            str(inp),
            "--claim",
            "model met the accuracy objective",
            "--scope",
            "offline eval",
            "--packet-id",
            "me-1",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    packet = json.loads((out / "packet.json").read_text(encoding="utf-8"))
    assert validate_model_eval_packet(packet) == []
    assert packet["decision"]["outcome"] == "promote"
    assert (out / "crucible-thesis.json").exists()


def test_unified_dispatcher_routes_to_model_eval(tmp_path):
    inp = tmp_path / "in.json"
    inp.write_text(json.dumps(_INPUT), encoding="utf-8")
    out = tmp_path / "out"
    rc = dispatch_main(
        [
            "model-eval",
            "--input",
            str(inp),
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
