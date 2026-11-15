"""optimization-workflow CLI + unified dispatcher routing."""

from __future__ import annotations

import json
from pathlib import Path

from proof_surface.cli import main as dispatch
from proof_surface.optimization_workflow.cli import main as cli_main

_HEX = "a" * 64

_SPEC = {
    "sources": [{"ref": "dogfood:pass-0086", "sha256": _HEX}],
    "problem": {
        "sense": "maximize",
        "objective": "sum(value_i * x_i)",
        "constraints": ["sum(resource_i * x_i) <= 10"],
        "encoding": "QUBO surrogate",
    },
    "candidate_space": {
        "variables": 6,
        "evaluated": 64,
        "feasible": 30,
        "infeasible": 34,
    },
    "baseline": {
        "method": "exact-enumeration",
        "objective_value": 36,
        "feasible": True,
        "candidate_digest": _HEX,
    },
    "solver": {
        "branch_id": "exact-0",
        "method": "exact",
        "status": "COMPLETED",
        "objective_value": 36,
        "constraint_status": "satisfied",
        "tolerance": 0.5,
        "selected": ["C", "D", "E", "F"],
    },
}


def _write_spec(tmp_path: Path) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(_SPEC), encoding="utf-8")
    return path


def test_cli_writes_artifacts_and_exits_zero(tmp_path):
    spec = _write_spec(tmp_path)
    out = tmp_path / "artifacts"
    rc = cli_main(
        [
            "--input",
            str(spec),
            "--claim",
            "exact optimum",
            "--scope",
            "toy",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    packet = json.loads((out / "packet.json").read_text(encoding="utf-8"))
    assert packet["verdicts"]["overall"] == "MATCH"
    assert (out / "report.md").exists()
    assert (out / "bundle.json").exists()


def test_dispatcher_routes_optimization_workflow(tmp_path):
    spec = _write_spec(tmp_path)
    out = tmp_path / "artifacts"
    rc = dispatch(
        [
            "optimization-workflow",
            "--input",
            str(spec),
            "--claim",
            "exact optimum",
            "--scope",
            "toy",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    assert (out / "packet.json").exists()
