"""Level 3 and the receipts: another renderer's AO held to raw-native's, both verdicts kept.

Claims under test:
- raw-native's ray-traced AO handed back as the candidate is MATCH and PASS;
- one float nudged by 1e-3 is DRIFT and still PASS: identity and tolerance are
  separate verdicts, and the receipt keeps both;
- raw-native's own screen-space AO as the candidate is DRIFT and FAIL, at the
  RMSE the certificate records;
- a coverage mask that disagrees on more than 0.5 % of covered pixels fails;
- a candidate of the wrong size is UNVERIFIABLE with a stated reason;
- every receipt verifies under the vendored superstack contract, carries both
  verdicts in Flywheel's words and lists the four fixed lines first; a receipt
  edited after sealing fails its seal;
- paired mutation: a bound loosened to accept anything is caught.
"""
from __future__ import annotations

import struct

import pytest

from harness._vendor import superstack as ss
from harness.certificates import raw_ao, raw_ao_independent as ri, raw_ao_receipt as rr
from harness.certificates.raw_ao_buffers import canonical_ao, canonical_mask
from tests.raw_native_fixtures import cert, files

NAME = "windows-x64"


def _candidate(which: str = "ao_rt.pfm", **override) -> dict:
    fs = files(NAME)
    w, h, ao = canonical_ao(fs[which])
    _, _, mask = canonical_mask(fs["mask.pgm"])
    return {"ao_f32": ao, "mask_u8": mask, "width": w, "height": h,
            "backend": "test-backend", "producer": "test", "version": "0", **override}


def _receipt(candidate: dict) -> dict:
    rec = ri.receipt(cert(NAME), files(NAME), candidate)
    assert rr.check(rec) == []
    return rec


def _nudge(ao: bytes, index: int, delta: float) -> bytes:
    (v,) = struct.unpack_from("<f", ao, 4 * index)
    return ao[:4 * index] + struct.pack("<f", v + delta) + ao[4 * index + 4:]


def _first_covered(mask: bytes) -> int:
    return next(i for i, m in enumerate(mask) if m)


def test_the_reference_against_itself_is_match_and_pass():
    rec = _receipt(_candidate())
    assert rec["reconcile"]["identity"] == "MATCH"
    assert rec["flywheel"]["identity"] == "MATCH" and rec["flywheel"]["tolerance"] == "PASS"


def test_a_nudged_float_is_drift_and_still_pass():
    c = _candidate()
    c["ao_f32"] = _nudge(c["ao_f32"], _first_covered(c["mask_u8"]), 1e-3)
    rec = _receipt(c)
    assert (rec["flywheel"]["identity"], rec["flywheel"]["tolerance"]) == ("DRIFT", "PASS")


def _ssao_known_answer() -> None:
    rec = _receipt(_candidate("ao_ss.pfm"))
    assert (rec["flywheel"]["identity"], rec["flywheel"]["tolerance"]) == ("DRIFT", "FAIL")
    rmse = rec["reconcile"]["tolerance"]["metrics"]["ao_rmse"]
    assert rmse == pytest.approx(cert(NAME)["exact"]["rmse"], abs=1e-6)


def test_the_screen_space_shortcut_is_drift_and_fail():
    _ssao_known_answer()


def test_a_coverage_mismatch_over_half_a_percent_fails():
    c = _candidate()
    mask = bytearray(c["mask_u8"])
    covered = [i for i, m in enumerate(mask) if m]
    for i in covered[:10]:          # 10 of 928 covered pixels, about 1.1 %
        mask[i] = 0
    c["mask_u8"] = bytes(mask)
    tol = _receipt(c)["reconcile"]["tolerance"]
    assert tol["verdict"] == "refuted"
    assert tol["metrics"]["coverage_mismatch_frac"] == pytest.approx(10 / 928)


def test_a_candidate_of_the_wrong_size_is_unverifiable_with_a_reason():
    c = _candidate(width=39)
    tol = _receipt(c)["reconcile"]["tolerance"]
    assert tol["verdict"] == "unverifiable" and tol["reason"] == "size differs from the reference"


def test_level1_receipt_carries_both_verdicts_and_the_fixed_lines():
    rec = rr.level1_receipt(cert(NAME), files(NAME), platform=NAME)
    assert rr.check(rec) == []
    assert rec["does_not_prove"][:4] == list(raw_ao.DOES_NOT_PROVE)
    assert (rec["flywheel"]["identity"], rec["flywheel"]["tolerance"],
            rec["flywheel"]["verdict"]) == ("MATCH", "PASS", "PASS")
    assert rec["flywheel"]["certificate_sha256"] == raw_ao.certificate_sha256(cert(NAME))
    assert rec["scene_sha256"] == ss.canonical_sha256(rr.scene_for(cert(NAME)["params"]))


def test_a_refuted_render_reads_fail_on_tolerance_and_pass_on_the_recheck():
    rec = rr.level1_receipt(cert("windows-x64-refuted"), files("windows-x64-refuted"))
    assert (rec["flywheel"]["identity"], rec["flywheel"]["tolerance"],
            rec["flywheel"]["verdict"]) == ("MATCH", "FAIL", "PASS")


def test_an_edited_receipt_fails_its_seal_and_a_dropped_line_is_caught():
    rec = rr.level1_receipt(cert(NAME), files(NAME))
    edited = dict(rec, flywheel=dict(rec["flywheel"], tolerance="FAIL"))
    assert "seal" in ss.verify_receipt(edited) or "flywheel:tolerance" in rr.check(edited)
    resealed = ss.seal(dict(rec, does_not_prove=rec["does_not_prove"][1:]))
    assert "flywheel:does_not_prove" in rr.check(resealed)
    mixed = ss.seal(dict(rec, flywheel=dict(rec["flywheel"], identity="DRIFT")))
    assert rr.check(mixed) == ["flywheel:identity"]


def test_paired_mutation_a_bound_that_accepts_anything_is_caught(monkeypatch):
    monkeypatch.setitem(ri.BOUNDS, "ao_rmse_max", 1.0)
    with pytest.raises(AssertionError):
        _ssao_known_answer()
