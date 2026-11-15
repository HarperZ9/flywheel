"""The gateway's ledger is kept on disk and chained across restarts.

A real gateway on a loopback port with a stub upstream writes to the ledger
of its Flywheel home (`gateway-ledger/`), through `gateway._router_ledger()`
as a running gateway does. A restart is modelled by closing the ledger and
letting the next call open it again from the files; no second operating
system process is started, and no provider is called.
"""
import json
import logging
import threading
from pathlib import Path

import pytest

from harness import gateway, gateway_ledger, gateway_ledger_cli
from harness.local_session import Entry
from tests import gateway_messages_support as support
from tests.gateway_keys_support import keyed, post, served, turn2  # noqa: F401  (fixtures)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release


@pytest.fixture
def on_disk(monkeypatch, tmp_path, served):
    """start(answers) -> (url, upstream, home): a gateway whose ledger is on disk."""
    home = tmp_path / "home"
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))

    def start(answers):
        url, upstream, _memory = served(answers)
        monkeypatch.setattr(gateway, "_ROUTER_LEDGER", None)
        return url, upstream, home
    yield start
    gateway_ledger.close_all()


def _cli(home, *argv) -> int:
    return gateway_ledger_cli.main(list(argv), environ={"FLYWHEEL_HOME": str(home)})


def _restart() -> None:
    gateway_ledger.close_all()


def _segment(home, number: int = 1) -> Path:
    return gateway_ledger.folder(home) / f"segment-{number:06d}.jsonl"


def test_entries_survive_a_restart_and_the_chain_verifies_across_it(on_disk, capsys):
    url, _upstream, home = on_disk(turn2(3))
    assert post(url, "/v1/messages", support.TOKEN)[0] == 200
    first = support.recorded(gateway._router_ledger())[0]
    _restart()
    assert post(url, "/v1/responses", support.TOKEN)[0] == 200
    ledger = gateway._router_ledger()
    assert isinstance(ledger, gateway_ledger.GatewayLedger) and ledger.found_broken is None
    assert support.kinds(ledger) == ["endpoint_call", "endpoint_call"]
    assert support.recorded(ledger)[0] == first, "the entry written before the restart was loaded"
    assert [e.kind for e in ledger.entries][2] == "endpoint_call_started"
    assert ledger.entries[2].prev_hash == first.entry_hash, "the new call chains onto it"
    assert ledger.verify()
    assert [s["name"] for s in gateway_ledger.check(home)] == ["segment-000001.jsonl"]
    assert _cli(home, "verify") == 0
    assert "gateway ledger verifies: 4 entries" in capsys.readouterr().out    # two per call


def test_an_entry_is_in_the_file_before_the_reply_is_sent(on_disk, monkeypatch):
    url, _upstream, home = on_disk(turn2(1))
    seen, real = [], support.gateway.__dict__["_Handler"].send_response

    def send_response(self, code, *args):
        if code == 200 and self.path == "/v1/messages":
            text = _segment(home).read_text(encoding="utf-8")
            seen.append((text.count('"kind": "endpoint_call_started"'),
                         text.count('"kind": "endpoint_call"')))
        return real(self, code, *args)
    monkeypatch.setattr(gateway._Handler, "send_response", send_response)
    assert post(url, "/v1/messages", support.TOKEN)[0] == 200
    assert seen == [(1, 1)], "both entries were on disk when the status line was written"


def test_a_flipped_byte_is_found_by_verify_and_at_start(on_disk, capsys, caplog):
    url, _upstream, home = on_disk(turn2(2))
    assert post(url, "/v1/messages", support.TOKEN)[0] == 200
    _restart()
    path = _segment(home)
    raw = path.read_bytes()
    at = raw.index(b'"model_ref": "') + len(b'"model_ref": "')
    path.write_bytes(raw[:at] + bytes([raw[at] ^ 1]) + raw[at + 1:])
    damaged = path.read_bytes()

    assert _cli(home, "verify") == 1
    # Line 1 is the header, line 2 the call's started entry, line 3 its end entry.
    assert "BROKEN: line 3 does not verify" in capsys.readouterr().out

    with caplog.at_level(logging.ERROR, logger="harness.gateway_ledger"):
        assert post(url, "/v1/messages", support.TOKEN)[0] == 200
    assert "GATEWAY LEDGER BROKEN: segment-000001.jsonl: line 3 does not verify" in caplog.text
    ledger = gateway._router_ledger()
    assert ledger.found_broken and ledger.path.name == "segment-000002.jsonl"
    assert path.read_bytes() == damaged, "the broken segment was not appended to"
    header = json.loads(_segment(home, 2).read_text(encoding="utf-8").splitlines()[0])
    assert header["previous"] == "segment-000001.jsonl"
    assert header["previous_state"] == "broken" and "line 3" in header["reason"]
    # The damaged line was the first call's end entry. Its started entry still verifies, so
    # that call is now a start with no end the ledger can vouch for: the new segment carries
    # it in its header and names it unsettled before it records the new call.
    lost, = header["open_calls"]
    assert ledger.entries[0].kind == "calls_unsettled" and ledger.entries[0].meta["calls"] == [lost]
    assert support.kinds(ledger) == ["calls_unsettled", "endpoint_call"] and ledger.verify()
    _restart()
    assert _cli(home, "verify") == 1
    out = capsys.readouterr().out
    assert "records a break in segment-000001.jsonl" in out and "DOES NOT VERIFY" in out


