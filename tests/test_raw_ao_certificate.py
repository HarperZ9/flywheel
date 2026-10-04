"""raw_ao_v1, level 1 and the translation table: a raw-native certificate read as data.

Claims under test, all without running anything:
- level 1 reproduces raw-native 0.4.0's recorded pixel count, RMSE, maximum
  error and verdict bit for bit, for renders from both release binaries;
- a forged certificate fails: a flipped verdict, an edited RMSE, and a forgery
  whose output digests were recomputed so only the arithmetic can catch it;
- a tampered PFM fails, both with its old digest left in place and with the
  digest rewritten to match the tampered bytes;
- a certificate without the float buffers (0.2.0 style), or with a listed file
  absent, is UNVERIFIABLE with ENVELOPE_MISSING, never FAIL;
- the translation table maps verified, refuted, unverifiable and garbage as the
  proposal fixes them, and every result carries the four fixed lines;
- paired mutations: float64 subtraction instead of the renderer's float32, and a
  checker that skips the arithmetic, are each caught by these tests;
- the family's modules import nothing that can execute.
"""
from __future__ import annotations

import ast
import hashlib
import json
import struct
from pathlib import Path

import pytest

from harness.certificates import raw_ao, raw_ao_buffers
from harness.verdict import Verdict
from tests.raw_native_fixtures import RENDERS, cert, files

FIXED_LINES = (
    "The reference is a 64-sample hemisphere estimate from a deterministic per-pixel "
    "hash, so it is repeatable, not exact.",
    "A pass on RMSE says nothing about the worst pixel. The high view passes at 0.0827 "
    "RMSE with a 0.625 maximum error.",
    "One built-in scene; no claim about other geometry, lights or materials.",
    "Byte-identical output is checked on x86-64 only.",
)


def _verify(c: dict, fs: dict):
    return raw_ao.verify_level1(json.dumps(c), fs)


def _rehash(c: dict, fs: dict) -> dict:
    """A forger's move: make every recorded digest match the files given."""
    out = json.loads(json.dumps(c))
    out["outputs"] = {n: hashlib.sha256(fs[n]).hexdigest() for n in out["outputs"]}
    return out


def _flip_float(pfm: bytes, index: int, delta: float) -> bytes:
    header_end = len(pfm) - (len(pfm) - pfm.index(b"-1.0\n") - 5)
    off = header_end + 4 * index
    (value,) = struct.unpack("<f", pfm[off:off + 4])
    return pfm[:off] + struct.pack("<f", value + delta) + pfm[off + 4:]


def _known_answer() -> None:
    for name in RENDERS:
        got = raw_ao_buffers.reconcile_files(files(name))
        ex = cert(name)["exact"]
        assert got["pixels"] == ex["pixels"]
        assert got["rmse"] == raw_ao_buffers.f32(ex["rmse"])
        assert got["maxError"] == raw_ao_buffers.f32(ex["maxError"])


@pytest.mark.parametrize("name", RENDERS)
def test_level1_reproduces_each_release_render_bit_for_bit(name):
    _known_answer()
    result = raw_ao.level1(cert(name), files(name))
    assert result["verdict"] == "PASS" and result["identity"] == "MATCH", result["detail"]
    r = _verify(cert(name), files(name))
    assert r.verdict_ is Verdict.PASS
    assert r.does_not_prove[:4] == list(FIXED_LINES)


def test_a_forged_verdict_fails():
    c = cert("windows-x64-refuted")
    c["verdict"] = "verified"
    r = raw_ao.level1(c, files("windows-x64-refuted"))
    assert r["verdict"] == "FAIL" and "verdict" in r["mismatches"]


def test_a_forged_rmse_with_rehashed_outputs_fails_on_the_arithmetic_alone():
    fs = files("windows-x64")
    c = _rehash(cert("windows-x64"), fs)
    c["exact"]["rmse"] = 0.05
    c["evidence"] = [["pixels", "928"], ["rmse", "0.0500"], ["maxError", "0.3854"],
                     ["tolerance", "0.1200"]]
    r = raw_ao.level1(c, fs)
    assert r["identity"] == "MATCH"
    assert r["verdict"] == "FAIL" and r["mismatches"] == ["rmse", "evidence.rmse"]


def test_evidence_that_disagrees_with_the_exact_values_fails():
    c = cert("windows-x64")
    c["evidence"][1] = ["rmse", "0.0100"]
    assert raw_ao.level1(c, files("windows-x64"))["mismatches"] == ["evidence.rmse"]


