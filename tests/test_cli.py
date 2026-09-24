"""cli falsifier — the runner entry point stays usable.

Invokes harness.cli.main() on a materialized task and checks the structured
verdict + exit code. The stub proposer returns a no-op so the honest verdict is
FAIL (exit 1); the point is that the CLI plumbing runs end-to-end without
crashing and emits the expected envelope shape.
"""
import json
import sys
from pathlib import Path

import pytest

from harness.tasks_lib import REGISTRY, materialize


def test_cli_runs_and_emits_verdict(tmp_path, capsys):
    spec = REGISTRY[0]
    task_dir = materialize(spec, tmp_path / "task")
    from harness.cli import main
    rc = main([
        str(task_dir), "--search", "--no-witness",
        "--envelopes-dir", str(tmp_path / "env"),
    ])
    out = capsys.readouterr().out
    obj = json.loads(out)
    assert obj["task_id"] == spec.task_id
    assert obj["verdict"] in ("PASS", "FAIL", "BLOCKED", "UNVERIFIABLE")
    assert "chain_stages" in obj
    assert rc in (0, 1)


def test_cli_single_mode_no_search(tmp_path, capsys):
    spec = REGISTRY[1]
    task_dir = materialize(spec, tmp_path / "task")
    from harness.cli import main
    rc = main([str(task_dir), "--no-witness",
               "--envelopes-dir", str(tmp_path / "env")])
    out = capsys.readouterr().out
    obj = json.loads(out)
    assert "search" not in obj["chain_stages"]


def test_cli_with_cache_does_not_crash(tmp_path, capsys):
    spec = REGISTRY[0]
    task_dir = materialize(spec, tmp_path / "task")
    from harness.cli import main
    main([str(task_dir), "--no-witness",
          "--cache", str(tmp_path / "cache"),
          "--envelopes-dir", str(tmp_path / "env")])
    out = capsys.readouterr().out
    assert json.loads(out)["task_id"] == spec.task_id


def test_cli_boot_root_leads_chain_with_boot_stage(tmp_path, capsys,
                                                   monkeypatch):
    # --boot once raised NameError inside run_loop. The index lane is stubbed
    # so the run does not spawn an MCP server.
    import harness.boot as boot_mod
    monkeypatch.setattr(boot_mod, "_safe_context_envelope",
                        lambda *a, **k: None)
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "mod.py").write_text("X = 1\n")
    task_dir = materialize(REGISTRY[1], tmp_path / "task")
    from harness.cli import main
    rc = main([str(task_dir), "--no-witness", "--boot", str(ws),
               "--envelopes-dir", str(tmp_path / "env")])
    obj = json.loads(capsys.readouterr().out)
    assert obj["chain_stages"][0] == "boot"
    assert rc in (0, 1)
