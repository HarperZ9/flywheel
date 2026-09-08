import hashlib
import json
from datetime import timedelta

from harness.adapter_runtime_matrix import build_matrix
from scripts import run_local_finalizer_candidate_prefix_experiment as cli
from tests.adapter_runtime_fixtures import NOW, contract_fixture, gate_fixture, profile_fixture


def _sha(path):
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _gate_receipt(row):
    body = {key: value for key, value in row.items() if key not in {"receipt_hash", "latency_ms"}}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()


def test_cli_stale_gate_stops_before_adapter_registry_or_runner(tmp_path, monkeypatch, capsys):
    profiles = profile_fixture()
    profile_path = tmp_path / "profiles.json"
    profile_path.write_text(json.dumps(profiles), encoding="utf-8")
    gate = gate_fixture(profiles["profiles"][0], observed_at=(NOW - timedelta(seconds=901)).isoformat())
    gate["rows"][0]["schema"] = "harness.model-endpoint-gate.row/v1"
    gate["rows"][0]["receipt_hash"] = _gate_receipt(gate["rows"][0])
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate), encoding="utf-8")
    matrix = build_matrix(contract_fixture(profiles["profiles"][0]), contract_path="contract.json",
                          contract_sha256="contract-hash", endpoint_profiles=profiles,
                          endpoint_profiles_path=str(profile_path), endpoint_profiles_sha256=_sha(profile_path),
                          endpoint_gate=gate, endpoint_gate_path=str(gate_path),
                          endpoint_gate_sha256=_sha(gate_path), expected_gate_run_id="gate-run", now=NOW)
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    called = []
    monkeypatch.setattr(cli, "build_adapter_registry", lambda *a, **k: called.append("adapter"))
    monkeypatch.setattr(cli, "LocalCandidatePrefixRunner", lambda *a, **k: called.append("runner"))
    monkeypatch.setattr(cli, "run_candidate_prefix_experiment", lambda *a, **k: called.append("experiment"))

    result = cli.main(["--source-root", str(tmp_path / "source"), "--task-set", str(tmp_path / "tasks.json"),
                       "--contract", str(tmp_path / "contract.json"), "--runtime-matrix", str(matrix_path),
                       "--endpoint-gate", str(gate_path), "--gate-run-id", "gate-run",
                       "--private-run-root", str(tmp_path / "run")])

    assert result == 2
    assert called == []
    output = json.loads(capsys.readouterr().out)
    assert output["state"] == "local_endpoint_gate_blocked"
    assert output["provider_role"] == "local_14b"
    assert output["blocking_gates"] == ["endpoint_gate_stale"]
    assert not (tmp_path / "run" / "task-overlay").exists()