@pytest.mark.parametrize("cut, said", [
    ("line", "entries were removed"),       # the last entry removed whole
    ("bytes", "is cut short"),              # the last entry cut in the middle
])
def test_control_verify_fails_on_a_truncated_file(on_disk, capsys, cut, said):
    url, _upstream, home = on_disk(turn2(2))
    assert post(url, "/v1/messages", support.TOKEN)[0] == 200
    assert post(url, "/v1/messages", support.TOKEN)[0] == 200
    _restart()
    assert _cli(home, "verify") == 0, "control: the untouched ledger verifies"
    capsys.readouterr()
    path = _segment(home)
    raw = path.read_bytes()
    end = raw.rstrip(b"\n").rindex(b"\n") + 1 if cut == "line" else len(raw) - 40
    path.write_bytes(raw[:end])
    assert _cli(home, "verify") == 1
    assert said in capsys.readouterr().out
    assert gateway_ledger.GatewayLedger(home).found_broken
    gateway_ledger.close_all()


def test_show_by_key_returns_only_that_keys_entries(on_disk, keyed, capsys):
    keys, _store = keyed
    bot, _ = keys.create("ci-bot")
    other, _ = keys.create("teammate", token_limit=1)
    url, _upstream, home = on_disk(turn2(4))
    for credential in (bot, support.TOKEN, other, bot, other):   # the last one is refused
        post(url, "/v1/messages", credential)
    _restart()
    capsys.readouterr()

    def shown(*argv) -> list:
        assert _cli(home, "show", "--json", *argv) == 0
        return [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(shown()) == 9 and len(support.recorded(shown())) == 5    # four calls, one refusal
    mine = support.recorded(shown("--key", "ci-bot"))
    assert [row["meta"]["key"] for row in mine] == ["ci-bot", "ci-bot"]
    assert all(row["meta"]["charged_tokens"] == 460 for row in mine)
    assert [row["kind"] for row in support.recorded(shown("--key", "teammate"))] == [
        "endpoint_call", "endpoint_call_refused"]
    assert [row["meta"]["key"] for row in support.recorded(shown("--key", "owner"))] == ["owner"]
    assert shown("--key", "nobody") == []
    assert [row["kind"] for row in shown("--key", "teammate", "--kind", "endpoint_call")] == [
        "endpoint_call"]
    assert _cli(home, "show", "--key", "ci-bot") == 0
    text = capsys.readouterr().out
    assert text.count("key=ci-bot") == 4 and text.count("endpoint_call_started") == 2
    assert "teammate" not in text and bot not in text      # two calls, a start and an end each


def test_a_second_writer_is_refused_and_the_gateway_serves_nothing_unrecorded(
        tmp_path, caplog):
    first = gateway_ledger.GatewayLedger(tmp_path)
    try:
        with pytest.raises(gateway_ledger.LedgerBusy):
            gateway_ledger.GatewayLedger(tmp_path)
    finally:
        first.close()
    blocker = gateway_ledger.GatewayLedger(tmp_path)
    try:
        with caplog.at_level(logging.ERROR, logger="harness.gateway_ledger"):
            assert gateway_ledger.for_home(tmp_path) is None
        assert "gateway ledger unavailable (LedgerBusy" in caplog.text
    finally:
        blocker.close()


def test_parallel_appends_from_every_path_leave_one_chain(tmp_path):
    """The chat path appends without the interfaces' lock; the ledger has its own."""
    ledger = gateway_ledger.GatewayLedger(tmp_path)

    def writer(name: str) -> None:
        for index in range(25):
            ledger.append("endpoint_call", f"{name}-{index}", {"key": name})
    threads = [threading.Thread(target=writer, args=(f"t{n}",)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    ledger.close()
    assert len(ledger.entries) == 200 and ledger.verify()
    found, = gateway_ledger.check(tmp_path)
    assert found["ok"] and found["entries"] == 200


def test_a_full_segment_is_closed_and_the_next_links_to_its_head(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway_ledger, "ROTATE_AT", 3)
    ledger = gateway_ledger.GatewayLedger(tmp_path)
    for index in range(3):
        ledger.append("endpoint_call", str(index), {})
    head = ledger.checkpoint()
    ledger.close()
    again = gateway_ledger.GatewayLedger(tmp_path)
    again.append("endpoint_call", "3", {})
    again.close()
    first, second = gateway_ledger.check(tmp_path)
    assert first["ok"] and second["ok"] and again.found_broken is None
    assert second["header"]["previous_state"] == "verified"
    assert second["header"]["previous_head"] == head
    # Control: a link that names another head fails.
    path = _segment(tmp_path, 2)
    path.write_text(path.read_text(encoding="utf-8").replace(head, "0" * 64),
                    encoding="utf-8", newline="\n")
    assert not gateway_ledger.check(tmp_path)[1]["ok"]


def test_the_entry_format_is_the_session_ledgers(tmp_path):
    ledger = gateway_ledger.GatewayLedger(tmp_path)
    made = ledger.append("endpoint_call", "abc", {"key": "owner"})
    ledger.close()
    line = _segment(tmp_path).read_text(encoding="utf-8").splitlines()[1]
    assert Entry(**json.loads(line)) == made
    assert made.entry_hash == Entry.compute_hash(0, "endpoint_call", "abc", {"key": "owner"},
                                                 made.prev_hash)
