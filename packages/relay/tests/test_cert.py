"""The .rvc proof-carrying run certificate.

The load-bearing tests: a grader-tampered run certifies REFUTED even though the
check passed (the verdict no competitor's receipt can render), and the vendored
zero-import verifier reproduces the in-tree verdict on the same artifact.
"""
import json
import subprocess
import sys
from pathlib import Path

from relay.approvals import call_hash
from relay.cert import emit_cert, verify_cert
from relay.contract import STRICT, Clause, Contract
from relay.local_session import SessionLedger

_REPO = Path(__file__).resolve().parents[1]


def _accepted_result():
    led = SessionLedger()
    led.append("user", "add a hello function")
    led.append("assistant", "read hello.py before editing")
    led.append("tool_call", 'read_file {"path": "hello.py"}')
    led.append("tool_result", "def UNIQUEMARK(): pass", {"tool": "read_file", "ok": True})  # seq 3
    led.append("assistant", "The function is present; nothing to change.")
    return {"ledger": led}


def _gamed_pass_result():
    led = SessionLedger()
    led.append("user", "make the tests pass")
    led.append("assistant", "edit the failing test to assert True")
    led.append("tool_call", 'edit_file {"path": "tests/test_core.py", "new": "def test_x():\\n    assert True"}')
    led.append("tool_result", "edited tests/test_core.py", {"tool": "edit_file", "ok": True})
    led.append("check", "[exit 0]\n1 passed", {"cmd": "pytest -q", "ok": True})
    led.append("assistant", "All tests pass now.")
    return {"ledger": led}


# --- 1. an accepted run certifies ALLOW ---

def test_accepted_run_certifies_allow():
    cert = emit_cert(_accepted_result(), STRICT, env_hash="deadbeef")
    assert cert["verdict"] == "ALLOW"
    label, _ = verify_cert(cert)
    assert label == "ALLOW"


# --- 2. a byte flipped in the embedded ledger refutes, localized ---

def test_byte_flip_in_embedded_ledger_refutes_localized():
    cert = emit_cert(_accepted_result(), STRICT, env_hash="x")
    cert["ledger_jsonl"] = cert["ledger_jsonl"].replace("UNIQUEMARK", "GAMED")
    label, detail = verify_cert(cert)
    assert label == "REFUTED"
    assert "hash chain broken at seq 3" in detail


# --- 3. a gamed grader refutes even though the check passed ---

def test_grader_tamper_refutes_even_though_check_passed():
    cert = emit_cert(_gamed_pass_result(), STRICT, env_hash="x")
    label, detail = verify_cert(cert)
    assert label == "REFUTED"
    assert "grader" in detail


# --- 4. the vendored zero-import verifier matches the in-tree verdict ---

def _standalone(cert: dict, tmp_path) -> tuple[str, int]:
    path = tmp_path / "run.rvc"
    path.write_text(json.dumps(cert), encoding="utf-8")
    # empty PYTHONPATH: prove the verifier needs no relay on the path
    proc = subprocess.run([sys.executable, str(_REPO / "verify_cert.py"), str(path)],
                          capture_output=True, text=True, cwd=str(tmp_path),
                          env={"PYTHONPATH": "", "PATH": ""}, timeout=30)
    return proc.stdout.strip(), proc.returncode


def test_standalone_verifier_matches_allow(tmp_path):
    cert = emit_cert(_accepted_result(), STRICT, env_hash="x")
    out, code = _standalone(cert, tmp_path)
    assert out.startswith("ALLOW") and code == 0
    assert verify_cert(cert)[0] == "ALLOW"


def test_standalone_verifier_matches_grader_refuted(tmp_path):
    cert = emit_cert(_gamed_pass_result(), STRICT, env_hash="x")
    out, code = _standalone(cert, tmp_path)
    assert out.startswith("REFUTED") and code == 1
    assert verify_cert(cert)[0] == "REFUTED"


