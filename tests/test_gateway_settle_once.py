"""A key is charged for one call once: at its end, or when an operator settles it.

Sixth review round of 2.0.0, findings S3 and S5 of the fourth independent
review (probes r4probes/test_p3_kill.py and p5_settle_and_rotation.py):

  - two model calls that arrived while one settle request waited each applied
    it: the key was charged 920 for one call of 460, with two settled entries;
  - a settle that stopped between the debit and its entry charged again when
    it was repeated;
  - a gateway killed after the debit and before the end entry left the key
    charged, and settling the call with the provider's figures charged it a
    second time;
  - a settle request file with negative counts credited a key;
  - a last segment whose header was never written dropped the held
    reservation of an unsettled call, and `settle` raised;
  - a call that ended with no end entry in a gateway that kept running was
    reported `open` and could not be settled until a restart;
  - every start of a gateway appended another `calls_unsettled` entry.

The planted controls show each assertion can fail: the settle lock removed,
and the charge record ignored. No provider is called.
"""
import contextlib
import json
import threading

import pytest

from harness import (gateway_calls, gateway_key_gate, gateway_keys, gateway_ledger,
                     gateway_ledger_cli, gateway_ledger_health, gateway_ledger_settle as settle)
from harness import gateway_key_charges     # noqa: I001  (new in round 6)
from tests.gateway_keys_support import FakeStore

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release
ONE = {"input": 451, "output": 9}       # what the call cost: 460 tokens


@pytest.fixture
def keyed(monkeypatch, tmp_path):
    """(home, keys): a key `ci-bot` with a limit of 1000 tokens."""
    monkeypatch.setattr(gateway_keys, "WARM", False)
    home, store = tmp_path / "home", FakeStore()
    home.mkdir()
    monkeypatch.setattr(gateway_key_gate, "open_keys",
                        lambda where: gateway_keys.Keys(where, store=store))
    keys = gateway_keys.Keys(home, store=store)
    keys.create("ci-bot", token_limit=1000)
    yield home, keys
    gateway_ledger.close_all()


def begin(ledger, keys) -> str:
    return gateway_calls.begin(ledger, {
        "endpoint": "openai", "interface": "anthropic-messages", "prompt_sha": "p" * 16,
        "key": "ci-bot", "key_fp": keys.row("ci-bot")["fingerprint"]}, [25, 64])


def unsettled(home, keys, charged=False) -> str:
    """One call whose gateway is gone; with `charged`, the key was debited first."""
    ledger = gateway_ledger.GatewayLedger(home)
    call = begin(ledger, keys)
    if charged:
        keys.debit("ci-bot", ONE, False, call)      # as Bill.settle does, with the call id
    ledger.close()
    return call


def cli(capsys, home, *argv) -> tuple:
    capsys.readouterr()
    code = gateway_ledger_cli.main(list(argv), environ={"FLYWHEEL_HOME": str(home)})
    said = capsys.readouterr()
    return code, said.out + said.err


def tokens(keys) -> int:
    return keys.row("ci-bot")["totals"]["tokens"]


def kinds(home) -> list:
    return [entry.kind for segment in gateway_ledger.check(home) for entry in segment["rows"]]


def request(home, call, counts) -> None:
    (gateway_ledger.folder(home) / f"settle-{call}.json").write_text(
        json.dumps({"call": call, "counts": counts, "note": ""}), encoding="utf-8")


