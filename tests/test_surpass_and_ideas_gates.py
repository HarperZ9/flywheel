# SPDX-License-Identifier: MIT
"""Unit tests for harness/surpass_gate and harness/ideas_audit_bridge."""

from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path
from typing import Any

import pytest

from harness.ideas_audit_bridge import (
    HONEST_SCOPE_LIMIT as IDEAS_SCOPE_LIMIT,
)
from harness.ideas_audit_bridge import (
    REQUIRED_IDEAS_COLUMNS,
    parse_receipt_index,
    parse_score_1_to_10,
    verify_ideas_audit,
    verify_ideas_audit_files,
)
from harness.surpass_gate import (
    HONEST_SCOPE_LIMIT as SURPASS_SCOPE_LIMIT,
)
from harness.surpass_gate import (
    REQUIRED_TSV_COLUMNS,
    is_strict_finite_float,
    is_strict_int,
    verify_surpass_matrix,
    verify_surpass_matrix_files,
)


def _sample_surpass_fixture() -> tuple[bytes, dict[str, Any], set[int]]:
    header = "\t".join(REQUIRED_TSV_COLUMNS)
    rows = [
        "CS-001\tlane-a\tcomp1\tpain1\twhy1\ttgt1\tA1\tflywheel",
        "CS-002\tlane-a\tcomp2\tpain2\twhy2\ttgt2\tA2\tbuildlang",
        "CS-003\tlane-b\tcomp3\tpain3\twhy3\ttgt3\tA3\tsuperframe",
    ]
    tsv_bytes = ("\n".join([header] + rows) + "\n").encode("utf-8")
    tsv_sha = hashlib.sha256(tsv_bytes).hexdigest()
    matrix = {
        "schema": "competitive-surpass-matrix/v3/2026-11-27",
        "source_registry": {"name": "signals.tsv", "row_count": 3, "sha256": tsv_sha},
        "summary": {
            "total_signals": 3,
            "surpassed_with_receipt": 1,
            "parity_verified": 1,
            "open_next_wave_opportunity": 1,
            "combined_covered": 2,
            "surpassed_pct": 33.33,
            "parity_pct": 33.33,
            "combined_covered_pct": 66.67,
            "open_pct": 33.33,
        },
        "signals": [
            {"signal_id": "CS-001", "lane": "lane-a", "tier": "surpassed_with_receipt", "evidence_catalogue_ids": [68701]},
            {"signal_id": "CS-002", "lane": "lane-a", "tier": "parity_verified", "evidence_catalogue_ids": [68702]},
            {"signal_id": "CS-003", "lane": "lane-b", "tier": "open_next_wave_opportunity", "evidence_catalogue_ids": []},
        ],
    }
    return tsv_bytes, matrix, {68701, 68702}


def _idea_row(
    iid: str,
    status: str,
    evidence: str,
    val: str = "9",
    feas: str = "8",
) -> str:
    cols = [
        iid, "dom", "sub", f"title-{iid}", "2026-11-01", "2026-11-27", "prov",
        "5 msgs", status, "flywheel", evidence, "next", "test", "P1", "tool",
        val, feas, "flywheel",
    ]
    return "\t".join(cols)


def _sample_ideas_bytes(rows: list[str]) -> bytes:
    header = "\t".join(REQUIRED_IDEAS_COLUMNS)
    return ("\n".join([header] + rows) + "\n").encode("utf-8")


def test_surpass_clean_pass_and_deterministic_attestation() -> None:
    tsv_b, mat, known = _sample_surpass_fixture()
    r1 = verify_surpass_matrix(tsv_b, mat, known_catalogue_ids=known, expected_count=3)
    r2 = verify_surpass_matrix(tsv_b, mat, known_catalogue_ids=known, expected_count=3)
    assert r1.passed and r1.total_signals == 3 and r1.surpassed_count == 1
    assert r1.parity_count == 1 and r1.open_count == 1 and r1.unique_catalogue_ids == 2
    assert len(r1.surpass_attestation_sha256) == 64
    assert r1.surpass_attestation_sha256 == r2.surpass_attestation_sha256


def test_surpass_rejects_forged_catalogue_id() -> None:
    tsv_b, mat, known = _sample_surpass_fixture()
    mat["signals"][0]["evidence_catalogue_ids"] = [999999]
    rep = verify_surpass_matrix(tsv_b, mat, known_catalogue_ids=known, expected_count=3)
    assert not rep.passed and any("forged" in v for v in rep.violations)


