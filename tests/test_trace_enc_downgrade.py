"""S17, S18: encryption does not quietly go backwards. A one-file item whose
store has a floor and whose key exists is refused when its file is swapped
for plaintext; a key shard written in plaintext (no key store at the time)
is resealed the next time it is read with a provider, and status names any
still in plaintext."""
import json

import pytest

from delete_fixtures import OWNER, plant_turn
from harness.trace_enc import EncError, NoProvider
from harness.trace_enc_probe import encryption_status
from harness.trace_keystore import CUSTODY, PLAIN, Keystore
from harness.trace_turn_store import TurnStore
from trace_enc_fakes import StreamTestProvider, using


def test_a_turn_swapped_for_plaintext_is_refused(tmp_path):
    with using(StreamTestProvider()):
        turn = plant_turn(tmp_path)
        store = TurnStore(tmp_path, OWNER)
        path = next(store.base.glob(f"*/*/{turn['turn_ref']}.enc"))
        path.write_bytes(json.dumps({"turn_ref": turn["turn_ref"], "forged": True}).encode())
        with pytest.raises(EncError) as refused:
            store.read_turn(turn["turn_ref"])
    assert refused.value.code == "ENC_DOWNGRADE"


def test_a_plaintext_key_shard_is_resealed_and_counted_until_then(tmp_path):
    state = tmp_path / "state"
    with using(NoProvider()):
        key = Keystore(state, OWNER).custody_key()
    shard = state / "keys" / "v1" / "owners" / OWNER / CUSTODY
    assert shard.read_bytes().startswith(PLAIN)
    with using(StreamTestProvider()):
        status = encryption_status(state)
        assert status["plaintext_shards"] == 1 and "KEYSTORE_PLAINTEXT" in status["protection"]
        assert Keystore(state, OWNER).custody_key() == key
        assert not shard.read_bytes().startswith(PLAIN)
        assert encryption_status(state)["plaintext_shards"] == 0
