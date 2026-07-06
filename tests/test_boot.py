"""boot falsifier (harness/boot.py — Layer-1 hydration).

The boot packet is the first thing every session acts on, so its invariants are
load-bearing: it must be deterministic for a fixed tree, collapse to DRIFT the
instant the tree changes (no stale hydration), respect its budget, and report
UNVERIFIABLE when the workspace is missing/empty. If any of these fail, every
model boots into an unreliable snapshot.
"""
from pathlib import Path

import pytest

from harness.boot import boot, verify_boot, hydrate_prompt

CORRECT = "def add(a, b):\n    return a + b\n"


def _scaffold(root: Path) -> Path:
    (root / "harness").mkdir()
    (root / "harness" / "__init__.py").write_text("")
    (root / "harness" / "loop.py").write_text("def f():\n    return 1\n")
    (root / "STATE.md").write_text(
        "# STATE\nLast updated: 2026-07-04\n\n## Phase: 2 test\n")
    (root / "tasks").mkdir()
    (root / "tasks" / "t1").mkdir()
    (root / "tasks" / "t1" / "task.json").write_text('{"task_id":"t1"}')
    return root


def test_boot_is_deterministic_for_fixed_tree(tmp_path):
    _scaffold(tmp_path)
    p1 = boot(tmp_path, budget=2000)
    p2 = boot(tmp_path, budget=2000)
    assert p1.verdict == "MATCH"
    assert p1.root_hash == p2.root_hash
    assert p1.envelope_id == p2.envelope_id


def test_boot_collapses_to_drift_on_tree_change(tmp_path):
    _scaffold(tmp_path)
    pkt = boot(tmp_path, budget=2000)
    assert pkt.verdict == "MATCH"
    (tmp_path / "harness" / "loop.py").write_text("def f():\n    return 2\n")
    assert verify_boot(pkt, tmp_path) == "DRIFT"


def test_boot_missing_root_is_unverifiable(tmp_path):
    pkt = boot(tmp_path / "nonexistent", budget=1000)
    assert pkt.verdict == "UNVERIFIABLE"
    assert pkt.failure_code == "missing_root"
    assert verify_boot(pkt, tmp_path / "nonexistent") == "UNVERIFIABLE"


def test_boot_empty_workspace_is_unverifiable(tmp_path):
    (tmp_path / "empty").mkdir()
    pkt = boot(tmp_path / "empty", budget=1000)
    assert pkt.verdict == "UNVERIFIABLE"
    assert pkt.failure_code == "empty_workspace"


def test_boot_respects_budget(tmp_path):
    _scaffold(tmp_path)
    pkt = boot(tmp_path, budget=400)
    assert pkt.packet_tokens_approx <= 400 or pkt.failure_code == "budget_exceeded"


def test_boot_summary_extracts_phase_and_state(tmp_path):
    _scaffold(tmp_path)
    pkt = boot(tmp_path, budget=2000)
    assert "Phase: 2 test" in pkt.summary["phase_line"]
    assert pkt.summary["state_updated"] == "2026-07-04"
    assert "t1" in pkt.summary["task_inventory"]


def test_hydrate_prompt_injects_ground_header(tmp_path):
    _scaffold(tmp_path)
    pkt = boot(tmp_path, budget=2000)
    out = hydrate_prompt(pkt, "do the task")
    assert out.startswith("[ground]")
    assert "do the task" in out


def test_hydrate_prompt_passthrough_on_non_match(tmp_path):
    _scaffold(tmp_path)
    pkt = boot(tmp_path / "nope", budget=1000)
    assert hydrate_prompt(pkt, "do the task") == "do the task"


def test_envelope_carries_boot_receipt(tmp_path):
    from harness.envelope import ProofEnvelope
    _scaffold(tmp_path)
    pkt = boot(tmp_path, budget=2000)
    receipt = pkt.root_receipt()
    assert receipt["stage"] == "boot"
    assert receipt["root_hash"] == pkt.root_hash
    env = ProofEnvelope(
        task_id="x", candidate="c", oracle="pytest", oracle_cmd="c",
        oracle_output_hash="h", verdict="PASS", model_ref="stub",
        seed=0, prompt_hash="p", budget_spent={}, injected_context=receipt)
    assert env.injected_context["root_hash"] == pkt.root_hash
