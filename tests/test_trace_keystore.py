"""I14 and SP-06/SP-10: item keys live in encrypted shards, reach disk before
they are used, survive a fault mid-rewrite, and are gone once destroyed."""
import base64

import pytest

from harness import trace_keystore
from harness.trace_keystore import Keystore
from trace_enc_fakes import StreamTestProvider

OWNER = "owner_" + "a" * 32


@pytest.fixture
def provider():
    return StreamTestProvider()


@pytest.fixture
def state(tmp_path):
    path = tmp_path / "state"
    path.mkdir()
    return path


def test_a_new_key_is_on_disk_before_it_is_returned(state, provider):
    key = Keystore(state, OWNER, provider).item_key("S1", "agt_a", create=True)
    assert len(key) == 32
    assert Keystore(state, OWNER, provider).item_key("S1", "agt_a") == key


def test_a_fault_between_the_temporary_write_and_the_rename_keeps_the_old_shard(
        state, provider, monkeypatch):
    first = Keystore(state, OWNER, provider).item_key("S1", "agt_a", create=True)

    def fail(*_a, **_k):
        raise OSError("injected fault before the rename")
    monkeypatch.setattr(trace_keystore, "_replace", fail)
    with pytest.raises(OSError):
        Keystore(state, OWNER, provider).item_key("S1", "agt_b", create=True)
    monkeypatch.undo()
    fresh = Keystore(state, OWNER, provider)
    assert fresh.item_key("S1", "agt_a") == first
    assert fresh.item_key("S1", "agt_b") is None


def test_a_destroyed_key_is_absent_from_the_current_shard(state, provider):
    keystore = Keystore(state, OWNER, provider)
    key = keystore.item_key("S1", "agt_a", create=True)
    keystore.item_key("S1", "agt_b", create=True)
    assert keystore.destroy("S1", ["agt_a"]) == 1
    fresh = Keystore(state, OWNER, provider)
    assert fresh.item_key("S1", "agt_a") is None and fresh.item_key("S1", "agt_b")
    opened = b"".join(fresh.unsealed_shards("S1"))
    assert b"agt_a" not in opened and base64.b64encode(key) not in opened


def test_the_custody_key_survives_item_deletions(state, provider):
    keystore = Keystore(state, OWNER, provider)
    custody = keystore.custody_key()
    keystore.item_key("S1", "agt_a", create=True)
    keystore.destroy("S1", ["agt_a"])
    assert Keystore(state, OWNER, provider).custody_key() == custody


def test_shards_are_ciphertext_on_disk(state, provider):
    key = Keystore(state, OWNER, provider).item_key("S1", "agt_a", create=True)
    raw = b"".join(p.read_bytes() for p in (state / "keys").rglob("*.keys"))
    assert raw and base64.b64encode(key) not in raw and b"agt_a" not in raw


def test_a_full_shard_rolls_over_to_the_next(state, provider, monkeypatch):
    monkeypatch.setattr(trace_keystore, "MAX_SHARD_ENTRIES", 2)
    keystore = Keystore(state, OWNER, provider)
    keys = {ref: keystore.item_key("S1", ref, create=True) for ref in ("a1", "a2", "a3")}
    assert len(list((state / "keys" / "v1" / "owners" / OWNER / "S1").glob("*.keys"))) == 2
    fresh = Keystore(state, OWNER, provider)
    assert all(fresh.item_key("S1", ref) == key for ref, key in keys.items())


def test_a_shard_sealed_by_another_provider_is_refused_not_misread(state, provider):
    from harness.trace_enc import EncError
    Keystore(state, OWNER, provider).item_key("S1", "agt_a", create=True)
    with pytest.raises(EncError) as failure:
        Keystore(state, OWNER, StreamTestProvider()).item_key("S1", "agt_a")
    assert failure.value.code in ("OS_KEY_UNAVAILABLE", "ENC_INTEGRITY")


def test_another_process_rewrite_is_seen_through_the_cache(state, provider):
    reader = Keystore(state, OWNER, provider)
    assert reader.item_key("S1", "agt_a") is None
    key = Keystore(state, OWNER, provider).item_key("S1", "agt_a", create=True)
    assert reader.item_key("S1", "agt_a") == key
