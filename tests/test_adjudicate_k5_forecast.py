"""The k=5 adjudication must read its constants FROM the sealed record, not
hand-retyped rounded copies. The rounded band was wider at BOTH ends, so a
measured rate the sealed interval would reject could read INSIDE the script's
band. Constants come from the sealed forecast (unrounded), the claim shas
re-derive from the sealed thesis, the pinned oracle hash is bound in the
interval claim, and a tampered record refuses adjudication.
"""
import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("crucible")

from scripts.adjudicate_k5_forecast import ORACLE_SHA, sealed_constants

BASE = (Path(__file__).resolve().parent.parent / "docs" / "claims"
        / "2026-07-14-passk-forecast")


def test_constants_are_the_unrounded_sealed_values():
    sc = sealed_constants(BASE)
    forecast = json.loads(
        (BASE / "FORECAST-14B-K5.json").read_text(encoding="utf-8"))
    assert sc["het"] == forecast["expected_pass_rate"] == 0.6659
    assert [sc["het_lo"], sc["het_hi"]] == forecast["interval_95"] == \
        [0.5952, 0.7365]
    assert sc["iid"] == forecast["iid_baseline"]["expected_pass_rate"] == 0.7593
    # the old hand-retyped constants were lossy and wider at both ends
    assert (sc["het"], sc["het_lo"], sc["het_hi"], sc["iid"]) != \
        (0.666, 0.595, 0.737, 0.759)


def test_claim_shas_rederive_from_the_sealed_thesis():
    sc = sealed_constants(BASE)
    assert sc["claims"]["c-14b-k5-interval"] == \
        "633c6a73a7e4c3c091e39dedce3a003e0a0537b7d22ce92b2955712357872e88"
    assert sc["claims"]["c-14b-k5-het-beats-iid"].startswith("4e655d64")
    assert sc["claims"]["c-14b-k5-iid-beats-het"].startswith("9b91597e")


def test_oracle_sha_is_bound_in_the_sealed_interval_claim():
    # sealed_constants asserts the pinned oracle hash appears verbatim in the
    # sealed c-14b-k5-interval claim text; returning it proves the binding held
    sc = sealed_constants(BASE)
    assert sc["oracle_sha"] == ORACLE_SHA


def test_tampered_forecast_record_is_refused(tmp_path):
    dst = tmp_path / "claims"
    shutil.copytree(BASE, dst)
    forecast = json.loads(
        (dst / "FORECAST-14B-K5.json").read_text(encoding="utf-8"))
    forecast["expected_pass_rate"] = 0.9        # break the seal preimage
    (dst / "FORECAST-14B-K5.json").write_text(
        json.dumps(forecast, indent=1), encoding="utf-8")
    with pytest.raises(SystemExit):
        sealed_constants(dst)
