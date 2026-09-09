import json
from types import SimpleNamespace

from scripts import run_local_finalizer_candidate_prefix_experiment as cli


def test_cli_loads_explicit_order_plan_and_passes_it_to_runner(tmp_path, monkeypatch, capsys):
    captured = {}
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps({"runtime_rows": [{"provider_role": "local_14b",
        "focused_run_ready": True, "endpoint_gate_ready": True, "blocking_gates": []}]}), encoding="utf-8")
    order_plan = {"schema": "harness.local-finalizer-candidate-prefix-order-plan/v1",
                  "orders": {"lfh-015-evidence-bound-nonleaky": ["C", "A", "B"]}}
    order_path = tmp_path / "order-plan.json"
    order_path.write_text(json.dumps(order_plan), encoding="utf-8")

    monkeypatch.setattr(cli, "_recheck_local_gate", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "build_adapter_registry", lambda matrix, roles: {"local_14b": SimpleNamespace()})
    monkeypatch.setattr(cli, "build_tasks", lambda *args: [{"task_id": "lfh-015-evidence-bound-nonleaky"}])
    monkeypatch.setattr(cli, "LocalCandidatePrefixRunner", lambda *args, **kwargs:
                        SimpleNamespace(candidate=lambda *a: None, finalizer=lambda *a: None))

    def experiment(tasks, run_root, params, **kwargs):
        captured["order_plan"] = kwargs.get("order_plan")
        return {"rows": [], "params_sha256": "p" * 64}

    monkeypatch.setattr(cli, "run_candidate_prefix_experiment", experiment)

    result = cli.main(["--source-root", str(tmp_path / "source"), "--task-set", str(tmp_path / "tasks.json"),
                       "--contract", str(tmp_path / "contract.json"), "--runtime-matrix", str(matrix_path),
                       "--endpoint-gate", str(tmp_path / "gate.json"), "--gate-run-id", "gate-run",
                       "--private-run-root", str(tmp_path / "run"), "--order-plan", str(order_path)])

    assert result == 0
    assert captured["order_plan"] == order_plan
    assert json.loads(capsys.readouterr().out)["rows"] == 0


def test_cli_missing_order_plan_fails_before_private_run_root_creation(tmp_path, monkeypatch):
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps({"runtime_rows": [{"provider_role": "local_14b",
        "focused_run_ready": True, "endpoint_gate_ready": True, "blocking_gates": []}]}), encoding="utf-8")
    run_root = tmp_path / "run"
    called = []
    monkeypatch.setattr(cli, "_recheck_local_gate", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "build_adapter_registry", lambda *args, **kwargs: called.append("adapter"))
    monkeypatch.setattr(cli, "build_tasks", lambda *args, **kwargs: called.append("tasks"))

    try:
        cli.main(["--source-root", str(tmp_path / "source"), "--task-set", str(tmp_path / "tasks.json"),
                  "--contract", str(tmp_path / "contract.json"), "--runtime-matrix", str(matrix_path),
                  "--endpoint-gate", str(tmp_path / "gate.json"), "--gate-run-id", "gate-run",
                  "--private-run-root", str(run_root), "--order-plan", str(tmp_path / "missing.json")])
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing order plan should fail before execution setup")

    assert called == []
    assert not run_root.exists()
