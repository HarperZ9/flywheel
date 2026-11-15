"""competition-attempt CLI + unified dispatcher routing."""

from __future__ import annotations

import json
from pathlib import Path

from proof_surface.cli import main as dispatch
from proof_surface.competition_attempt.cli import main as cli_main

_HEX64 = "a" * 64
_HEX40 = "b" * 40

_SPEC = {
    "sources": [{"ref": "run:comp-1", "sha256": _HEX64}],
    "challenge": {
        "challenge_ref": "challenge:sair-2026",
        "stage": "stage-1",
        "judge_repo": {
            "repo_ref": "github:example/judge",
            "head_sha": _HEX40,
            "observed_files": 12,
            "files_digest": _HEX64,
        },
    },
    "attempt": {
        "attempt_id": "att-1",
        "model_ref": "model:m-1",
        "external_model_calls": 0,
    },
    "answer_extraction": {
        "method": "boxed",
        "extracted_ref": "answers/final.txt",
        "injection_checked": True,
    },
    "certificate_layers": [
        {
            "layer": "informal-model-output",
            "status": "EXECUTED",
            "evidence_ref": "transcript:att-1",
        },
        {
            "layer": "judge-verdict",
            "status": "EXECUTED",
            "evidence_ref": "judge:run-9",
            "passing": True,
        },
    ],
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
            "the stage-1 attempt passed the pinned judge",
            "--scope",
            "one challenge, one judge revision",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    packet = json.loads((out / "packet.json").read_text(encoding="utf-8"))
    assert packet["verdicts"]["overall"] == "MATCH"
    assert packet["challenge"]["judge_repo"]["head_sha"] == _HEX40
    assert (out / "report.md").exists()
    assert (out / "crucible-thesis.json").exists()
    assert (out / "crucible-measurements.json").exists()
    assert (out / "bundle.json").exists()


def test_cli_rejects_a_fenced_layer_without_probe(tmp_path):
    bad = json.loads(json.dumps(_SPEC))
    bad["certificate_layers"].append(
        {"layer": "machine-checked-proof", "status": "UNAVAILABLE_FENCED"}
    )
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


def test_dispatcher_routes_competition_attempt(tmp_path):
    spec = _write_spec(tmp_path, _SPEC)
    out = tmp_path / "artifacts"
    rc = dispatch(
        [
            "competition-attempt",
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
