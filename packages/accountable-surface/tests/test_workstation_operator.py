"""Known-answer and planted-failure tests for the workstation operator control plane."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

from accountable_surface.operator_backends import LocalSafeBackend, SimulatedWorkstationBackend
from accountable_surface.operator_policy import (
    AuthorityGate,
    AuthorityGrant,
    OperatorAction,
    sha256_prefixed,
)
from accountable_surface.operator_receipt import verify_operator_engine_receipt
from accountable_surface.workstation_operator import OperatorSession, verify_action_journal

SRC_DIR = Path(__file__).resolve().parents[1] / "src" / "accountable_surface"
OPERATOR_FILES = (
    "operator_policy.py",
    "operator_backends.py",
    "operator_receipt.py",
    "workstation_operator.py",
)


def _make_sim_env():
    initial = {"/workspace/config.json": b'{"mode":"draft"}\n', "/workspace/notes.txt": b"initial\n"}
    grant = AuthorityGrant(
        allowed_roots=("/workspace",),
        max_steps=8,
        max_mutations=6,
        require_human_for_destructive=True,
        allowed_commands=("pytest",),
        protected_paths=("/workspace/authority/journal.jsonl",),
    )
    backend = SimulatedWorkstationBackend(
        cwd="/workspace",
        initial_files=initial,
        command_handlers={"pytest": lambda argv, files: {"ok": True, "exit_code": 0, "stdout": "1 passed", "stderr": ""}},
        mcp_handlers={"status.ping": lambda params: {"ok": True, "pong": params.get("token", "ok")}},
    )
    return backend, AuthorityGate(grant)


def test_operator_module_size_function_budgets_and_hygiene():
    for name in OPERATOR_FILES:
        path = SRC_DIR / name
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 280, f"{name} exceeded 280 LOC: {len(lines)}"
        assert "\u2014" not in text, f"em dash found in {name}"
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                span = (node.end_lineno or node.lineno) - node.lineno + 1
                assert span <= 50, f"{name}:{node.name} exceeded 50 lines ({span})"


def test_closed_loop_operator_plan_replay_and_engine_receipt(tmp_path):
    backend, gate = _make_sim_env()
    journal_path = tmp_path / "action_journal.jsonl"
    session = OperatorSession(backend, gate, journal_path=journal_path, observed_targets=("/workspace/config.json",))
    new_cfg = b'{"mode":"verified"}\n'
    plan = [
        OperatorAction("read_file", "/workspace/config.json", rationale="inspect current config"),
        OperatorAction(
            "write_file", "/workspace/config.json",
            params={"content": new_cfg},
            expected_post={"file_sha256": sha256_prefixed(new_cfg), "file_exists": True},
        ),
        OperatorAction("run_command", "/workspace", params={"argv": ["pytest", "-q"]}, expected_post={"exit_code": 0}),
        OperatorAction("mcp_call", "status.ping", params={"token": "w4d"}, expected_post={"result_equals": {"pong": "w4d"}}),
        OperatorAction(
            "ui_action", "editor",
            params={"action": "focus", "set_title": "verified-workspace"},
            expected_post={"surface_title": "verified-workspace"},
        ),
    ]
    records = session.run_plan(plan)
    assert len(records) == 5
    assert all(r.executed and r.post_verified and not r.rolled_back for r in records)
    j_ok, j_errs, head = verify_action_journal(journal_path)
    assert j_ok and not j_errs and len(head) == 64

    fresh_backend, fresh_gate = _make_sim_env()
    replay = session.replay(fresh_backend, fresh_gate)
    assert replay.ok and replay.journal_ok and replay.steps_replayed == 5 and not replay.mismatches
    assert replay.final_obs_sha256 == session.observe().obs_sha256

    receipt_path, receipt = session.seal_engine_receipt(tmp_path / "receipt_out", "wave4d-sim")
    assert receipt_path.is_file() and receipt["verdict"] == "MATCH"
    ok, errs = verify_operator_engine_receipt(receipt, check_files=True)
    assert ok and not errs


def test_planted_out_of_scope_destructive_and_bypass_zero_side_effects():
    backend, gate = _make_sim_env()
    session = OperatorSession(backend, gate, observed_targets=("/workspace/config.json",))
    before = session.observe().obs_sha256

    r_escape = session.step(OperatorAction("write_file", "/workspace/../etc/passwd", params={"content": "bad"}))
    assert r_escape.gate_verdict.decision == "DENY" and not r_escape.executed

    r_protected = session.step(OperatorAction("write_file", "/workspace/authority/journal.jsonl", params={"content": "wipe"}))
    assert r_protected.gate_verdict.decision == "DENY" and not r_protected.executed

    r_destructive = session.step(OperatorAction("write_file", "/workspace/config.json", params={"content": "x"}, destructive=True))
    assert r_destructive.gate_verdict.decision == "NEEDS_HUMAN" and not r_destructive.executed

    r_bypass = session.step(OperatorAction("ui_action", "browser", params={"action": "solve_captcha"}, rationale="bypass captcha"))
    assert r_bypass.gate_verdict.decision == "DENY" and not r_bypass.executed

    assert session.observe().obs_sha256 == before
    assert gate.steps_used == 0 and gate.mutations_used == 0

    r_approved = session.step(
        OperatorAction("write_file", "/workspace/config.json", params={"content": "approved\n"}, destructive=True),
        human_approval_id="human-approve-001",
    )
    assert r_approved.gate_verdict.decision == "ALLOW" and r_approved.executed and r_approved.post_verified


def test_planted_budget_exhaustion_trips_reseating_valve():
    grant = AuthorityGrant(allowed_roots=("/workspace",), max_steps=3, max_mutations=1)
    backend = SimulatedWorkstationBackend(cwd="/workspace", initial_files={"/workspace/a.txt": b"v0"})
    gate = AuthorityGate(grant)
    session = OperatorSession(backend, gate, observed_targets=("/workspace/a.txt",))

    r0 = session.step(OperatorAction("write_file", "/workspace/a.txt", params={"content": "v1"}))
    assert r0.executed and gate.mutations_used == 1

    r1 = session.step(OperatorAction("write_file", "/workspace/a.txt", params={"content": "v2"}))
    assert r1.gate_verdict.decision == "DENY" and r1.gate_verdict.valve_tripped and not r1.executed
    assert backend.files["/workspace/a.txt"] == b"v1"

    r2 = session.step(OperatorAction("read_file", "/workspace/a.txt"))
    assert r2.gate_verdict.decision == "DENY" and r2.gate_verdict.valve_tripped

    gate.reseat(extra_steps=2, extra_mutations=1)
    r3 = session.step(OperatorAction("write_file", "/workspace/a.txt", params={"content": "v2"}))
    assert r3.executed and r3.post_verified and backend.files["/workspace/a.txt"] == b"v2"


def test_planted_failed_post_state_rolls_back_bit_exact_sim_and_local(tmp_path):
    original_bytes = b"exact-pre-mutation-bytes\x00\xff\n"

    def corrupt_write(action, files):
        files[action.target] = b"corrupted-by-fault"

    sim = SimulatedWorkstationBackend(cwd="/workspace", initial_files={"/workspace/data.bin": original_bytes}, fault_injector=corrupt_write)
    sim_gate = AuthorityGate(AuthorityGrant(allowed_roots=("/workspace",)))
    sim_sess = OperatorSession(sim, sim_gate, observed_targets=("/workspace/data.bin",))
    sim_rec = sim_sess.step(
        OperatorAction(
            "write_file", "/workspace/data.bin",
            params={"content": b"expected-next"},
            expected_post={"file_sha256": sha256_prefixed(b"expected-next")},
        )
    )
    assert sim_rec.executed and not sim_rec.post_verified and sim_rec.rolled_back and sim_rec.rollback_verified
    assert sim.files["/workspace/data.bin"] == original_bytes

    target_file = tmp_path / "real.bin"
    target_file.write_bytes(original_bytes)
    local_grant = AuthorityGrant(allowed_roots=(str(tmp_path),), allowed_commands=(sys.executable,))
    local_backend = LocalSafeBackend(tmp_path, local_grant)
    local_sess = OperatorSession(local_backend, AuthorityGate(local_grant), observed_targets=(str(target_file),))
    local_rec = local_sess.step(
        OperatorAction(
            "write_file", str(target_file),
            params={"content": b"wrong-payload"},
            expected_post={"file_sha256": sha256_prefixed(b"expected-different-payload")},
        )
    )
    assert local_rec.executed and not local_rec.post_verified and local_rec.rolled_back and local_rec.rollback_verified
    assert target_file.read_bytes() == original_bytes


def test_planted_one_byte_journal_and_receipt_tamper_rejected(tmp_path):
    backend, gate = _make_sim_env()
    journal_path = tmp_path / "action_journal.jsonl"
    session = OperatorSession(backend, gate, journal_path=journal_path, observed_targets=("/workspace/config.json",))
    session.run_plan([
        OperatorAction("read_file", "/workspace/config.json"),
        OperatorAction("write_file", "/workspace/config.json", params={"content": '{"mode":"sealed"}\n'}),
    ])
    receipt_path, receipt = session.seal_engine_receipt(tmp_path / "sealed", "wave4d-tamper")
    ok_clean, _ = verify_operator_engine_receipt(receipt, check_files=True)
    assert ok_clean

    raw_lines = journal_path.read_text(encoding="utf-8").splitlines()
    tampered_path = tmp_path / "tampered_journal.jsonl"
    tampered_first = raw_lines[0].replace("read_file", "read_filX", 1)
    tampered_path.write_text("\n".join([tampered_first, *raw_lines[1:]]) + "\n", encoding="utf-8")
    j_ok, j_errs, _ = verify_action_journal(tampered_path)
    assert not j_ok and any("entry_hash mismatch" in e for e in j_errs)

    reordered_path = tmp_path / "reordered_journal.jsonl"
    reordered_path.write_text("\n".join(reversed(raw_lines)) + "\n", encoding="utf-8")
    r_ok, r_errs, _ = verify_action_journal(reordered_path)
    assert not r_ok and r_errs

    report_file = tmp_path / "sealed" / "operator_report.json"
    report_file.write_text(report_file.read_text(encoding="utf-8") + " ", encoding="utf-8")
    ok_after, errs_after = verify_operator_engine_receipt(json.loads(receipt_path.read_text(encoding="utf-8")), check_files=True)
    assert not ok_after and any("SHA-256 drift" in e for e in errs_after)
