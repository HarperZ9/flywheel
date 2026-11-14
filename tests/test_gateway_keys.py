"""The gateway key store: minting, authentication, totals and their limits.

No HTTP here. Every key lives in the in-memory store from
tests.gateway_keys_support; the real credential store is never touched.
"""
import json
import threading

import pytest

from harness import gateway_keys
from harness.gateway_keys import INDEX, PREFIX, SLOT, Keys, KeysError
from tests.gateway_keys_support import FakeStore


def _keys(tmp_path, store=None):
    return Keys(tmp_path, store=store or FakeStore())


def _index(tmp_path) -> dict:
    return json.loads((tmp_path / INDEX).read_text(encoding="utf-8"))["keys"]


def test_create_stores_the_key_in_the_credential_store_and_facts_in_the_index(tmp_path):
    store = FakeStore()
    raw, row = _keys(tmp_path, store).create("ci-bot", token_limit=1000, models=["b", "a", "a"])
    assert raw.startswith(PREFIX) and len(raw) > 40
    assert store.saved == {f"{SLOT}@ci-bot": raw}
    assert _index(tmp_path)["ci-bot"] == row
    assert row["fingerprint"] == gateway_keys.fingerprint(raw) and len(row["fingerprint"]) == 16
    assert row["models"] == ["a", "b"] and row["token_limit"] == 1000
    assert row["revoked"] is False and row["totals"]["tokens"] == 0
    assert raw not in (tmp_path / INDEX).read_text(encoding="utf-8")


def test_two_keys_differ_and_a_taken_name_is_refused(tmp_path):
    keys = _keys(tmp_path)
    first, _ = keys.create("one")
    second, _ = keys.create("two")
    assert first != second
    with pytest.raises(KeysError, match="already exists"):
        keys.create("one")


@pytest.mark.parametrize("options, said", [
    ({"spend_limit": 5.0}, "needs --price-in and --price-out"),
    ({"spend_limit": 5.0, "price_in": 3.0}, "both --price-in and --price-out"),
    ({"token_limit": -1}, "--token-limit must be a whole number"),
    ({"price_in": float("nan"), "price_out": 1.0}, "--price-in must be a number"),
])
def test_limits_that_cannot_be_enforced_are_refused_at_creation(tmp_path, options, said):
    store = FakeStore()
    with pytest.raises(KeysError, match=said):
        _keys(tmp_path, store).create("ci-bot", **options)
    assert store.saved == {} and not (tmp_path / INDEX).exists()


@pytest.mark.parametrize("name", ["", "has space", "-lead", "x" * 33, "a/b", "a@b"])
def test_a_name_that_is_not_a_plain_label_is_refused(tmp_path, name):
    with pytest.raises(KeysError, match="a key name is 1 to 32 characters"):
        _keys(tmp_path).create(name)


def test_no_credential_store_refuses_creation_with_the_named_reason(tmp_path, monkeypatch):
    from harness import keychain
    monkeypatch.setattr(keychain, "keychain_refusal", lambda: "secret-tool is not installed")
    store = FakeStore(present=False)
    with pytest.raises(KeysError, match="secret-tool is not installed"):
        _keys(tmp_path, store).create("ci-bot")
    assert store.saved == {} and not (tmp_path / INDEX).exists()


def test_authenticate_accepts_the_minted_key_and_nothing_near_it(tmp_path):
    keys = _keys(tmp_path)
    raw, row = keys.create("ci-bot")
    assert keys.authenticate(raw) == ("ci-bot", row)
    for offered in (raw[:-1], raw + "x", raw.upper(), PREFIX, "", None, 7, raw[len(PREFIX):],
                    PREFIX + "x" * 300):
        assert keys.authenticate(offered) is None


def test_an_index_row_alone_does_not_make_a_key(tmp_path):
    """Index tampering: the fingerprint matches, the credential store holds nothing."""
    store = FakeStore()
    keys = _keys(tmp_path, store)
    keys.create("real")
    forged = PREFIX + "forged-by-a-process-that-can-only-write-the-index"
    rows = _index(tmp_path)
    rows["planted"] = {**rows["real"], "fingerprint": gateway_keys.fingerprint(forged)}
    (tmp_path / INDEX).write_text(json.dumps({"version": 1, "keys": rows}), encoding="utf-8")
    assert "planted" in keys.rows()                 # the row is read, so the lookup finds it
    assert keys.authenticate(forged) is None
    store.saved[f"{SLOT}@planted"] = forged         # control: with the store entry it works
    assert keys.authenticate(forged)[0] == "planted"


def test_a_row_pointed_at_another_keys_secret_is_refused(tmp_path):
    store = FakeStore()
    keys = _keys(tmp_path, store)
    raw, _ = keys.create("real")
    other = PREFIX + "some-other-value"
    rows = _index(tmp_path)
    rows["real"]["fingerprint"] = gateway_keys.fingerprint(other)
    (tmp_path / INDEX).write_text(json.dumps({"version": 1, "keys": rows}), encoding="utf-8")
    assert keys.authenticate(other) is None and keys.authenticate(raw) is None


