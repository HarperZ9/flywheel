import json
import os
from pathlib import Path
import subprocess
import sys

from harness.journey_cli import main

NOW = "2026-08-14T12:00:00Z"
REPO = Path(__file__).resolve().parents[1]


def _run(args, root, capsys):
    code = main(args, home=root / "home", state_root=root / "state",
                evidence_root=root / "evidence", clock=lambda: NOW)
    return code, json.loads(capsys.readouterr().out)


def test_cli_prepare_approve_create_list_round_trip(tmp_path, capsys):
    """Separate CLI invocations must use durable proposal custody, not memory."""
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "intake.json").write_text(
        '{"summary":"bounded"}', encoding="utf-8")
    prepare = ["grant", "prepare", "create", "--goal", "Preserve evidence",
               "--intake-ref", "intake.json", "--client-request-id", "create-1"]
    code, proposal = _run(prepare, tmp_path, capsys)
    assert code == 0 and proposal["proposal_ref"].startswith("prp_")
    code, approved = _run(["grant", "approve-once", "--proposal-ref",
                           proposal["proposal_ref"]], tmp_path, capsys)
    assert code == 0
    create = ["journey", "create", "--goal", "Preserve evidence",
              "--intake-ref", "intake.json", "--client-request-id", "create-1",
              "--grant-ref", approved["grant_ref"]]
    code, ack = _run(create, tmp_path, capsys)
    assert code == 0 and ack["journey_ref"].startswith("jrn_")
    code, listed = _run(["journey", "list"], tmp_path, capsys)
    assert code == 0 and listed["journeys"][0]["journey_ref"] == ack["journey_ref"]


def test_prepare_and_approve_survive_separate_cli_processes(tmp_path):
    """Approval must load private proposal custody from disk in a new process."""
    evidence = tmp_path / "evidence"; evidence.mkdir()
    artifacts = tmp_path / "home" / "state" / "artifacts"; artifacts.mkdir(parents=True)
    (artifacts / "intake.json").write_text('{"summary":"bounded"}', encoding="utf-8")
    env = os.environ.copy()
    env["FLYWHEEL_HOME"] = str(tmp_path / "home")
    env["PYTHONPATH"] = str(REPO)
    prepare = subprocess.run([sys.executable, "-m", "harness.journey_cli",
        "grant", "prepare", "create", "--goal", "Preserve evidence",
        "--intake-ref", "intake.json", "--client-request-id", "create-1"],
        cwd=evidence, env=env, capture_output=True, text=True, check=False)
    proposal = json.loads(prepare.stdout)
    approve = subprocess.run([sys.executable, "-m", "harness.journey_cli",
        "grant", "approve-once", "--proposal-ref", proposal["proposal_ref"]],
        cwd=evidence, env=env, capture_output=True, text=True, check=False)
    approved = json.loads(approve.stdout)
    assert prepare.returncode == approve.returncode == 0
    assert approved["grant_ref"] == proposal["planned_grant_ref"]


def test_cli_invalid_arguments_are_fixed_json(tmp_path, capsys):
    """Argparse diagnostics must not echo secrets or host paths."""
    code, result = _run(["journey", "create", "--goal", "C:/private/secret"],
                        tmp_path, capsys)
    assert code == 2 and result["error"]["code"] == "INVALID_ARGUMENTS"
    assert "private" not in json.dumps(result)


def test_console_dispatches_grant_and_journey_to_durable_cli(monkeypatch):
    """Falling through to the checkout controller would make packaged grants unusable."""
    from harness import cli_entry, journey_cli
    seen = []
    monkeypatch.setattr(journey_cli, "main", lambda args: seen.append(args) or 7)
    monkeypatch.setattr(cli_entry.runpy, "run_path", lambda *_a, **_k: None)
    assert cli_entry.main(["grant", "approve-once", "--proposal-ref", "prp_x"]) == 7
    assert cli_entry.main(["journey", "list"]) == 7
    assert seen == [["grant", "approve-once", "--proposal-ref", "prp_x"],
                    ["journey", "list"]]
