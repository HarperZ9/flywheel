"""The standalone twin of verify_receipts, exercised as a stranger would run it.

These tests build a real bundle with a domain CLI, then invoke the vendored
``verify_bundle.py`` at the repo root as a subprocess. The verifier re-reads the
sealed artifacts and re-derives ``bundle_hash`` with nothing from the package on
its path, so a reviewer holding only the bundle reaches the same verdict.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from proof_surface.agent_action.cli import main

_VERIFIER = Path(__file__).resolve().parents[1] / "verify_bundle.py"

_AUTH = {
    "authorization_version": "0.1",
    "receipt_id": "auth-1",
    "kind": "authorization-grant",
    "principal": {"id": "user:zain"},
    "agent": {"id": "agent:claude"},
    "intent": "write",
    "scope": {
        "allowed_actions": ["fs.write"],
        "allowed_targets": ["/work/config.json"],
    },
    "granted_at": "2020-01-01T00:00:00+00:00",
    "expires_at": "2999-01-01T00:00:00+00:00",
    "revoked": False,
}
_TRACE = {
    "trace_id": "t1",
    "service": "demo",
    "spans": [
        {
            "span_id": "s2",
            "parent_span_id": None,
            "name": "write",
            "kind": "client",
            "start_unix_ns": 0,
            "end_unix_ns": 1,
            "status": {"code": "ok", "message": ""},
            "attributes": {
                "actor.id": "user:zain",
                "tool.name": "fs",
                "action.kind": "fs.write",
                "action.target": "/work/config.json",
                "side_effect.class": "write",
                "content.sha256": "a" * 64,
                "after.sha256": "c" * 64,
            },
            "events": [],
        }
    ],
}


def _build_bundle(tmp_path: Path) -> Path:
    trace = tmp_path / "t.json"
    trace.write_text(json.dumps(_TRACE), encoding="utf-8")
    auth = tmp_path / "a.json"
    auth.write_text(json.dumps(_AUTH), encoding="utf-8")
    out = tmp_path / "out"
    rc = main(
        [
            "--trace",
            str(trace),
            "--authorization",
            str(auth),
            "--claim",
            "c",
            "--scope",
            "s",
            "--packet-id",
            "pkt-1",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    assert (out / "bundle.json").exists()
    return out


def _verify(bundle_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_VERIFIER), str(bundle_dir)],
        capture_output=True,
        text=True,
        cwd=str(bundle_dir.parent),
    )


def test_clean_bundle_matches(tmp_path):
    out = _build_bundle(tmp_path)
    result = _verify(out)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_tampered_artifact_drifts(tmp_path):
    out = _build_bundle(tmp_path)
    report = out / "report.md"
    report.write_text(report.read_text(encoding="utf-8") + "\ntamper\n", encoding="utf-8")
    result = _verify(out)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "DRIFT" in result.stdout
    assert "report.md" in result.stdout


def test_missing_bundle_is_unverifiable(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _verify(empty)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "UNVERIFIABLE" in result.stdout
