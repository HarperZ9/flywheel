"""conservation CLI + unified dispatcher routing."""

from __future__ import annotations

import json
from pathlib import Path

from proof_surface.cli import main as dispatch
from proof_surface.conservation.cli import main as cli_main

_HEX = "a" * 64

_SPEC = {
    "sources": [{"ref": "dogfood:pass-0106", "sha256": _HEX}],
    "transformation": {"description": "closed reaction network", "domain": "chemistry"},
    "invariant": {"name": "total mass", "declared": "sum of species amounts"},
    "witnesses": [
        {"kind": "algebraic", "drift": 0.0, "tolerance": 1e-12, "method": "l^T S == 0"},
        {"kind": "numeric", "drift": 4e-15, "tolerance": 1e-10, "method": "euler"},
    ],
    "negative_fixture": {
        "description": "leaky open network",
        "drift": 0.456,
        "tolerance": 0.01,
        "breaks_invariant": True,
    },
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
            "conserved",
            "--scope",
            "net",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    packet = json.loads((out / "packet.json").read_text(encoding="utf-8"))
    assert packet["verdicts"]["overall"] == "MATCH"
    assert (out / "bundle.json").exists()


def test_dispatcher_routes_conservation(tmp_path):
    spec = _write_spec(tmp_path)
    out = tmp_path / "artifacts"
    rc = dispatch(
        [
            "conservation",
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