def test_a_tampered_pfm_fails_on_its_digest():
    fs = files("windows-x64")
    fs["ao_ss.pfm"] = _flip_float(fs["ao_ss.pfm"], 800, 0.5)
    r = raw_ao.level1(cert("windows-x64"), fs)
    assert r["verdict"] == "FAIL" and r["identity"] == "DRIFT"
    assert "sha256 ao_ss.pfm" in r["mismatches"]


def test_a_tampered_pfm_with_a_rewritten_digest_fails_on_the_arithmetic():
    fs = files("windows-x64")
    mask = raw_ao_buffers.canonical_mask(fs["mask.pgm"])[2]
    covered_bottom_up = next(i for i in range(len(mask)) if mask[(39 - i // 40) * 40 + i % 40])
    fs["ao_ss.pfm"] = _flip_float(fs["ao_ss.pfm"], covered_bottom_up, 0.25)
    r = raw_ao.level1(_rehash(cert("windows-x64"), fs), fs)
    assert r["identity"] == "MATCH"
    assert r["verdict"] == "FAIL" and "rmse" in r["mismatches"]


def test_a_0_2_0_certificate_is_unverifiable_not_wrong():
    c = cert("windows-x64")
    for key in ("schema", "renderer", "params", "samples", "exact", "outputs"):
        c.pop(key)
    r = _verify(c, files("windows-x64"))
    assert r.verdict_ is Verdict.UNVERIFIABLE and r.unverifiable_reason == "ENVELOPE_MISSING"


def test_an_absent_buffer_is_unverifiable_not_wrong():
    fs = files("windows-x64")
    del fs["mask.pgm"]
    r = raw_ao.level1(cert("windows-x64"), fs)
    assert r["verdict"] == "UNVERIFIABLE" and r["missing"] == ["mask.pgm"]


@pytest.mark.parametrize("text", ["", "not json", "[1]", '{"verdict": "verified"} trailing'])
def test_an_unreadable_certificate_is_unverifiable(text):
    r = raw_ao.verify_level1(text, files("windows-x64"))
    assert r.verdict_ is Verdict.UNVERIFIABLE and r.unverifiable_reason == "ENVELOPE_MISSING"


@pytest.mark.parametrize("raw,verdict,reason", [
    ("verified", Verdict.PASS, ""), ("refuted", Verdict.FAIL, ""),
    ("unverifiable", Verdict.UNVERIFIABLE, "ORACLE_UNAVAILABLE"),
    ("maybe", Verdict.UNVERIFIABLE, "ENVELOPE_MISSING"),
    (None, Verdict.UNVERIFIABLE, "ENVELOPE_MISSING")])
def test_translation_table(raw, verdict, reason):
    c = cert("windows-x64")
    c["verdict"] = raw
    t = raw_ao.translate(c)
    assert (t.verdict, t.reason) == (verdict, reason)
    if verdict is Verdict.PASS:
        assert t.note == raw_ao.COVERAGE_NOTE


def test_translation_of_a_missing_or_foreign_certificate_is_envelope_missing():
    assert raw_ao.translate(None).reason == "ENVELOPE_MISSING"
    assert raw_ao.translate({"oracle": "raw-arena-v1", "verdict": "verified"}).verdict \
        is Verdict.UNVERIFIABLE


def test_the_fixed_lines_are_exactly_the_proposals():
    assert raw_ao.DOES_NOT_PROVE == FIXED_LINES


def test_paired_mutation_float64_subtraction_is_caught(monkeypatch):
    real = raw_ao_buffers.reconcile

    def float64_diff(ss, rt, mask, w, h):
        out = real(ss, rt, mask, w, h)
        diffs = [abs(ss[y][x] - rt[y][x]) for y in range(h) for x in range(w) if mask[y][x]]
        out["rmse"] = (sum(d * d for d in diffs) / len(diffs)) ** 0.5
        return out
    monkeypatch.setattr(raw_ao_buffers, "reconcile", float64_diff)
    with pytest.raises(AssertionError):
        _known_answer()


def test_paired_mutation_a_checker_that_skips_the_arithmetic_is_caught(monkeypatch):
    monkeypatch.setattr(raw_ao, "_arithmetic_mismatches", lambda c, got: [])
    with pytest.raises(AssertionError):
        test_a_forged_rmse_with_rehashed_outputs_fails_on_the_arithmetic_alone()


@pytest.mark.parametrize("module", ["raw_ao.py", "raw_ao_buffers.py", "raw_ao_receipt.py",
                                    "raw_ao_independent.py"])
def test_the_family_imports_nothing_that_can_execute(module):
    path = Path(raw_ao.__file__).with_name(module)
    banned = {"subprocess", "socket", "ctypes", "pickle", "shutil", "importlib", "os"}
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                 else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
        assert not {n.split(".")[0] for n in names} & banned, (module, names)
