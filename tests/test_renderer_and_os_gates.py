# SPDX-License-Identifier: MIT
"""Unit tests for harness/renderer_parity_gate and harness/zero_c_os_verifier."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import pytest

from harness.renderer_parity_gate import (
    HONEST_SCOPE_LIMIT as RENDERER_SCOPE_LIMIT,
)
from harness.renderer_parity_gate import (
    REQUIRED_PARITY_COLUMNS,
    normalize_fnv1a_pin,
    parse_strict_ulp,
    verify_renderer_parity,
    verify_renderer_parity_files,
)
from harness.zero_c_os_verifier import (
    HONEST_SCOPE_LIMIT as OS_SCOPE_LIMIT,
)
from harness.zero_c_os_verifier import (
    REQUIRED_ISAS,
    REQUIRED_SLICE_COLUMNS,
    extract_slice_binaries_from_receipt,
    hash_binary_file,
    validate_binary_magic,
    verify_zero_c_os_tsv,
)


def _sample_parity_bytes(rows: list[str] | None = None) -> bytes:
    header = "\t".join(REQUIRED_PARITY_COLUMNS)
    body = rows if rows is not None else [
        "12\tart_dither.bld\t68693\tr12.json\tart_dither.bld\t0xb9ca7e2db4a440f7\t0\t1",
        "13\tart_noise.bld\t68704\tr13.json\tart_noise.bld\t0xbb69adfcaefa21bc\t0\t1",
    ]
    return ("\n".join([header] + body) + "\n").encode("utf-8")


def _sample_slice_rows(
    slice_id: str,
    cid: int,
    *,
    zero_c: int = 1,
    runs: int = 25,
    attacks: int = 4,
    omit_isa: str | None = None,
) -> list[str]:
    sha = "a" * 64
    out: list[str] = []
    for isa in sorted(REQUIRED_ISAS):
        if isa == omit_isa:
            continue
        out.append(f"{slice_id}\t{cid}\t{slice_id}.json\t{isa}\t{zero_c}\t{runs}\t{attacks}\t{slice_id}.{isa}\t1024\t{sha}")
    return out


def _sample_os_bytes(rows: list[str]) -> bytes:
    return ("\n".join(["\t".join(REQUIRED_SLICE_COLUMNS)] + rows) + "\n").encode("utf-8")


def test_renderer_parity_clean_pass_and_deterministic_attestation() -> None:
    raw = _sample_parity_bytes()
    r1 = verify_renderer_parity(
        raw,
        expected_module_range=(12, 13),
        known_catalogue_ids={68693, 68704},
        expected_fnv_pins={"art_dither.bld": "0xb9ca7e2db4a440f7"},
        receipt_verdicts={68693: True, 68704: True},
    )
    r2 = verify_renderer_parity(raw, expected_module_range=(12, 13))
    assert r1.passed and r1.module_count == 2 and r1.zero_ulp_count == 2
    assert r1.planted_controls_caught == 2 and r1.min_module_num == 12 and r1.max_module_num == 13
    assert len(r1.renderer_parity_attestation_sha256) == 64
    assert r1.renderer_parity_attestation_sha256 == r2.renderer_parity_attestation_sha256


def test_renderer_parity_rejects_fnv_tamper_and_zero_pin() -> None:
    raw = _sample_parity_bytes()
    rep = verify_renderer_parity(raw, expected_fnv_pins={"art_dither.bld": "0x1111111111111111"})
    assert not rep.passed and any("FNV-1a pin mismatch" in v for v in rep.violations)
    zero_raw = _sample_parity_bytes(["12\tart_dither.bld\t68693\tr.json\ta.bld\t0x0000000000000000\t0\t1"])
    assert not verify_renderer_parity(zero_raw).passed
    assert normalize_fnv1a_pin("0x1234", "p")[0] is None


def test_renderer_parity_rejects_nonzero_ulp_and_uncaught_control() -> None:
    bad_ulp = _sample_parity_bytes(["12\tart_dither.bld\t68693\tr.json\ta.bld\t0xb9ca7e2db4a440f7\t1\t1"])
    assert not verify_renderer_parity(bad_ulp).passed
    bad_ctrl = _sample_parity_bytes(["12\tart_dither.bld\t68693\tr.json\ta.bld\t0xb9ca7e2db4a440f7\t0\t0"])
    assert not verify_renderer_parity(bad_ctrl).passed


def test_renderer_parity_rejects_forged_cid_missing_range_and_bad_receipt() -> None:
    raw = _sample_parity_bytes()
    assert not verify_renderer_parity(raw, known_catalogue_ids={68693}).passed
    assert not verify_renderer_parity(raw, expected_module_range=(12, 14)).passed
    assert not verify_renderer_parity(raw, receipt_verdicts={68693: True, 68704: False}).passed


@pytest.mark.parametrize("bad_ulp", [math.nan, math.inf, -math.inf, True, False, -0.5, "NaN"])
def test_renderer_parity_rejects_non_finite_and_bool_ulp(bad_ulp: Any) -> None:
    val, err = parse_strict_ulp(bad_ulp, "ulp")
    assert val is None and err is not None
    assert not verify_renderer_parity(_sample_parity_bytes(), max_ulp_err=bad_ulp).passed


def test_renderer_parity_file_roundtrip_and_errors(tmp_path: Path) -> None:
    p = tmp_path / "parity.tsv"
    p.write_bytes(_sample_parity_bytes())
    assert verify_renderer_parity_files(p, expected_module_range=(12, 13)).passed
    assert not verify_renderer_parity_files(tmp_path / "missing.tsv").passed
    assert not verify_renderer_parity(b"\xff\xfe").passed
    assert not verify_renderer_parity(_sample_parity_bytes(), known_catalogue_ids={True}).passed


def test_zero_c_os_clean_pass_and_binary_hash_check() -> None:
    rows = _sample_slice_rows("slice17_boot", 68741) + _sample_slice_rows("slice18_sched", 68750)
    bhashes = {("slice17_boot", isa): (1024, "a" * 64) for isa in REQUIRED_ISAS}
    bhashes.update({("slice18_sched", isa): (1024, "a" * 64) for isa in REQUIRED_ISAS})
    rep = verify_zero_c_os_tsv(
        _sample_os_bytes(rows),
        min_slices=2,
        known_catalogue_ids={68741, 68750},
        binary_hashes=bhashes,
        receipt_verdicts={68741: True, 68750: True},
    )
    assert rep.passed and rep.slice_count == 2 and rep.binary_count == 10
    assert rep.isa_complete_slices == 2 and rep.total_attacks_caught == 8
    assert len(rep.zero_c_os_attestation_sha256) == 64


def test_zero_c_os_rejects_missing_isa_and_duplicate_isa() -> None:
    miss = _sample_slice_rows("slice17_boot", 68741, omit_isa="rv64-elf")
    rep = verify_zero_c_os_tsv(_sample_os_bytes(miss), min_slices=1)
    assert not rep.passed and any("missing required ISAs" in v for v in rep.violations)
    dup = _sample_slice_rows("slice17_boot", 68741) + [_sample_slice_rows("slice17_boot", 68741)[0]]
    rep2 = verify_zero_c_os_tsv(_sample_os_bytes(dup), min_slices=1)
    assert not rep2.passed and any("duplicate ISA" in v for v in rep2.violations)


def test_zero_c_os_rejects_attack_bypass_zero_c_false_and_forged_cid() -> None:
    att = _sample_slice_rows("slice17_boot", 68741, attacks=3)
    assert not verify_zero_c_os_tsv(_sample_os_bytes(att), min_slices=1).passed
    zc = _sample_slice_rows("slice17_boot", 68741, zero_c=0)
    assert not verify_zero_c_os_tsv(_sample_os_bytes(zc), min_slices=1).passed
    ok_rows = _sample_slice_rows("slice17_boot", 999999)
    assert not verify_zero_c_os_tsv(_sample_os_bytes(ok_rows), min_slices=1, known_catalogue_ids={68741}).passed


def test_zero_c_os_rejects_tampered_binary_digest_and_bad_thresholds() -> None:
    rows = _sample_slice_rows("slice17_boot", 68741)
    bad_hashes = {("slice17_boot", isa): (1024, "b" * 64) for isa in REQUIRED_ISAS}
    rep = verify_zero_c_os_tsv(_sample_os_bytes(rows), min_slices=1, binary_hashes=bad_hashes)
    assert not rep.passed and any("binary digest or size mismatch" in v for v in rep.violations)


@pytest.mark.parametrize("bad_param", [True, False, 0, -1, math.nan, math.inf, "7"])
def test_zero_c_os_rejects_invalid_thresholds(bad_param: Any) -> None:
    rows = _sample_slice_rows("slice17_boot", 68741)
    assert not verify_zero_c_os_tsv(_sample_os_bytes(rows), min_slices=bad_param).passed
    assert not verify_zero_c_os_tsv(_sample_os_bytes(rows), min_slices=1, min_attacks_per_slice=bad_param).passed


@pytest.mark.parametrize("bad_pin", ["", "0x123", "0x" + "g" * 16, "0x" + "0" * 16, 12345, None])
def test_renderer_parity_rejects_malformed_fnv_pins(bad_pin: Any) -> None:
    pin, err = normalize_fnv1a_pin(bad_pin, "pin")
    assert pin is None and err is not None


@pytest.mark.parametrize(
    ("isa", "header", "expected"),
    [
        ("x64-pe", b"MZ\x90\x00", True),
        ("x64-elf", b"\x7fELF\x02\x01", True),
        ("rv64-elf", b"\x7fELF\x02\x01", True),
        ("aarch64-elf", b"\x7fELF\x02\x01", True),
        ("wasm", b"\x00asm\x01\x00", True),
        ("wasm", b"\x7fELF", False),
        ("x64-pe", b"\x00asm", False),
        ("unknown-isa", b"\x7fELF", False),
    ],
)
def test_zero_c_os_magic_matrix(isa: str, header: bytes, expected: bool) -> None:
    assert validate_binary_magic(isa, header) is expected


def test_zero_c_os_receipt_extraction_and_hash_helper(tmp_path: Path) -> None:
    bin_f = tmp_path / "k.wasm"
    bin_f.write_bytes(b"\x00asm\x01\x00\x00\x00")
    sz, dig = hash_binary_file(bin_f)
    assert sz == 8 and dig == hashlib.sha256(b"\x00asm\x01\x00\x00\x00").hexdigest()
    rec = {
        "subject": {
            "artifacts": [
                {"rel_path": "out/k.aarch64.elf", "bytes": 100, "sha256": f"sha256:{'a' * 64}"},
                {"rel_path": "out/k.rv64.elf", "bytes": 100, "sha256": f"sha256:{'a' * 64}"},
                {"rel_path": "out/k.x64.elf", "bytes": 100, "sha256": f"sha256:{'a' * 64}"},
                {"rel_path": "out/k.exe", "bytes": 100, "sha256": f"sha256:{'a' * 64}"},
                {"rel_path": "out/k.wasm", "bytes": 100, "sha256": f"sha256:{'a' * 64}"},
            ]
        }
    }
    bins, errs = extract_slice_binaries_from_receipt("slice24_v1", 68811, rec)
    assert not errs and len(bins) == 5


def test_explicit_honest_scope_limits_present() -> None:
    assert "Pure-Python stdlib" in RENDERER_SCOPE_LIMIT
    assert "Pure-Python stdlib" in OS_SCOPE_LIMIT