def test_revoke_deletes_the_stored_key_and_keeps_the_totals(tmp_path):
    store = FakeStore()
    keys = _keys(tmp_path, store)
    raw, _ = keys.create("ci-bot")
    keys.debit("ci-bot", {"input": 10, "output": 5})
    row = keys.revoke("ci-bot")
    assert row["revoked"] is True and row["totals"]["tokens"] == 15
    assert store.saved == {} and keys.authenticate(raw) is None
    rows = _index(tmp_path)
    rows["ci-bot"]["revoked"] = False               # un-flagging the index does not revive it
    (tmp_path / INDEX).write_text(json.dumps({"version": 1, "keys": rows}), encoding="utf-8")
    assert keys.authenticate(raw) is None


def test_debit_adds_every_count_once_and_spend_follows_the_prices(tmp_path):
    keys = _keys(tmp_path)
    keys.create("ci-bot", spend_limit=1.0, price_in=3.0, price_out=15.0)
    keys.debit("ci-bot", {"input": 51, "output": 9, "cache_read": 400, "cache_write": None})
    row = keys.debit("ci-bot", {"input": 12, "output": 300, "cache_read": 2051, "cache_write": 300})
    assert row["totals"] == {
        "calls": 2, "tokens": 51 + 9 + 400 + 12 + 300 + 2051 + 300, "input_tokens": 63,
        "output_tokens": 309, "cache_read_tokens": 2451, "cache_write_tokens": 300,
        "estimated_calls": 0, "estimated_tokens": 0}
    # (63 + 2451 + 300) input-side tokens at $3 and 309 output tokens at $15, per million
    assert gateway_keys.spend(row) == pytest.approx((2814 * 3.0 + 309 * 15.0) / 1_000_000, abs=1e-9)
    assert gateway_keys.spend(row) == 0.013077


def test_an_estimated_debit_is_counted_apart(tmp_path):
    keys = _keys(tmp_path)
    keys.create("ci-bot")
    keys.debit("ci-bot", {"input": 100, "output": 20})
    row = keys.debit("ci-bot", {"input": 7, "output": 3}, estimated=True)
    assert (row["totals"]["tokens"], row["totals"]["estimated_tokens"]) == (130, 10)
    assert (row["totals"]["calls"], row["totals"]["estimated_calls"]) == (2, 1)


def test_over_names_the_limit_that_was_reached(tmp_path):
    keys = _keys(tmp_path)
    keys.create("tokens", token_limit=100)
    keys.create("spend", spend_limit=0.001, price_in=1.0, price_out=1.0)
    assert gateway_keys.over(keys.debit("tokens", {"input": 99})) is None
    assert gateway_keys.over(keys.debit("tokens", {"output": 1}))[0] == "token_limit"
    assert gateway_keys.over(keys.debit("spend", {"input": 999})) is None
    reason, said = gateway_keys.over(keys.debit("spend", {"input": 1}))
    assert reason == "spend_limit" and "$0.001000 of $0.001000" in said


def test_totals_survive_a_new_store_instance_and_reset_zeroes_them(tmp_path):
    store = FakeStore()
    _keys(tmp_path, store).create("ci-bot", token_limit=1000)
    _keys(tmp_path, store).debit("ci-bot", {"input": 400, "output": 60})
    again = _keys(tmp_path, store)                  # as after a gateway restart
    assert again.row("ci-bot")["totals"]["tokens"] == 460
    assert gateway_keys.view("ci-bot", again.row("ci-bot"))["remaining"] == {"tokens": 540}
    assert again.reset("ci-bot")["totals"]["tokens"] == 0
    assert _keys(tmp_path, store).row("ci-bot")["totals"]["calls"] == 0


def test_parallel_debits_from_threads_sum_exactly(tmp_path):
    store = FakeStore()
    _keys(tmp_path, store).create("ci-bot")
    failures = []

    def work():
        try:
            mine = _keys(tmp_path, store)           # one instance per thread, one file
            for _ in range(25):
                mine.debit("ci-bot", {"input": 3, "output": 2, "cache_read": 1})
        except Exception as exc:  # noqa: BLE001 - reported below
            failures.append(exc)
    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    totals = _keys(tmp_path, store).row("ci-bot")["totals"]
    assert failures == []
    assert (totals["calls"], totals["tokens"]) == (200, 1200)
    assert (totals["input_tokens"], totals["output_tokens"], totals["cache_read_tokens"]) == (
        600, 400, 200)


def test_a_damaged_index_is_an_error_and_a_malformed_row_is_not_a_key(tmp_path):
    keys = _keys(tmp_path)
    raw, _ = keys.create("ci-bot")
    (tmp_path / INDEX).write_text(json.dumps({"version": 1, "keys": {
        "ci-bot": {"fingerprint": gateway_keys.fingerprint(raw)}}}), encoding="utf-8")
    assert keys.rows() == {} and keys.authenticate(raw) is None
    (tmp_path / INDEX).write_text("{not json", encoding="utf-8")
    with pytest.raises(KeysError, match="cannot read the gateway key list"):
        keys.rows()
