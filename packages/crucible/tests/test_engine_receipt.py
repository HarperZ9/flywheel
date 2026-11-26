"""Tests for Crucible canonical engine-receipt/1 emission and planted-tamper rejection."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from crucible.engine_receipt import (
    SCHEMA,
    emit_crucible_engine_receipt,
    verify_crucible_engine_receipt,
)


def test_emit_and_verify_match_drift_unverifiable(tmp_path: Path) -> None:
    artifact = tmp_path / "thesis.json"
    artifact.write_text('{"verdict": "supported"}\n', encoding="utf-8")

    rec_match = emit_crucible_engine_receipt(
        "t-match", tmp_path, [artifact], passed=True, pass_count=2, summary="[PASS] ok", hmac_key="sec"
    )
    assert rec_match["schema"] == SCHEMA
    assert rec_match["verdict"] == "MATCH"
    ok, errs = verify_crucible_engine_receipt(rec_match, check_files=True, hmac_key="sec")
    assert ok and errs == []

    rec_unv = emit_crucible_engine_receipt("t-unv", tmp_path, [artifact], passed=None)
    assert rec_unv["verdict"] == "UNVERIFIABLE"
    assert verify_crucible_engine_receipt(rec_unv, check_files=True) == (True, [])

    rec_drift = emit_crucible_engine_receipt("t-drift", tmp_path, [artifact], passed=False, fail_count=1)
    assert rec_drift["verdict"] == "DRIFT"
    assert verify_crucible_engine_receipt(rec_drift, check_files=True) == (True, [])


def test_planted_tampers_fail_closed(tmp_path: Path) -> None:
    artifact = tmp_path / "evidence.json"
    artifact.write_text('{"score": 1.0}\n', encoding="utf-8")
    rec = emit_crucible_engine_receipt(
        "t-tamper", tmp_path, [artifact], passed=True, pass_count=1, hmac_key="k1"
    )

    bad_schema = copy.deepcopy(rec)
    bad_schema["schema"] = "bogus/1"
    ok, errs = verify_crucible_engine_receipt(bad_schema)
    assert not ok and any("unexpected schema" in e for e in errs)

    forged = copy.deepcopy(rec)
    forged["oracle"] = None
    ok, errs = verify_crucible_engine_receipt(forged)
    assert not ok and any("fail-closed" in e for e in errs)

    ok, errs = verify_crucible_engine_receipt(rec, hmac_key="wrong")
    assert not ok and any("HMAC" in e for e in errs)

    artifact.write_text('{"score": 0.0}\n', encoding="utf-8")
    ok, errs = verify_crucible_engine_receipt(rec, check_files=True)
    assert not ok and any("artifact SHA-256 drift" in e for e in errs)

    artifact.unlink()
    ok, errs = verify_crucible_engine_receipt(rec, check_files=True)
    assert not ok and any("missing artifact file" in e for e in errs)


def test_missing_artifact_raises_and_outside_root_uses_basename(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    outside = tmp_path / "ext.txt"
    outside.write_text("ext", encoding="utf-8")
    rec = emit_crucible_engine_receipt("t-ext", sub, [outside], passed=True, pass_count=1)
    assert rec["subject"]["artifacts"][0]["rel_path"] == "ext.txt"
    assert verify_crucible_engine_receipt(rec, check_files=True) == (True, [])

    with pytest.raises(FileNotFoundError):
        emit_crucible_engine_receipt("t-miss", sub, [sub / "nope.txt"], passed=True)
