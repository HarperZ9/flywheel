"""`verify` holds on a ledger a gateway is appending to, and ignores stray files.

Independent review of 2.0.0, findings A1 and N2.

A1. `verify` reported "entries were removed" on an intact ledger while a
gateway appended, because it read the segment before the head record. On a
segment of some thousand entries the second read a quarter of a second later
failed the same way. The head record is read first now.

N2. A file named like a segment that is not one (`segment-backup.jsonl`,
`segment-000001 - Copy.jsonl`) stopped the gateway at start with an uncaught
error, or failed `verify` on an intact ledger. Such a file is ignored and
named.
"""
import threading
import time

import pytest

from harness import gateway_ledger, gateway_ledger_cli, gateway_ledger_gate

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release


@pytest.fixture
def home(monkeypatch, tmp_path):
    where = tmp_path / "home"
    where.mkdir()
    monkeypatch.setenv("FLYWHEEL_HOME", str(where))
    yield where
    gateway_ledger.close_all()


@pytest.mark.parametrize("name", ["segment-backup.jsonl", "segment-000001 - Copy.jsonl",
                                  "segment-0000001.jsonl", "segment-000002.jsonl.bak"])
def test_a_stray_file_in_the_ledger_folder_is_ignored_and_named(home, name, capsys):
    ledger = gateway_ledger.for_home(home)
    ledger.append("endpoint_call", "x", {})
    gateway_ledger.close_all()
    folder = home / "gateway-ledger"
    (folder / name).write_bytes((folder / "segment-000001.jsonl").read_bytes())
    found = gateway_ledger.check(home)
    assert [(s["name"], s["ok"]) for s in found] == [("segment-000001.jsonl", True)]
    assert gateway_ledger_cli.main(["verify"]) == 0
    assert f"ignored {name!r}" in capsys.readouterr().out
    lines = []
    assert gateway_ledger_gate.startup(lambda: gateway_ledger.for_home(home), out=lines.append)
    assert any("ignored" in line and name in line for line in lines), lines
    gateway_ledger.for_home(home).append("endpoint_call", "y", {})     # and the chain goes on
    gateway_ledger.close_all()
    assert [s["entries"] for s in gateway_ledger.check(home)] == [2]


def test_verify_holds_when_an_entry_is_appended_between_its_two_reads(home, monkeypatch):
    """The forced order: the head record moves on after the segment was read."""
    monkeypatch.setenv(gateway_ledger.SYNC_ENV, "0")
    ledger = gateway_ledger.GatewayLedger(home)
    for index in range(5):
        ledger.append("endpoint_call", "x" * 64, {"n": index})
    real = gateway_ledger.read_segment

    def read_then_append(path):
        found = real(path)
        ledger.append("endpoint_call", "y" * 64, {})
        return found
    monkeypatch.setattr(gateway_ledger, "read_segment", read_then_append)
    try:
        found = gateway_ledger.check(home)
    finally:
        ledger.close()
    assert [(s["ok"], s["problem"], s["entries"]) for s in found] == [(True, None, 5)]


def test_verify_holds_on_a_ledger_that_a_writer_thread_appends_to(home, monkeypatch):
    monkeypatch.setenv(gateway_ledger.SYNC_ENV, "0")
    ledger = gateway_ledger.GatewayLedger(home)
    for index in range(4000):
        ledger.append("endpoint_call", "x" * 64, {"endpoint": "openai", "n": index})
    stop = threading.Event()

    def writer():
        while not stop.is_set():
            ledger.append("endpoint_call", "y" * 64, {"endpoint": "openai"})
            time.sleep(0.002)
    thread = threading.Thread(target=writer)
    thread.start()
    try:
        problems = []
        for _ in range(8):
            found = gateway_ledger.check(home)                  # one read, no retry
            problems += [s["problem"] for s in found if not s["ok"]]
        monkeypatch.setattr(gateway_ledger_cli, "RETRY_AFTER", 0.01)
        codes = [gateway_ledger_cli.main(["verify"]) for _ in range(3)]
    finally:
        stop.set()
        thread.join()
        ledger.close()
    assert [p for p in problems if "removed" in p] == [], problems
    assert codes == [0, 0, 0]
    assert all(s["ok"] for s in gateway_ledger.check(home))


def test_a_cut_line_is_named_and_the_entries_before_it_still_count(home):
    """`verify` named the line before the cut one and did not count that entry."""
    ledger = gateway_ledger.GatewayLedger(home)
    for index in range(3):
        ledger.append("endpoint_call", f"sha{index}", {})
    ledger.close()
    path = home / "gateway-ledger" / "segment-000001.jsonl"
    path.write_bytes(path.read_bytes()[:-40])                   # the third entry is cut
    found, = gateway_ledger.check(home)
    assert found["problem"] == "line 4 is cut short" and found["entries"] == 2