def test_surpass_rejects_missing_row_and_partition_break() -> None:
    tsv_b, mat, known = _sample_surpass_fixture()
    mat["signals"] = mat["signals"][:2]
    rep = verify_surpass_matrix(tsv_b, mat, known_catalogue_ids=known, expected_count=3)
    assert not rep.passed and any("partition" in v for v in rep.violations)


def test_surpass_rejects_incomplete_sequence() -> None:
    tsv_b, mat, known = _sample_surpass_fixture()
    rep = verify_surpass_matrix(tsv_b, mat, known_catalogue_ids=known, expected_count=4)
    assert not rep.passed and any("completeness" in v for v in rep.violations)


def test_surpass_rejects_tampered_tsv_digest() -> None:
    tsv_b, mat, known = _sample_surpass_fixture()
    mat["source_registry"]["sha256"] = "0" * 64
    rep = verify_surpass_matrix(tsv_b, mat, known_catalogue_ids=known, expected_count=3)
    assert not rep.passed and any("sha256 mismatch" in v for v in rep.violations)


def test_surpass_rejects_lane_mismatch() -> None:
    tsv_b, mat, known = _sample_surpass_fixture()
    mat["signals"][1]["lane"] = "wrong-lane"
    rep = verify_surpass_matrix(tsv_b, mat, known_catalogue_ids=known, expected_count=3)
    assert not rep.passed and any("lane mismatch" in v for v in rep.violations)


@pytest.mark.parametrize("bad_pct", [math.nan, math.inf, -math.inf, True, -1.0, 101.0])
def test_surpass_rejects_non_finite_and_bool_pct(bad_pct: Any) -> None:
    tsv_b, mat, known = _sample_surpass_fixture()
    mat["summary"]["surpassed_pct"] = bad_pct
    rep = verify_surpass_matrix(tsv_b, mat, known_catalogue_ids=known, expected_count=3)
    assert not rep.passed


@pytest.mark.parametrize("bad_id", [True, False, 0, -5, 68701.5, "68701"])
def test_surpass_rejects_invalid_catalogue_id_types(bad_id: Any) -> None:
    tsv_b, mat, known = _sample_surpass_fixture()
    mat["signals"][0]["evidence_catalogue_ids"] = [bad_id]
    rep = verify_surpass_matrix(tsv_b, mat, known_catalogue_ids=known, expected_count=3)
    assert not rep.passed


def test_surpass_rejects_bool_summary_count_and_empty_evidence() -> None:
    tsv_b, mat, known = _sample_surpass_fixture()
    m1 = copy.deepcopy(mat)
    m1["summary"]["surpassed_with_receipt"] = True
    assert not verify_surpass_matrix(tsv_b, m1, known_catalogue_ids=known, expected_count=3).passed
    m2 = copy.deepcopy(mat)
    m2["signals"][0]["evidence_catalogue_ids"] = []
    assert not verify_surpass_matrix(tsv_b, m2, known_catalogue_ids=known, expected_count=3).passed


def test_surpass_rejects_bad_inputs_and_file_roundtrip(tmp_path: Path) -> None:
    assert not verify_surpass_matrix(b"\xff\xfe", {}, expected_count=3).passed
    assert not verify_surpass_matrix(b"", {}, expected_count=True).passed
    assert not verify_surpass_matrix_files(tmp_path / "a.tsv", tmp_path / "b.json").passed
    tsv_b, mat, known = _sample_surpass_fixture()
    tp, mp = tmp_path / "s.tsv", tmp_path / "m.json"
    tp.write_bytes(tsv_b)
    import json
    mp.write_text(json.dumps(mat), encoding="utf-8")
    ok = verify_surpass_matrix_files(tp, mp, known_catalogue_ids=known, expected_count=3)
    assert ok.passed and is_strict_int(3) and not is_strict_int(True)
    assert is_strict_finite_float(1.5) and not is_strict_finite_float(math.nan)


