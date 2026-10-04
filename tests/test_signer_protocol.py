"""The signer's narrow interface: what it signs, what it refuses, what it keeps.

Success criteria: the journal refuses a skipped, rewound or re-pointed sequence
number and accepts an exact retry; an operator rewind appears in every later
signed head; the signer answers only its three operations and refuses any
request outside the attestation shape; frames past the cap are refused; and the
key file is refused when other users could read it.
"""
from __future__ import annotations

import io
import os
import struct
import sys

import pytest

from harness.signer import statement, wire
from harness.signer.client import client_from_env
from harness.signer.journal import Journal, JournalConflict

A, B, C = "a" * 64, "b" * 64, "c" * 64


def _signer(tmp_path):
    try:
        import cryptography  # noqa: F401
    except ImportError:
        pytest.importorskip("nacl.signing", reason="signing needs cryptography or pynacl")
    from harness.signer import keys
    from harness.signer.server import Signer
    keys.create(tmp_path / "home")
    return Signer(tmp_path / "home", clock=lambda: "2026-10-04T00:00:00Z")


ISO = {"mode": "same-identity", "signer": "uid:1", "client": "uid:1", "via": "test"}


def test_journal_orders_and_refuses_rewrites(tmp_path):
    j = Journal(tmp_path)
    assert j.advance("s", 1, "", A) is True
    assert j.advance("s", 1, "", A) is False             # exact retry
    with pytest.raises(JournalConflict, match="already signed"):
        j.advance("s", 1, "", B)
    with pytest.raises(JournalConflict, match="skips ahead"):
        j.advance("s", 3, A, C)
    with pytest.raises(JournalConflict, match="previous seq"):
        j.advance("s", 2, C, B)
    assert j.advance("s", 2, A, B) is True
    assert j.head("s")["seq"] == 2 and j.head("other")["seq"] == 0


def test_a_rewind_is_one_step_and_stays_visible(tmp_path):
    j = Journal(tmp_path)
    j.advance("s", 1, "", A)
    j.advance("s", 2, A, B)
    after = j.rewind("s", "2026-10-04T00:00:00Z")
    assert after["seq"] == 1 and after["seal"] == A
    with pytest.raises(JournalConflict):
        j.rewind("s", "x")                               # one step only
    j.advance("s", 2, A, C)
    assert [r["seq"] for r in j.head("s")["rewinds"]] == [2]


def test_signed_head_carries_rewinds(tmp_path):
    s = _signer(tmp_path)
    s.handle({"op": "sign_record", "store": "s", "seq": 1, "prev": "", "seal": A}, ISO)
    s.journal.rewind("s", "2026-10-04T00:00:00Z")
    head = s.handle({"op": "head", "store": "s"}, ISO)["head"]
    assert statement.check(head, s.public, statement.HEAD_SCHEMA) == (True, "ok")
    assert head["rewinds"][0]["seal"] == A and head["seq"] == 0


@pytest.mark.parametrize("req, error", [
    ({"op": "sign_bytes", "data": "00"}, "unknown_op"),
    ({"op": "sign_record", "store": "s", "seq": 1, "prev": "", "seal": "zz"}, "bad_request"),
    ({"op": "sign_record", "store": "s", "seq": 0, "prev": "", "seal": A}, "bad_request"),
    ({"op": "sign_record", "store": "s", "seq": True, "prev": "", "seal": A}, "bad_request"),
    ({"op": "sign_record", "store": "s", "seq": 2, "prev": "", "seal": A}, "bad_request"),
    ({"op": "sign_record", "store": "", "seq": 1, "prev": "", "seal": A}, "bad_request"),
])
def test_the_signer_signs_nothing_outside_the_attestation_shape(tmp_path, req, error):
    reply = _signer(tmp_path).handle(req, ISO)
    assert reply["ok"] is False and reply["error"] == error


def test_attestation_binds_the_measured_isolation(tmp_path):
    s = _signer(tmp_path)
    att = s.handle({"op": "sign_record", "store": "s", "seq": 1, "prev": "", "seal": A},
                   ISO)["attestation"]
    assert statement.check(att, s.public, statement.ATTESTATION_SCHEMA) == (True, "ok")
    assert statement.isolation_of(att) == "same-identity"
    att["isolation"] = dict(ISO, mode="separate-identity")
    assert statement.check(att, s.public, statement.ATTESTATION_SCHEMA)[0] is False


def test_a_head_signature_is_not_an_attestation(tmp_path):
    s = _signer(tmp_path)
    head = s.handle({"op": "head", "store": "s"}, ISO)["head"]
    ok, why = statement.check(head, s.public, statement.ATTESTATION_SCHEMA)
    assert not ok and why.startswith("wrong_schema")


def test_oversized_and_non_object_frames_are_refused():
    big = struct.pack(">I", wire.MAX_FRAME + 1)
    with pytest.raises(wire.WireError, match="too large"):
        wire.decode_from(io.BytesIO(big).read)
    with pytest.raises(wire.WireError, match="not an object"):
        wire.decode_from(io.BytesIO(struct.pack(">I", 2) + b"[]").read)
    with pytest.raises(wire.WireError, match="closed"):
        wire.decode_from(io.BytesIO(struct.pack(">I", 9) + b"{}").read)


def test_client_reads_its_configuration_from_the_environment():
    assert client_from_env({}) is None
    c = client_from_env({"FLYWHEEL_SIGNER": "/run/x.sock", "FLYWHEEL_SIGNER_PUBKEY": "00" * 32})
    assert c.address == "/run/x.sock" and c.pinned == bytes(32)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_a_seed_other_users_can_read_is_refused(tmp_path):
    s = _signer(tmp_path)
    from harness.signer import keys
    seed = tmp_path / "home" / keys.SEED_NAME
    os.chmod(seed, 0o644)
    with pytest.raises(keys.KeyError_, match="0600"):
        keys.load(tmp_path / "home")
    assert s.public
