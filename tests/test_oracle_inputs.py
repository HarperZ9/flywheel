"""Bounds and refusals for the fixture set a receipt carries.

capture() runs on our side of the trust boundary and restore() runs on a file
someone else wrote, so the interesting arms here are the ones that hand
restore() input capture() would never have produced. Every bound is re-checked
on the way back in, and every failure drops the entry rather than repairing it:
under the asymmetry in grounding.py a dropped fixture costs a confirmation and
can never grant one.

The digest arm is the other half of the story. Adding these fields had to leave
receipts sealed before them verifying against their own signatures, and it had
to leave the fixture set signed, because an unsigned one is a false MATCH for
sale.
"""
import hashlib
import json
from dataclasses import asdict

import pytest

from harness.envelope import ProofEnvelope
from harness.oracle_inputs import (MAX_FILE_BYTES, MAX_TOTAL_BYTES, capture,
                                   restore, safe_relative)

BASE = dict(task_id="t", candidate="x", oracle="pytest", oracle_cmd="c",
            oracle_output_hash="h", verdict="PASS", model_ref="stub", seed=0,
            prompt_hash="p", budget_spent={})


def _tree(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def test_capture_takes_the_fixtures_and_leaves_the_candidate(tmp_path):
    _tree(tmp_path, {"solution.py": "def add(a, b): ...",
                     "tests/test_solution.py": "def test_add(): ...",
                     "conftest.py": "import sys"})
    got = capture(tmp_path, exclude=("solution.py",))
    assert set(got) == {"tests/test_solution.py", "conftest.py"}
    assert got["conftest.py"] == "import sys"


def test_capture_skips_what_a_build_produced_not_what_a_task_supplied(tmp_path):
    _tree(tmp_path, {"tests/test_x.py": "ok",
                     "__pycache__/x.pyc": "stale",
                     ".pytest_cache/v/lastfailed": "{}",
                     "node_modules/dep/index.js": "0"})
    assert set(capture(tmp_path)) == {"tests/test_x.py"}


def test_capture_never_ships_the_answer_key(tmp_path):
    """canonical_hash reads outcomes back out of the junit file. A receipt
    carrying one would arrive in the fresh directory already graded."""
    _tree(tmp_path, {"tests/t.py": "ok", "_oracle_junit.xml": "<testsuites/>"})
    assert set(capture(tmp_path)) == {"tests/t.py"}


def test_capture_drops_a_file_over_the_per_file_cap(tmp_path):
    _tree(tmp_path, {"small.py": "ok", "big.py": "#" * (MAX_FILE_BYTES + 1)})
    assert set(capture(tmp_path)) == {"small.py"}


def test_capture_stays_under_the_total_cap(tmp_path):
    chunk = "#" * (MAX_FILE_BYTES - 1)
    _tree(tmp_path, {f"f{i:02d}.py": chunk for i in range(40)})
    got = capture(tmp_path)
    assert sum(len(v.encode()) for v in got.values()) <= MAX_TOTAL_BYTES
    assert 0 < len(got) < 40      # bounded, and not bounded to nothing


def test_capture_drops_binary_rather_than_mangling_it(tmp_path):
    (tmp_path / "blob.bin").write_bytes(bytes([0xFF, 0xFE, 0x00, 0x01]))
    (tmp_path / "ok.py").write_text("ok", encoding="utf-8")
    assert set(capture(tmp_path)) == {"ok.py"}


def test_capture_of_a_missing_workdir_is_empty_not_an_error(tmp_path):
    assert capture(tmp_path / "nope") == {}


def test_capture_is_deterministic(tmp_path):
    _tree(tmp_path, {"a.py": "1", "b/c.py": "2", "d.py": "3"})
    first = capture(tmp_path)
    assert json.dumps(first, sort_keys=True) == json.dumps(capture(tmp_path),
                                                           sort_keys=True)


def test_round_trip_rebuilds_the_tree(tmp_path):
    src = _tree(tmp_path / "src", {"tests/test_x.py": "def test_x(): pass",
                                   "data/fixture.json": '{"k": 1}'})
    dest = tmp_path / "dest"
    dest.mkdir()
    assert restore(capture(src), dest) == 2
    assert (dest / "tests/test_x.py").read_text() == "def test_x(): pass"
    assert (dest / "data/fixture.json").read_text() == '{"k": 1}'


@pytest.mark.parametrize("hostile", [
    "../escape.py", "../../escape.py", "a/../../escape.py",
    "/etc/passwd", "C:/Windows/x.py", "sub\\escape.py", "", ".", "..",
])
def test_restore_refuses_a_path_that_could_leave_the_directory(hostile, tmp_path):
    """Refused, not sanitised. A rewritten path that still writes somewhere is
    worse than one that does not run: refusing costs a confirmation,
    sanitising invents an environment nobody sealed."""
    assert safe_relative(hostile) is None
    assert restore({hostile: "payload"}, tmp_path) == 0
    assert list(tmp_path.rglob("*")) == []


def test_restore_re_enforces_every_bound_capture_applied(tmp_path):
    """capture() runs on our side; restore() reads a file someone else wrote,
    so it cannot inherit capture's guarantees. It re-checks them."""
    hostile = {
        "_oracle_junit.xml": "<testsuites/>",          # the answer key
        "__pycache__/x.pyc": "stale",                  # a build artefact
        "big.py": "#" * (MAX_FILE_BYTES + 1),          # over the per-file cap
        "n.py": 5,                                     # not even text
        "keep.py": "ok",
    }
    assert restore(hostile, tmp_path) == 1
    assert [p.name for p in tmp_path.rglob("*") if p.is_file()] == ["keep.py"]


def test_restore_of_nothing_is_zero_not_an_error(tmp_path):
    assert restore({}, tmp_path) == 0
    assert restore(None, tmp_path) == 0


def test_a_receipt_sealed_before_these_fields_keeps_its_digests():
    """The back-compat proof, computed the way the pre-2026-09-06 code did:
    over an asdict() that had neither key. A signature covers claim_sha256, so
    folding a new field in unconditionally would have broken verification on
    every receipt already sealed."""
    env = ProofEnvelope(**BASE)
    old = asdict(env)
    for k in ("candidate_path", "oracle_inputs", "oracle_stdout_excerpt"):
        old.pop(k, None)
    expected = hashlib.sha256(
        json.dumps(old, sort_keys=True).encode()).hexdigest()
    assert env.claim_sha256() == "sha256:" + expected
    assert env.claim_hash() == expected[:16]


def test_the_fields_are_signed_once_a_receipt_actually_carries_them():
    """The other direction. Held out unconditionally, the fixture set would be
    rewritable in place, and a test file with the same ids and weaker
    assertions reproduces the canonical hash against a tampered candidate."""
    plain = ProofEnvelope(**BASE)
    with_path = ProofEnvelope(**BASE, candidate_path="solution.py")
    with_inputs = ProofEnvelope(**BASE, oracle_inputs={"tests/t.py": "assert 1"})
    assert with_path.claim_sha256() != plain.claim_sha256()
    assert with_inputs.claim_sha256() != plain.claim_sha256()
    assert with_inputs.content_hash() != plain.content_hash()


def test_an_empty_carried_set_is_the_same_receipt_as_none_at_all():
    """A default is a default however it got there, or the same receipt would
    hash two ways depending on whether a writer spelled the empty case out."""
    assert (ProofEnvelope(**BASE, oracle_inputs={}, candidate_path="").claim_sha256()
            == ProofEnvelope(**BASE).claim_sha256())