def test_ideas_clean_verified_and_unverified_partition() -> None:
    raw = _sample_ideas_bytes([
        _idea_row("A1", "BUILT", "catalogue_id: 68701; ok.json"),
        _idea_row("A2", "BUILT", "catalogue_id: 68702; drift.json"),
        _idea_row("A3", "BUILT", "no receipt cited"),
        _idea_row("A4", "PARTIAL", "in progress"),
    ])
    rep = verify_ideas_audit(
        raw,
        known_catalogue_ids={68701, 68702},
        known_json_names={"ok.json", "drift.json"},
        verified_tokens={"cid:68701": True, "cid:68702": False},
    )
    assert rep.passed and rep.built_count == 3 and rep.partial_count == 1
    assert rep.verified_match_count == 1 and rep.unverified_count == 2
    assert rep.unverified_no_receipt_ids == ("A3",)
    assert rep.unverified_drift_ids == ("A2",)
    assert len(rep.ideas_attestation_sha256) == 64


def test_ideas_strict_mode_rejects_unverified_built_rows() -> None:
    raw = _sample_ideas_bytes([_idea_row("A1", "BUILT", "no receipt")])
    rep = verify_ideas_audit(raw, known_catalogue_ids={68701}, require_all_built_verified=True)
    assert not rep.passed and any("unverified_built_rows" in v for v in rep.violations)


def test_ideas_rejects_forged_catalogue_id() -> None:
    raw = _sample_ideas_bytes([_idea_row("A1", "BUILT", "catalogue_id: 999999")])
    rep = verify_ideas_audit(raw, known_catalogue_ids={68701})
    assert not rep.passed and rep.forged_catalogue_ids == (999999,)


def test_ideas_rejects_wrong_cols_flag_dup_and_illegal_status() -> None:
    bad_cols = ("\t".join(REQUIRED_IDEAS_COLUMNS) + "\nA1\tonly_two\n").encode("utf-8")
    assert not verify_ideas_audit(bad_cols).passed
    flag_raw = _sample_ideas_bytes([_idea_row("A1", "BUILT", "FLAG")])
    assert not verify_ideas_audit(flag_raw).passed
    dup_raw = _sample_ideas_bytes([_idea_row("A1", "BUILT", "68701"), _idea_row("A1", "PARTIAL", "x")])
    assert not verify_ideas_audit(dup_raw).passed
    bad_st = _sample_ideas_bytes([_idea_row("A1", "DONE", "68701")])
    assert not verify_ideas_audit(bad_st).passed


@pytest.mark.parametrize("bad_score", [True, False, math.nan, math.inf, -math.inf, 0, 11, 5.5, "NaN"])
def test_ideas_rejects_invalid_scores(bad_score: Any) -> None:
    val, err = parse_score_1_to_10(bad_score, "score")
    assert val is None and err is not None


@pytest.mark.parametrize("bad_ratio", [math.nan, math.inf, -math.inf, True, -0.1, 1.1])
def test_ideas_rejects_invalid_ratio_threshold(bad_ratio: Any) -> None:
    raw = _sample_ideas_bytes([_idea_row("A1", "BUILT", "catalogue_id: 68701")])
    rep = verify_ideas_audit(raw, known_catalogue_ids={68701}, min_verified_ratio=bad_ratio)
    assert not rep.passed


def test_ideas_rejects_bool_catalogue_ids_and_bad_index(tmp_path: Path) -> None:
    raw = _sample_ideas_bytes([_idea_row("A1", "BUILT", "catalogue_id: 68701")])
    assert not verify_ideas_audit(raw, known_catalogue_ids={True}).passed
    idx, errs = parse_receipt_index("cid\t68701\trec.json\nfile\trec.json\trec.json\n")
    assert not errs and 68701 in idx.cid_to_path and "rec.json" in idx.file_to_path
    _, bad_errs = parse_receipt_index("cid\tnot_an_int\trec.json\n")
    assert bad_errs
    tp, ip = tmp_path / "ideas.tsv", tmp_path / "idx.tsv"
    tp.write_bytes(raw)
    ip.write_text("cid\t68701\trec.json\n", encoding="utf-8")
    rep = verify_ideas_audit_files(tp, receipt_index_path=ip, verified_tokens={"cid:68701": True})
    assert rep.passed and rep.verified_match_count == 1
    assert not verify_ideas_audit_files(tmp_path / "missing.tsv").passed


def test_explicit_honest_scope_limits_present() -> None:
    assert "Pure-Python stdlib" in SURPASS_SCOPE_LIMIT
    assert "Pure-Python stdlib" in IDEAS_SCOPE_LIMIT
