"""I5 for turn receipts: a v2 receipt holds commitments and random ids only,
no URL and no unsalted digest, so once its salts are deleted nothing in the
store confirms a guess of the turn. The opening (text and salt) verifies it,
and the session appears only as a ref keyed with the owner's custody key."""
import hashlib
import os
import re

import pytest

from harness.capture_hooks.protocol import commitment
from harness.trace_turn_receipt import verify_opening
from turn_fixtures import SESSION, custody_bytes, receipts, turn_store

CANARY = "CANARY-TURN-" + "q7" * 6


@pytest.fixture
def spy(monkeypatch):
    """Record every sha256 output whose input held the canary, at write time, in
    the modules that write receipts and commitments (a proxy per module)."""
    seen = []
    real = hashlib

    class Spy:
        digest_size, block_size, name = 32, 64, "sha256"

        def __init__(self, data=b""):
            self.inner, self.data = real.sha256(data), bytes(data)

        def update(self, data):
            self.data += bytes(data)
            self.inner.update(data)

        def copy(self):
            twin = Spy()
            twin.inner, twin.data = self.inner.copy(), self.data
            return twin

        def hexdigest(self):
            value = self.inner.hexdigest()
            if CANARY.encode() in self.data:
                seen.append(value)
            return value

        def digest(self):
            self.hexdigest()
            return self.inner.digest()

    class Proxy:
        sha256 = Spy

        def __getattr__(self, name):
            return getattr(real, name)
    import harness.capture_hooks.protocol as protocol_module
    import harness.store as store_module
    import harness.trace_turn_receipt as receipt_module
    for module in (store_module, receipt_module, protocol_module):
        monkeypatch.setattr(module, "hashlib", Proxy())
    return seen


def _turn(store, text=CANARY, key="pid-1"):
    psalt, asalt = os.urandom(32), os.urandom(32)
    store.prompt("claude-code", SESSION, key, commitment=commitment("prompt", psalt, text),
                 salt=psalt)
    result = store.stop("claude-code", SESSION, key,
                        commitment=commitment("answer", asalt, f"answer to {text}"), salt=asalt)
    return result, psalt, asalt


def test_a_v2_receipt_holds_commitments_and_random_ids_only(tmp_path):
    with turn_store(tmp_path) as store:
        result, _, _ = _turn(store)
    receipt = receipts(tmp_path)[-1]
    assert receipt["eid"].startswith("tr2_") and re.fullmatch(r"tr2_[0-9a-f]{24}", receipt["eid"])
    data = receipt["data"]
    assert data["schema"] == "flywheel.turn-receipt/v2"
    assert "prompt_sha256" not in data and "answer_sha256" not in data
    assert "http" not in repr(data) and "sources_frozen" not in data
    assert data["session_ref"] != SESSION and SESSION not in repr(data)
    assert result["turn_ref"] not in repr(data)


def test_the_opening_verifies_the_receipt(tmp_path):
    with turn_store(tmp_path) as store:
        _, psalt, asalt = _turn(store)
    data = receipts(tmp_path)[-1]["data"]
    assert verify_opening(data, "prompt", CANARY, psalt)
    assert verify_opening(data, "answer", f"answer to {CANARY}", asalt)
    assert not verify_opening(data, "prompt", CANARY + "x", psalt)


def test_no_unsalted_digest_of_the_canary_reaches_custody(tmp_path, spy):
    with turn_store(tmp_path) as store:
        _, psalt, asalt = _turn(store)
        _turn(store, key="pid-2")
    stored = custody_bytes(tmp_path)
    assert spy, "false-success control: the spy saw the commitments being made"
    hiding = {r["data"][k] for r in receipts(tmp_path)
              for k in ("prompt_commitment", "answer_commitment")}
    for digest in spy:
        if digest in hiding:
            continue  # a salted commitment; its salt lives only in the encrypted turn
        for width in (64, 32, 12):
            assert digest[:width].encode() not in stored
    for salt in (psalt, asalt):
        assert salt not in stored and salt.hex().encode() not in stored


def test_the_keyed_session_ref_is_stable_per_owner_and_not_the_raw_id(tmp_path):
    with turn_store(tmp_path) as store:
        _turn(store, key="pid-1")
        _turn(store, key="pid-2")
    refs = {r["data"]["session_ref"] for r in receipts(tmp_path)}
    assert len(refs) == 1 and SESSION not in refs.pop()
