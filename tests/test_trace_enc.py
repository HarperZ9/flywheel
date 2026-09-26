"""I7 and I1: the encrypted file format, binding, padding and loss of the key.

Every case runs through each provider available here: the stdlib test
provider on every OS, AES-256-GCM when `cryptography` is installed, and
DPAPI on Windows.
"""
import os
import sys

import pytest

from harness.trace_custody_ledger import CustodyLedger
from harness.trace_enc import EncError, MAGIC
from harness.trace_enc_write import ItemCipher
from trace_enc_fakes import StreamTestProvider, UnavailableProvider, long_canary, shingles

OWNER = "owner_" + "a" * 32
ITEM = "agt_" + "1" * 32
OTHER = "agt_" + "2" * 32


def _aead():
    pytest.importorskip("cryptography")
    from harness.trace_enc_aead import AeadProvider
    key = os.urandom(32)
    return AeadProvider(lambda: key)


def _dpapi():
    if sys.platform != "win32":
        pytest.skip("DPAPI is Windows only")
    from harness.trace_enc_dpapi import DpapiProvider
    return DpapiProvider()


@pytest.fixture(params=["test", "aead", "dpapi"])
def provider(request):
    return {"test": StreamTestProvider, "aead": _aead, "dpapi": _dpapi}[request.param]()


@pytest.fixture
def state(tmp_path):
    path = tmp_path / "home" / "state"
    path.mkdir(parents=True)
    return path


def _cipher(state, provider, item=ITEM):
    return ItemCipher(state, OWNER, "S1", item, provider=provider)


def _code(call) -> str:
    with pytest.raises(EncError) as failure:
        call()
    return failure.value.code


def test_round_trip(state, provider):
    cipher = _cipher(state, provider)
    blob = cipher.seal("00000000.json", b'{"hello": "world"}')
    assert blob.startswith(MAGIC)
    assert _cipher(state, provider).open("00000000.json", blob) == b'{"hello": "world"}'


def test_a_flipped_byte_anywhere_after_the_header_is_an_integrity_failure(state, provider):
    cipher = _cipher(state, provider)
    blob = cipher.seal("00000000.json", b"x" * 300)
    start = blob.index(b"\n", len(MAGIC)) + 1
    for position in (start, start + 10, (start + len(blob)) // 2, len(blob) - 1):
        flipped = bytearray(blob)
        flipped[position] ^= 0x01
        assert _code(lambda: cipher.open("00000000.json", bytes(flipped))) == "ENC_INTEGRITY"


def test_a_tampered_header_is_caught(state, provider):
    cipher = _cipher(state, provider)
    blob = cipher.seal("00000000.json", b"payload")
    tampered = blob.replace(b'"bucket":1024', b'"bucket":2048', 1)
    assert tampered != blob
    assert _code(lambda: cipher.open("00000000.json", tampered)) in (
        "ENC_INTEGRITY", "ENC_FORMAT")


def test_a_destroyed_key_makes_the_file_unreadable(state, provider):
    cipher = _cipher(state, provider)
    blob = cipher.seal("00000000.json", b"payload")
    assert cipher.keystore.destroy("S1", [ITEM]) == 1
    assert _code(lambda: _cipher(state, provider).open("00000000.json", blob)) == "KEY_DESTROYED"


def test_a_file_moved_to_another_item_or_name_fails_binding(state, provider):
    blob = _cipher(state, provider).seal("00000000.json", b"payload")
    _cipher(state, provider, OTHER).seal("00000000.json", b"other")
    assert _code(lambda: _cipher(state, provider).open("00000001.json", blob)) == "ENC_BINDING"
    assert _code(lambda: _cipher(state, provider, OTHER).open("00000000.json", blob)) == (
        "ENC_BINDING")


def test_padding_hides_the_length_of_short_plaintexts(state, provider):
    cipher = _cipher(state, provider)
    assert len(cipher.seal("00000000.json", b"a")) == len(cipher.seal("00000001.json", b"a" * 200))


def test_the_long_canary_is_absent_from_the_blob(state, provider):
    canary = long_canary()
    blob = _cipher(state, provider).seal("00000000.json", canary.encode("utf-8"))
    assert canary.encode("utf-8") not in blob
    assert not any(piece in blob for piece in shingles(canary))
    keys = b"".join(p.read_bytes() for p in (state / "keys").rglob("*") if p.is_file())
    assert not any(piece in keys for piece in shingles(canary))


def test_a_lost_os_key_is_named_as_such_and_leaves_one_loss_record(state):
    provider = UnavailableProvider()
    cipher = _cipher(state, provider)
    blob = cipher.seal("00000000.json", b"payload")
    for _ in range(3):
        assert _code(lambda: _cipher(state, provider).open("00000000.json", blob)) == (
            "OS_KEY_UNAVAILABLE")
    entries = CustodyLedger(state.parent, OWNER).entries()
    losses = [e for e in entries if e["kind"] == "loss"]
    assert len(losses) == 1
    assert losses[0]["fields"]["reason_code"] == "OS_KEY_UNAVAILABLE"
    assert losses[0]["fields"]["store"] == "S1" and losses[0]["fields"]["items"] == 1


def test_bucket_sizes_follow_the_design():
    from harness.trace_enc import bucket_size
    assert bucket_size(1) == 1024 and bucket_size(1024) == 1024
    assert bucket_size(1025) == 2048 and bucket_size(40_000) == 64 * 1024
    assert bucket_size(64 * 1024 + 1) == 128 * 1024
    assert bucket_size(200 * 1024) == 256 * 1024
