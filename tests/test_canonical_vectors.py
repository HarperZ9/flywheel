"""Canonical record v1 (docs/spec/canonical-record.md) against its golden vectors and Flywheel's receipts.

The vectors are the contract other repositories test against. These tests fail if the reference
implementation drifts from a vector, accepts an input the spec refuses, or if a tracked receipt
leaves the ground where Flywheel's older canonical() and the spec write the same bytes.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from harness import canonical_record as cr
from harness.certificates.base import canonical as certificate_canonical

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / "tests" / "data" / "canonical_vectors.json").read_text(encoding="utf-8"))
RECEIPT_GLOBS = ("artifacts/closeout/**/receipt.json", "tests/fixtures/**/receipt.json",
                 "tests/fixtures/model-receipt-golden.json")


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["id"])
def test_vector_bytes_and_digest(case):
    out = cr.dumps(json.loads(case["input"]))
    assert out.decode("utf-8") == case["canonical"]
    assert hashlib.sha256(out).hexdigest() == case["sha256"] == cr.sha256(json.loads(case["input"]))


@pytest.mark.parametrize("case", VECTORS["invalid"], ids=lambda c: c["id"])
def test_invalid_inputs_are_refused(case):
    with pytest.raises(cr.CanonicalError):
        cr.dumps(json.loads(case["input"]))


@pytest.mark.parametrize("case", VECTORS["arrays"], ids=lambda c: c["id"])
def test_array_header_and_digest(case):
    assert cr.array_header(case["dtype"], case["shape"]).hex() == case["header_hex"]
    assert cr.array_sha256(case["dtype"], case["shape"], case["values"]) == case["sha256"]


def test_array_dtype_and_shape_change_the_digest():
    base = cr.array_sha256("f64", [2], [1.0, 2.0])
    assert cr.array_sha256("f32", [2], [1.0, 2.0]) != base
    assert cr.array_sha256("f64", [2, 1], [1.0, 2.0]) != base
    with pytest.raises(cr.CanonicalError):
        cr.array_sha256("f64", [3], [1.0, 2.0])
    with pytest.raises(cr.CanonicalError):
        cr.array_sha256("f64", [1], [float("nan")])


def test_key_order_is_utf16_not_code_point():
    rec = {"": 1, "\U0001F600": 2}
    assert cr.text(rec) == '{"\U0001F600":2,"":1}'
    assert json.dumps(rec, sort_keys=True, ensure_ascii=False).startswith('{""')


def test_python_float_forms_are_not_canonical():
    for value, python_form, canonical in ((1.0, "1.0", "1"), (1e-7, "1e-07", "1e-7"), (1e16, "1e+16", "10000000000000000")):
        assert json.dumps(value) == python_form
        assert cr.number(value) == canonical


def test_the_vectors_cover_every_group_and_record_every_implementation():
    groups = {c["group"] for c in VECTORS["cases"]}
    assert {"core", "unicode", "float"} <= groups
    names = set(VECTORS["implementations"])
    assert len(names) == 6
    for case in VECTORS["cases"]:
        assert set(case["implementations"]) == names


def _receipts():
    seen = []
    for pattern in RECEIPT_GLOBS:
        seen += sorted(ROOT.glob(pattern))
    return seen


def _integral_floats_as_ints(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_integral_floats_as_ints(v) for v in value]
    if isinstance(value, dict):
        return {k: _integral_floats_as_ints(v) for k, v in value.items()}
    return value


def test_every_flywheel_receipt_has_a_canonical_form_and_differs_only_by_the_float_rule():
    receipts = _receipts()
    assert len(receipts) >= 30, "the receipt corpus went missing; this test would pass on nothing"
    differs = 0
    for path in receipts:
        record = json.loads(path.read_text(encoding="utf-8"))
        name = path.relative_to(ROOT).as_posix()
        spec_form = cr.text(record)
        if spec_form != certificate_canonical(record):
            differs += 1
        # Python writes 30.0 where the spec writes 30; with that one rule aside the two forms are equal.
        assert spec_form == certificate_canonical(_integral_floats_as_ints(record)), name
    assert differs >= 1, "no receipt carries an integral float any more; update the spec page summary"


def test_a_float_receipt_would_be_caught():
    record = {"kind": "receipt", "p": 1e-7}
    assert cr.text(record) != certificate_canonical(record)


def test_command_line_prints_the_vector_digest(tmp_path):
    case = next(c for c in VECTORS["cases"] if c["id"] == "float-in-record")
    path = tmp_path / "record.json"
    path.write_text(case["input"], encoding="utf-8")
    out = subprocess.run([sys.executable, "-m", "harness.canonical_record", "sha256", str(path)],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == case["sha256"]
    path.write_text("[NaN]", encoding="utf-8")
    bad = subprocess.run([sys.executable, "-m", "harness.canonical_record", "sha256", str(path)],
                         cwd=ROOT, capture_output=True, text=True)
    assert bad.returncode == 1 and "no canonical form" in bad.stderr
