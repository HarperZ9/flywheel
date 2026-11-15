"""The portable proof bundle: a content-addressed, re-checkable manifest."""

from __future__ import annotations

import json

from proof_surface._bundle import verify_receipts
from proof_surface.agent_action.cli import main
from proof_surface.cli import main as proof_main

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


def _run(tmp_path, out_name):
    trace = tmp_path / "t.json"
    trace.write_text(json.dumps(_TRACE), encoding="utf-8")
    auth = tmp_path / "a.json"
    auth.write_text(json.dumps(_AUTH), encoding="utf-8")
    out = tmp_path / out_name
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
    return json.loads((out / "bundle.json").read_text(encoding="utf-8"))


def test_bundle_manifest_lists_every_artifact_with_a_digest(tmp_path):
    bundle = _run(tmp_path, "out")
    assert bundle["domain"] == "agent-action"
    assert bundle["packet_id"] == "pkt-1"
    assert len(bundle["bundle_hash"]) == 64
    names = {f["name"] for f in bundle["files"]}
    assert names >= {
        "packet.json",
        "report.md",
        "crucible-thesis.json",
        "crucible-measurements.json",
    }
    for f in bundle["files"]:
        assert len(f["sha256"]) == 64


def test_bundle_hash_is_deterministic(tmp_path):
    a = _run(tmp_path, "out-a")
    b = _run(tmp_path, "out-b")
    assert a["bundle_hash"] == b["bundle_hash"]


def _blob(iss):
    return iss.path + " " + iss.message


def test_verify_receipts_accepts_an_untampered_bundle(tmp_path):
    _run(tmp_path, "out")
    assert verify_receipts(tmp_path / "out") == []


def test_verify_receipts_catches_a_mutated_artifact(tmp_path):
    _run(tmp_path, "out")
    report = tmp_path / "out" / "report.md"
    report.write_text(report.read_text(encoding="utf-8") + "\ntamper\n", encoding="utf-8")
    issues = verify_receipts(tmp_path / "out")
    assert any("report.md" in _blob(i) for i in issues)


def test_verify_receipts_catches_a_tampered_recorded_digest(tmp_path):
    _run(tmp_path, "out")
    bundle_path = tmp_path / "out" / "bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["files"][0]["sha256"] = "b" * 64
    bundle_path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    issues = verify_receipts(tmp_path / "out")
    name = bundle["files"][0]["name"]
    assert any(name in _blob(i) for i in issues)


def test_verify_receipts_catches_a_tampered_bundle_hash(tmp_path):
    _run(tmp_path, "out")
    bundle_path = tmp_path / "out" / "bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["bundle_hash"] = "c" * 64
    bundle_path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    issues = verify_receipts(tmp_path / "out")
    assert any("bundle_hash" in i.path for i in issues)


def test_verify_receipts_catches_a_missing_artifact(tmp_path):
    _run(tmp_path, "out")
    (tmp_path / "out" / "report.md").unlink()
    issues = verify_receipts(tmp_path / "out")
    assert any("report.md" in _blob(i) for i in issues)


def test_verify_receipts_reports_a_missing_bundle(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    issues = verify_receipts(empty)
    assert any("bundle.json" in _blob(i) for i in issues)


def test_cli_verify_reports_match_on_a_clean_bundle(tmp_path, capsys):
    _run(tmp_path, "out")
    capsys.readouterr()
    rc = proof_main(["verify", str(tmp_path / "out")])
    result = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert result["verdict"] == "MATCH"


def test_cli_verify_reports_drift_on_a_tampered_artifact(tmp_path, capsys):
    _run(tmp_path, "out")
    (tmp_path / "out" / "report.md").write_text("tampered", encoding="utf-8")
    capsys.readouterr()
    rc = proof_main(["verify", str(tmp_path / "out")])
    result = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert result["verdict"] == "DRIFT"
    assert result["issues"]


def test_cli_verify_reports_unverifiable_without_a_manifest(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    rc = proof_main(["verify", str(empty)])
    result = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert result["verdict"] == "UNVERIFIABLE"