def _two_calls_arrive(monkeypatch, home, keys):
    """Two model calls arrive while one settle request waits; both reach the charge."""
    call = unsettled(home, keys)
    ledger = gateway_ledger.GatewayLedger(home)
    request(home, call, ONE)
    barrier, real = threading.Barrier(2, timeout=1), settle._charge

    def charge(*args, **kwargs):        # hold each thread at the charge until both are there
        with contextlib.suppress(threading.BrokenBarrierError):
            barrier.wait()
        return real(*args, **kwargs)
    monkeypatch.setattr(settle, "_charge", charge)
    threads = [threading.Thread(target=gateway_ledger_health.usable, args=(ledger,))
               for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    settled = [entry.kind for entry in ledger.entries].count("endpoint_call_settled")
    ledger.close()
    return settled


def test_two_calls_that_arrive_together_apply_one_settle_request_once(keyed, monkeypatch, capsys):
    home, keys = keyed
    assert _two_calls_arrive(monkeypatch, home, keys) == 1
    assert tokens(keys) == 460 and keys.row("ci-bot")["totals"]["calls"] == 1
    assert cli(capsys, home, "verify")[0] == 0


def test_control_without_the_settle_lock_the_request_is_applied_twice(keyed, monkeypatch, capsys):
    """Planted: the lock removed. The ledger then gets two settled entries for one call,
    which `verify` names; the key is still charged once, because the debit carries the id."""
    home, keys = keyed
    monkeypatch.setattr(settle, "_SETTLING", contextlib.nullcontext())
    assert _two_calls_arrive(monkeypatch, home, keys) == 2
    assert tokens(keys) == 460
    code, text = cli(capsys, home, "verify")
    assert code == 4 and "second_end" in text


def test_control_without_the_lock_and_the_charge_record_the_key_pays_twice(keyed, monkeypatch):
    """Planted: the state before this round. 920 for one call of 460."""
    home, keys = keyed
    monkeypatch.setattr(settle, "_SETTLING", contextlib.nullcontext())
    monkeypatch.setattr(gateway_key_charges, "seen", lambda row, call: None)
    assert _two_calls_arrive(monkeypatch, home, keys) == 2
    assert tokens(keys) == 920


def test_a_settle_that_stopped_after_the_debit_charges_nothing_more_when_repeated(
        keyed, monkeypatch, capsys):
    home, keys = keyed
    call = unsettled(home, keys)
    real = gateway_ledger.GatewayLedger.append

    def append(self, kind, content, meta=None):
        if kind == "endpoint_call_settled":
            raise KeyboardInterrupt     # the process stops between the debit and the entry
        return real(self, kind, content, meta)
    monkeypatch.setattr(gateway_ledger.GatewayLedger, "append", append)
    with pytest.raises(KeyboardInterrupt):
        cli(capsys, home, "settle", call, "--input", "451", "--output", "9")
    monkeypatch.setattr(gateway_ledger.GatewayLedger, "append", real)
    gateway_ledger.close_all()
    assert tokens(keys) == 460 and "endpoint_call_settled" not in kinds(home)
    code, text = cli(capsys, home, "settle", call, "--input", "451", "--output", "9")
    assert code == 0 and "had already been charged 460 tokens" in text
    assert tokens(keys) == 460
    entry = [e for s in gateway_ledger.check(home) for e in s["rows"]][-1]
    assert entry.kind == "endpoint_call_settled"
    assert entry.meta["already_charged"] == 460 and entry.meta["charged_tokens"] == 0
    assert cli(capsys, home, "verify")[0] == 0


def test_a_call_charged_before_its_gateway_stopped_is_not_charged_again_by_settle(
        keyed, capsys):
    """Killed after the debit, before the end entry (review 4, S3)."""
    home, keys = keyed
    call = unsettled(home, keys, charged=True)
    assert tokens(keys) == 460
    ledger = gateway_ledger.GatewayLedger(home)     # a gateway starts and names the call
    marker = ledger.entries[-1]
    assert marker.kind == "calls_unsettled" and marker.meta["charged"] == {call: 460}
    for index in range(gateway_key_charges.KEPT + 5):   # the key's short record moves on
        keys.debit("ci-bot", {"input": 0, "output": 0}, False, f"{index:024x}")
    assert gateway_key_charges.seen(keys.row("ci-bot"), call) is None
    ledger.close()
    code, text = cli(capsys, home, "settle", call, "--input", "451", "--output", "9")
    assert code == 0 and "had already been charged 460 tokens" in text
    assert tokens(keys) == 460
    assert cli(capsys, home, "verify")[0] == 0


def test_control_a_call_that_was_never_charged_is_charged_by_settle(keyed, capsys):
    home, keys = keyed
    call = unsettled(home, keys)
    code, text = cli(capsys, home, "settle", call, "--input", "451", "--output", "9")
    assert code == 0 and "was charged 460 tokens" in text and tokens(keys) == 460


@pytest.mark.parametrize("counts", [
    {"input": -900, "output": -50}, {"input": 10 ** 13, "output": 0}, {"input": "5", "output": 1},
    {"input": 1.5, "output": 1}, {"input": True, "output": 1}, {"input": 5}, [5, 1],
    {"input": 5, "output": 1, "cache_read": -900}])
def test_a_settle_request_file_with_counts_that_are_not_valid_is_not_applied(keyed, counts):
    home, keys = keyed
    call = unsettled(home, keys)
    ledger = gateway_ledger.GatewayLedger(home)
    keys.debit("ci-bot", {"input": 900, "output": 50}, False)       # 950 of 1000 used
    request(home, call, counts)
    assert gateway_ledger_health.usable(ledger) is ledger
    assert tokens(keys) == 950
    assert call in ledger.calls.orphans and "endpoint_call_settled" not in [
        entry.kind for entry in ledger.entries]
    assert not list(gateway_ledger.folder(home).glob("settle-*.json"))     # dropped and logged


def test_control_a_valid_settle_request_file_is_applied(keyed):
    home, keys = keyed
    call = unsettled(home, keys)
    ledger = gateway_ledger.GatewayLedger(home)
    request(home, call, ONE)
    gateway_ledger_health.usable(ledger)
    assert tokens(keys) == 460 and call not in ledger.calls.orphans


def test_an_unreadable_last_segment_header_keeps_the_unsettled_call_held(keyed, capsys):
    """A rotation that stopped after creating the next segment and before its header."""
    home, keys = keyed
    call = unsettled(home, keys)
    (gateway_ledger.folder(home) / "segment-000002.jsonl").write_bytes(b"")
    ledger = gateway_ledger.GatewayLedger(home)
    fingerprint = keys.row("ci-bot")["fingerprint"]
    assert ledger.found_broken and sorted(ledger.calls.orphans) == [call]
    assert gateway_calls.held(ledger, fingerprint) == (25, 64, 1)
    ledger.close()
    code, text = cli(capsys, home, "settle", call, "--no-charge")
    assert code == 0, text
    code, text = cli(capsys, home, "verify")
    assert code == 1 and "UNSETTLED" not in text    # the break is recorded; the call is settled
    again = gateway_ledger.GatewayLedger(home)
    assert gateway_calls.held(again, fingerprint) == (0, 0, 0)
    again.close()


def test_a_call_that_is_no_orphan_of_the_opened_ledger_is_refused_not_raised(keyed, capsys,
                                                                             monkeypatch):
    home, keys = keyed
    call = unsettled(home, keys)
    monkeypatch.setattr(gateway_calls.Calls, "found", classmethod(
        lambda cls, header, entries, older, read: cls(None, [])))   # the ledger lost sight of it
    code, text = cli(capsys, home, "settle", call, "--no-charge")
    assert code == 1 and "was not settled" in text


def test_a_call_with_no_end_entry_in_a_running_gateway_is_named_unsettled_at_once(keyed, capsys):
    home, keys = keyed
    ledger = gateway_ledger.GatewayLedger(home)     # the gateway keeps running
    call = begin(ledger, keys)
    gateway_calls.defer(ledger, "endpoint_call_failed", "accounting_error", {"call": call})
    assert gateway_calls.held(ledger, keys.row("ci-bot")["fingerprint"]) == (25, 64, 1)
    marker = ledger.entries[-1]
    assert marker.kind == "calls_unsettled" and marker.meta["calls"] == [call]
    code, text = cli(capsys, home, "verify")        # read from the files while it runs
    assert code == 3 and f"UNSETTLED call {call}" in text
    code, text = cli(capsys, home, "settle", call, "--input", "451", "--output", "9")
    assert code == 0 and "request was left" in text
    gateway_ledger_health.usable(ledger)            # its next model call applies the request
    assert tokens(keys) == 460 and call not in ledger.calls.orphans
    ledger.close()
    assert cli(capsys, home, "verify")[0] == 0


def test_a_second_start_does_not_name_the_same_unsettled_call_again(keyed):
    home, keys = keyed
    unsettled(home, keys)
    for _ in range(3):
        gateway_ledger.GatewayLedger(home).close()
    assert kinds(home).count("calls_unsettled") == 1
