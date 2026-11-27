"""Tests for NativeWin32Backend (ctypes + C11 membrane + fallback) and day-to-day operator workflows."""
from __future__ import annotations

import ast
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

from accountable_surface.action_receipt import verify_receipts
from accountable_surface.native_win32_backend import (
    WS_DRY_RUN_PLANNED,
    WS_OK,
    WS_REFUSED_EXCLUDED_WINDOW,
    WS_REFUSED_NO_GRANT,
    WS_REFUSED_OUT_OF_BOUNDS,
    WS_REFUSED_TARGET_NOT_ALLOWLISTED,
    NativeWin32Backend,
    compile_win32_surface_dll,
    fnv1a64_bytes,
    is_excluded_window_title,
)
from accountable_surface.operator_backends import create_native_win32_backend
from accountable_surface.operator_policy import AuthorityGate, AuthorityGrant, OperatorAction
from accountable_surface.operator_workflows import (
    run_workstation_routine,
    stage_application_packet,
    stage_outreach_draft,
)
from accountable_surface.workstation_operator import OperatorSession, verify_action_journal

PKG_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PKG_ROOT / "src" / "accountable_surface"
NATIVE_DIR = PKG_ROOT / "native"


def _load_verify_journal_fn():
    spec = importlib.util.spec_from_file_location("verify_journal_standalone", PKG_ROOT / "verify_journal.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.verify_journal


def test_wave34a_module_and_native_size_function_budgets_and_hygiene():
    for name in ("native_win32_backend.py", "operator_workflows.py", "operator_backends.py"):
        text = (SRC_DIR / name).read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 280, f"{name} exceeded 280 LOC"
        assert "\u2014" not in text, f"em dash found in {name}"
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                span = (node.end_lineno or node.lineno) - node.lineno + 1
                assert span <= 50, f"{name}:{node.name} exceeded 50 lines ({span})"

    for c_name in ("win32_surface.h", "win32_surface.c", "test_win32_surface.c", "workstation_native_surface.bld"):
        c_text = (NATIVE_DIR / c_name).read_text(encoding="utf-8")
        assert len(c_text.splitlines()) <= 300, f"{c_name} exceeded 300 LOC"
        assert "\u2014" not in c_text, f"em dash found in {c_name}"


def test_native_win32_backend_fallback_and_fail_closed_controls(tmp_path):
    grant = AuthorityGrant(allowed_roots=(str(tmp_path),), max_steps=16, max_mutations=12)
    backend = create_native_win32_backend(
        tmp_path,
        grant,
        dll_path=tmp_path / "nonexistent.dll",
        allowlisted_window_titles=("Accountable Workspace",),
        allowed_bounds=(0, 0, 800, 600),
    )
    assert isinstance(backend, NativeWin32Backend)
    assert not backend.native_loaded

    obs = backend.observe_native_desktop()
    assert obs["status_code"] == WS_OK
    assert obs["mode"] == "python-dryrun-fallback"
    assert len(obs["frame_hash_fnv1a64"]) == 16
    assert fnv1a64_bytes(b"hello") == 0xA430D84680AABD0B

    r_no_grant = backend.plan_or_dispatch_native(
        target_title="Accountable Workspace", allowlist_title="Accountable Workspace",
        x=100, y=100, grant_verified=False, dry_run=True,
    )
    assert r_no_grant["status_code"] == WS_REFUSED_NO_GRANT and not r_no_grant["executed"]

    for excluded in ("Sign in - Portal", "Cloudflare Turnstile", "reCAPTCHA", "User Account Control (UAC)", "chrome://inspect"):
        assert is_excluded_window_title(excluded)
        r_ex = backend.plan_or_dispatch_native(
            target_title=excluded, allowlist_title=excluded,
            x=100, y=100, grant_verified=True, dry_run=True,
        )
        assert r_ex["status_code"] == WS_REFUSED_EXCLUDED_WINDOW and not r_ex["executed"]

    r_unlisted = backend.plan_or_dispatch_native(
        target_title="Other App", allowlist_title="Accountable Workspace",
        x=100, y=100, grant_verified=True, dry_run=True,
    )
    assert r_unlisted["status_code"] == WS_REFUSED_TARGET_NOT_ALLOWLISTED

    r_oob = backend.plan_or_dispatch_native(
        target_title="Accountable Workspace", allowlist_title="Accountable Workspace",
        x=1200, y=900, grant_verified=True, dry_run=True,
    )
    assert r_oob["status_code"] == WS_REFUSED_OUT_OF_BOUNDS

    r_ok = backend.plan_or_dispatch_native(
        target_title="Accountable Workspace - Editor", allowlist_title="Accountable Workspace",
        x=100, y=100, grant_verified=True, dry_run=True,
    )
    assert r_ok["ok"] and r_ok["status_code"] == WS_DRY_RUN_PLANNED and r_ok["dry_run"] and not r_ok["executed"]


def test_native_c11_compiled_dll_and_selftest_when_cc_present(tmp_path):
    cc = shutil.which("gcc") or shutil.which("clang")
    if cc is None:
        return
    dll = compile_win32_surface_dll(tmp_path / "build", compiler=cc)
    assert dll is not None and dll.is_file()

    grant = AuthorityGrant(allowed_roots=(str(tmp_path),), max_steps=16, max_mutations=12)
    backend = NativeWin32Backend(
        tmp_path, grant, dll_path=dll,
        allowlisted_window_titles=("Accountable Workspace",), allowed_bounds=(0, 0, 800, 600),
    )
    assert backend.native_loaded
    obs = backend.observe_native_desktop()
    assert obs["status_code"] == WS_OK and len(obs["frame_hash_fnv1a64"]) == 16

    r_no_grant = backend.plan_or_dispatch_native(
        target_title="Accountable Workspace", allowlist_title="Accountable Workspace",
        x=50, y=50, grant_verified=False, dry_run=True,
    )
    assert r_no_grant["status_code"] == WS_REFUSED_NO_GRANT and r_no_grant["mode"] == "native-c11"

    r_captcha = backend.plan_or_dispatch_native(
        target_title="Verify Turnstile CAPTCHA", allowlist_title="Verify Turnstile CAPTCHA",
        x=50, y=50, grant_verified=True, dry_run=True,
    )
    assert r_captcha["status_code"] == WS_REFUSED_EXCLUDED_WINDOW

    r_dry = backend.plan_or_dispatch_native(
        target_title="Accountable Workspace - Draft", allowlist_title="Accountable Workspace",
        x=50, y=50, grant_verified=True, dry_run=True,
    )
    assert r_dry["ok"] and r_dry["status_code"] == WS_DRY_RUN_PLANNED and r_dry["events_sent"] == 0

    exe = tmp_path / ("test_win32_surface.exe" if sys.platform.startswith("win") else "test_win32_surface")
    cmd = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", str(NATIVE_DIR / "win32_surface.c"), str(NATIVE_DIR / "test_win32_surface.c"), "-o", str(exe)]
    if sys.platform.startswith("win"):
        cmd.extend(["-lgdi32", "-luser32"])
    build = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert build.returncode == 0, build.stderr
    run = subprocess.run([str(exe)], capture_output=True, text=True, check=False)
    assert run.returncode == 0 and "PASSED" in run.stdout, run.stderr


def test_outreach_draft_staging_dedupe_receipt_and_needs_human_pause(tmp_path):
    grant = AuthorityGrant(allowed_roots=(str(tmp_path),), max_steps=20, max_mutations=16)
    backend = NativeWin32Backend(tmp_path, grant, dll_path=tmp_path / "none.dll")
    journal = tmp_path / "operator_journal.jsonl"
    receipts = tmp_path / "action_receipts.jsonl"
    ledger = tmp_path / "outreach_ledger.jsonl"
    session = OperatorSession(backend, AuthorityGate(grant), journal_path=journal)

    res = stage_outreach_draft(
        session,
        recipient="maintainer@example.org",
        subject="Technical verification report for accountable-surface",
        body="Sharing a concise verification note with reproducible test commands.",
        out_dir=tmp_path / "drafts",
        ledger_path=ledger,
        action_receipts_path=receipts,
    )
    assert res["staged"] and res["needs_human"] and res["status"] == "NEEDS_HUMAN"
    assert Path(res["draft_path"]).is_file()
    assert res["receipt"] is not None

    label, _ = verify_receipts(receipts.read_text(encoding="utf-8"))
    assert label == "MATCH"

    dup = stage_outreach_draft(
        session,
        recipient="MAINTAINER@example.org",
        subject="Technical verification report for accountable-surface",
        body="Second duplicate attempt.",
        out_dir=tmp_path / "drafts",
        ledger_path=ledger,
    )
    assert dup["status"] == "REFUSED_DUPLICATE" and not dup["staged"]

    bad_style = stage_outreach_draft(
        session,
        recipient="peer@example.org",
        subject="Note",
        body="Contains forbidden \u2014 em dash.",
        out_dir=tmp_path / "drafts",
        ledger_path=ledger,
    )
    assert bad_style["status"] == "REFUSED_STYLE" and not bad_style["staged"]

    bad_excl = stage_outreach_draft(
        session,
        recipient="peer@example.org",
        subject="Campaign",
        body="Run mass_outreach with solve_captcha enabled.",
        out_dir=tmp_path / "drafts",
        ledger_path=ledger,
    )
    assert bad_excl["status"] == "REFUSED_EXCLUDED" and not bad_excl["staged"]


def test_application_packet_budgets_honest_licenses_and_captcha_halt(tmp_path):
    grant = AuthorityGrant(allowed_roots=(str(tmp_path),), max_steps=20, max_mutations=16)
    backend = NativeWin32Backend(tmp_path, grant, dll_path=tmp_path / "none.dll")
    journal = tmp_path / "app_journal.jsonl"
    session = OperatorSession(backend, AuthorityGate(grant), journal_path=journal)

    bad_lic = stage_application_packet(
        session,
        applicant_profile={"name": "Operator"},
        program_name="Grant Track",
        fields={"summary": "Short summary"},
        field_limits={"summary": {"max_chars": 100}},
        out_dir=tmp_path / "apps",
        licenses={"engine": "FAKE-LICENSE-99"},
    )
    assert bad_lic["status"] == "REFUSED_LICENSE" and not bad_lic["staged"]

    over_budget = stage_application_packet(
        session,
        applicant_profile={"name": "Operator"},
        program_name="Grant Track",
        fields={"summary": "one two three four five six"},
        field_limits={"summary": {"max_words": 4}},
        out_dir=tmp_path / "apps",
    )
    assert over_budget["status"] == "REFUSED_BUDGET" and not over_budget["staged"]

    res = stage_application_packet(
        session,
        applicant_profile={"name": "Operator", "org": "Independent Research"},
        program_name="Open Infrastructure Fellowship",
        fields={"summary": "Verified deterministic tooling with fail-closed accountability."},
        field_limits={"summary": {"max_chars": 120, "max_words": 15}},
        out_dir=tmp_path / "apps",
        flags={"captcha_present": True, "legal_attestation_required": True, "ai_generation_banned": False},
        licenses={"buildlang": "AGPL-3.0-only", "flywheel": "MIT"},
    )
    assert res["staged"] and res["needs_human"] and res["status"] == "NEEDS_HUMAN"
    assert "captcha_present" in res["halt_reasons"] and "legal_attestation_required" in res["halt_reasons"]
    packet = json.loads(Path(res["packet_path"]).read_text(encoding="utf-8"))
    assert packet["licenses"] == {"buildlang": "AGPL-3.0-only", "flywheel": "MIT"}
    j_ok, j_errs, _ = verify_action_journal(journal)
    assert j_ok and not j_errs


def test_workstation_routine_appends_verifiable_journals_match(tmp_path):
    grant = AuthorityGrant(allowed_roots=(str(tmp_path),), max_steps=20, max_mutations=16)
    backend = NativeWin32Backend(tmp_path, grant, dll_path=tmp_path / "none.dll")
    op_journal = tmp_path / "operator_journal.jsonl"
    surface_journal = tmp_path / "journal.jsonl"
    receipts = tmp_path / "receipts.jsonl"
    session = OperatorSession(backend, AuthorityGate(grant), journal_path=op_journal)

    stage_outreach_draft(
        session,
        recipient="reviewer@example.org",
        subject="Routine preflight note",
        body="Clean staged note prior to routine verification.",
        out_dir=tmp_path / "drafts",
        ledger_path=tmp_path / "ledger.jsonl",
        action_receipts_path=receipts,
    )
    routine = run_workstation_routine(
        session,
        routine_name="morning-health",
        checks=[{"name": "disk_budget", "ok": True, "detail": "healthy"}],
        action_receipts_path=receipts,
        surface_journal_path=surface_journal,
        report_path=tmp_path / "routine_report.json",
    )
    assert routine["ok"] and routine["surface_journal_hash"] is not None

    j_ok, j_errs, _ = verify_action_journal(op_journal)
    assert j_ok and not j_errs

    verify_journal = _load_verify_journal_fn()
    label, detail = verify_journal(surface_journal.read_text(encoding="utf-8"))
    assert label == "MATCH", detail

    # Confirm 1-byte tamper trips verify_journal -> DRIFT
    tampered = surface_journal.read_text(encoding="utf-8").replace("morning-health", "morning-healtX", 1)
    t_label, _ = verify_journal(tampered)
    assert t_label == "DRIFT"

    # Confirm OperatorSession also gates ui_action cleanly through NativeWin32Backend
    ui_rec = session.step(
        OperatorAction(
            "ui_action", "Accountable Workspace",
            params={"target_title": "Accountable Workspace", "allowlist_title": "Accountable Workspace", "x": 40, "y": 40, "dry_run": True},
        )
    )
    assert ui_rec.executed and ui_rec.result["status_code"] == WS_DRY_RUN_PLANNED
