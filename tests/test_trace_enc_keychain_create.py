"""C2: a keychain lookup that fails is not "no key". A master key is created
only when the lookup says the keychain holds none, and only when sealing;
opening what an earlier key sealed never creates one. Keychain tools are
stubbed; no real keychain is touched."""
import pytest

from harness.trace_enc import EncError
from harness.trace_enc_aead import _masters

KEY = bytes(range(32))


def _world(lookups):
    created = []

    def lookup():
        return lookups.pop(0)

    def create():
        created.append(1)
        return KEY
    return _masters(lookup, create), created


def test_a_failed_lookup_never_creates_a_key():
    (opener, sealer), created = _world([(None, False), (None, False)])
    with pytest.raises(EncError) as refused:
        sealer()
    assert refused.value.code == "OS_KEY_UNAVAILABLE" and created == []


def test_opening_never_creates_a_key_even_when_none_is_found():
    (opener, sealer), created = _world([(None, True)])
    with pytest.raises(EncError):
        opener()
    assert created == []


def test_sealing_creates_a_key_only_after_a_definite_not_found():
    (opener, sealer), created = _world([(None, True)])
    assert sealer() == KEY and created == [1]
    assert opener() == KEY


def test_an_existing_key_is_used_and_never_replaced():
    (opener, sealer), created = _world([(KEY, False)])
    assert sealer() == KEY and created == []