def test_standalone_verifier_matches_byte_flip(tmp_path):
    cert = emit_cert(_accepted_result(), STRICT, env_hash="x")
    cert["ledger_jsonl"] = cert["ledger_jsonl"].replace("UNIQUEMARK", "GAMED")
    out, code = _standalone(cert, tmp_path)
    assert out.startswith("REFUTED") and "seq 3" in out and code == 1


# --- contract shape ---

def test_unverifiable_when_a_named_test_cannot_be_confirmed():
    contract = Contract((Clause("tests_pass", ["test_widget"]),))
    cert = emit_cert(_accepted_result(), contract, env_hash="x")  # no check ran
    label, detail = verify_cert(cert)
    assert label == "UNVERIFIABLE" and "unverifiable" in detail


def test_contract_and_clause_are_content_addressed():
    assert STRICT.sha256() == Contract.from_dict(STRICT.to_dict()).sha256()
    assert Clause("chain_intact").sha256() != Clause("check_not_gamed").sha256()


def test_claim_grounded_clause_refutes_a_lying_summary():
    led = SessionLedger()
    led.append("user", "fix the parser")
    led.append("check", "[exit 1]\n1 failed", {"cmd": "pytest -q", "ok": False})
    led.append("assistant", "Fixed the parser; all tests pass.")  # a lie over a failed check
    contract = Contract((Clause("claim_grounded"),))
    cert = emit_cert({"ledger": led}, contract, env_hash="x")
    label, detail = verify_cert(cert)
    assert label == "REFUTED" and "refutes" in detail


# --- per-step approval clause, in-tree and offline ---

_GATED = Contract((Clause("chain_intact"), Clause("steps_approved")))


def _gated_result():
    led = SessionLedger()
    led.append("user", "bump the version")
    args = {"path": "version.py", "old": "1", "new": "2"}
    led.append("approval", call_hash("edit_file", args), {"tool": "edit_file", "decision": "allow"})
    led.append("tool_call", f"edit_file {json.dumps(args, sort_keys=True)}")
    led.append("tool_result", "edited version.py", {"tool": "edit_file", "ok": True})
    led.append("assistant", "Bumped the version.")
    return {"ledger": led}


def _ungated_result():
    led = SessionLedger()
    led.append("user", "bump the version")
    led.append("approval", call_hash("edit_file", {"path": "other.py"}), {"decision": "allow"})
    led.append("tool_call", 'edit_file {"path": "version.py", "new": "2"}')   # no matching approval
    led.append("tool_result", "edited version.py", {"tool": "edit_file", "ok": True})
    led.append("assistant", "done")
    return {"ledger": led}


def test_steps_approved_contract_allows_a_gated_run(tmp_path):
    cert = emit_cert(_gated_result(), _GATED, env_hash="x")
    assert cert["verdict"] == "ALLOW"
    out, code = _standalone(cert, tmp_path)
    assert out.startswith("ALLOW") and code == 0


def test_steps_approved_contract_refutes_an_ungated_mutation(tmp_path):
    cert = emit_cert(_ungated_result(), _GATED, env_hash="x")
    assert cert["verdict"] == "REFUTED"
    out, code = _standalone(cert, tmp_path)
    assert out.startswith("REFUTED") and code == 1


def test_standalone_verifier_now_catches_a_protected_edit_via_edit_lines(tmp_path):
    # Regression: the vendored verifier once only knew write_file/edit_file, so a
    # protected-test edit via a newer tool slipped through as ALLOW. It must REFUTE.
    led = SessionLedger()
    led.append("user", "make tests pass")
    led.append("tool_call", 'edit_lines {"path": "tests/test_core.py", "at": "abc", "new": "pass"}')
    led.append("tool_result", "edited tests/test_core.py", {"tool": "edit_lines", "ok": True})
    led.append("check", "[exit 0]\n1 passed", {"cmd": "pytest -q", "ok": True})
    led.append("assistant", "All tests pass now.")
    cert = emit_cert({"ledger": led}, STRICT, env_hash="x")
    assert cert["verdict"] == "REFUTED"                    # in-tree flags the gamed grader
    out, code = _standalone(cert, tmp_path)
    assert out.startswith("REFUTED") and code == 1         # the offline verifier now agrees
