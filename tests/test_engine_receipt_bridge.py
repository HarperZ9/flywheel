"""Unit, planted-tamper, and cross-package tests for harness.engine_receipt_bridge."""
from __future__ import annotations

import ast
import copy
import sys
from pathlib import Path

import pytest

from harness.engine_receipt_bridge import (
    IN_TOTO_STATEMENT,
    PREDICATE_TYPE,
    SCHEMA,
    build_receipt,
    make_oracle_record,
    verify_receipt,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_bridge_and_decomposed_gateway_modules_stay_within_size_budgets() -> None:
    targets = [
        ("harness/engine_receipt_bridge.py", 200),
        ("harness/gateway_state.py", 300),
        ("harness/gateway_get_handlers.py", 300),
        ("harness/gateway_post_custody.py", 300),
        ("harness/gateway_post_core.py", 300),
        ("harness/gateway_post_studio.py", 300),
        ("harness/gateway_cli.py", 300),
    ]
    for rel, max_lines in targets:
        src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        lines = src.splitlines()
        assert len(lines) <= max_lines, f"{rel} is {len(lines)} lines (limit {max_lines})"
        assert "\u2014" not in src, f"literal em-dash in {rel}"
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                span = (node.end_lineno or node.lineno) - node.lineno + 1
                assert span <= 50, f"{rel}:{node.name} is {span} lines (limit 50)"


def test_build_and_verify_match_drift_unverifiable(tmp_path: Path) -> None:
    artifact = tmp_path / "evidence.json"
    artifact.write_text('{"ok": true}\n', encoding="utf-8")

    # 1. Executed exit-0 oracle -> MATCH
    r_match = build_receipt(
        "flywheel", "flywheel", "bridge-match", tmp_path, [artifact],
        oracle_cmd=[sys.executable, "-c", "print('[PASS] all checks ok')"],
        hmac_key="test-secret-key",
    )
    assert r_match["schema"] == SCHEMA
    assert r_match["in_toto_statement_type"] == IN_TOTO_STATEMENT
    assert r_match["predicate_type"] == PREDICATE_TYPE
    assert r_match["verdict"] == "MATCH"
    ok, errs = verify_receipt(r_match, check_files=True, hmac_key="test-secret-key")
    assert ok and errs == []

    # 2. Missing oracle -> UNVERIFIABLE (fail-closed)
    r_unv = build_receipt("flywheel", "flywheel", "bridge-unv", tmp_path, [artifact])
    assert r_unv["verdict"] == "UNVERIFIABLE"
    ok_u, errs_u = verify_receipt(r_unv, check_files=True)
    assert ok_u and errs_u == []

    # 3. Non-zero exit -> DRIFT
    r_drift = build_receipt(
        "flywheel", "flywheel", "bridge-drift", tmp_path, [artifact],
        oracle=make_oracle_record(["check"], tmp_path, exit_code=1, stdout="FAIL: bad"),
    )
    assert r_drift["verdict"] == "DRIFT"
    ok_d, errs_d = verify_receipt(r_drift, check_files=True)
    assert ok_d and errs_d == []


def test_planted_tampers_are_rejected(tmp_path: Path) -> None:
    artifact = tmp_path / "report.txt"
    artifact.write_text("measured=42\n", encoding="utf-8")
    receipt = build_receipt(
        "flywheel", "flywheel", "tamper-test", tmp_path, [artifact],
        oracle=make_oracle_record(["verify"], tmp_path, exit_code=0, stdout="[PASS] ok"),
        hmac_key="k1",
    )

    # Planted 1: forged MATCH without oracle
    forged = copy.deepcopy(receipt)
    forged["oracle"] = None
    ok, errs = verify_receipt(forged)
    assert not ok and any("fail-closed" in e for e in errs)

    # Planted 2: wrong HMAC key
    ok, errs = verify_receipt(receipt, hmac_key="wrong-key")
    assert not ok and any("HMAC" in e for e in errs)

    # Planted 3: mutated subject field
    mut = copy.deepcopy(receipt)
    mut["subject"]["task_id"] = "tampered-id"
    ok, errs = verify_receipt(mut)
    assert not ok and any("digest mismatch" in e for e in errs)

    # Planted 4: 1-byte file drift on disk
    artifact.write_text("measured=43\n", encoding="utf-8")
    ok, errs = verify_receipt(receipt, check_files=True)
    assert not ok and any("artifact SHA-256 drift" in e for e in errs)


def test_crucible_gather_forum_receipts_verify_through_bridge(tmp_path: Path) -> None:
    for pkg_src in ("packages/crucible/src", "packages/gather/src", "packages/forum/src"):
        p = str(REPO_ROOT / pkg_src)
        if p not in sys.path:
            sys.path.insert(0, p)

    from crucible.engine_receipt import emit_crucible_engine_receipt
    from forum.engine_receipt import emit_forum_engine_receipt
    from gather.engine_receipt import emit_gather_engine_receipt

    art = tmp_path / "pkg_out.json"
    art.write_text('{"status": "verified"}\n', encoding="utf-8")

    r_crucible = emit_crucible_engine_receipt("crucible-1", tmp_path, [art], passed=True, pass_count=3)
    r_gather = emit_gather_engine_receipt("gather-1", tmp_path, [art], verified=True, pass_count=2)
    r_forum = emit_forum_engine_receipt("forum-1", tmp_path, [art], verified=True, pass_count=4)

    for rec in (r_crucible, r_gather, r_forum):
        assert rec["verdict"] == "MATCH"
        ok, errs = verify_receipt(rec, check_files=True)
        assert ok, f"{rec['subject']['engine']} receipt failed bridge verify: {errs}"
