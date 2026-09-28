"""The DPAPI provider (Windows): round trip, the item key as required
entropy, an outer MAC that catches what DPAPI alone accepts, and the error
code mapping (experiment X8, in part)."""
import os
import sys

import pytest

from harness.trace_enc import EncError

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows only")


@pytest.fixture
def dpapi():
    from harness.trace_enc_dpapi import DpapiProvider
    return DpapiProvider()


def test_round_trip_with_the_item_key(dpapi):
    key = os.urandom(32)
    blob = dpapi.encrypt(key, b"inner bytes", b"aad")
    assert dpapi.decrypt(key, blob, b"aad") == b"inner bytes"


def test_another_item_key_cannot_decrypt(dpapi):
    blob = dpapi.encrypt(os.urandom(32), b"inner bytes", b"aad")
    with pytest.raises(EncError) as failure:
        dpapi.decrypt(os.urandom(32), blob, b"aad")
    assert failure.value.code == "ENC_INTEGRITY"


def test_the_raw_dpapi_blob_needs_the_entropy(dpapi):
    from harness.capture_hooks import protect
    key = os.urandom(32)
    blob = dpapi.encrypt(key, b"inner bytes", b"aad")
    raw = blob[:-32]
    with pytest.raises(OSError):
        protect.unprotect(raw, b"")


def test_every_flipped_byte_is_caught_including_those_dpapi_accepts(dpapi):
    from harness.capture_hooks import protect
    key = os.urandom(32)
    raw = protect.protect(b"x" * 64, key)
    accepted = []
    for position in range(min(40, len(raw))):
        flipped = bytearray(raw)
        flipped[position] ^= 1
        try:
            protect.unprotect(bytes(flipped), key)
            accepted.append(position)
        except OSError:
            pass
    assert accepted, "control: raw DPAPI accepts some flipped header bytes"
    blob = dpapi.encrypt(key, b"x" * 64, b"aad")
    for position in accepted:
        flipped = bytearray(blob)
        flipped[position] ^= 1
        with pytest.raises(EncError) as failure:
            dpapi.decrypt(key, bytes(flipped), b"aad")
        assert failure.value.code == "ENC_INTEGRITY"


def test_error_codes_map_to_named_failures():
    from harness.trace_enc_dpapi import map_error
    assert map_error(13) == "ENC_INTEGRITY"
    assert map_error(0x8009000B) == "OS_KEY_UNAVAILABLE"
    assert map_error(0x80090345) == "OS_KEY_UNAVAILABLE"
    assert map_error(5) == "ENC_UNREADABLE:5"


def test_the_start_up_probe_passes_here(dpapi):
    from harness.trace_enc_probe import probe
    assert probe(dpapi) == {"ok": True, "provider": "dpapi", "code": None}
