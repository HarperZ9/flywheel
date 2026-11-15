"""Helpers for the tests that run a gateway on a home's on-disk ledger and fail its disk.

  home              the fixture: an empty Flywheel home, its ledger closed afterwards
  gateway_on_disk   a real gateway whose ledger is the home's, with a disk switch
  Disk              the segment's file with that switch
  rows, kinds, late, rows_call   what the segments hold afterwards

Used by test_gateway_ledger_write_failure.py, test_gateway_ledger_round4.py and
test_gateway_write_ahead.py. No provider is called.
"""
import io
import sys
import time
import types

import pytest

from harness import gateway, gateway_ledger

ENOSPC = (28, "No space left on device")


@pytest.fixture
def home(monkeypatch, tmp_path):
    where = tmp_path / "home"
    where.mkdir()
    monkeypatch.setenv("FLYWHEEL_HOME", str(where))
    yield where
    gateway_ledger.close_all()


class Disk(io.RawIOBase):
    """The segment's file with a switch: `full` refuses writes, `half` takes half a line.
    `skip` writes are let through first, so a call's started entry can land before it."""

    def __init__(self, real, state):
        self.real, self.state = real, state

    def writable(self):
        return True

    def write(self, data):
        if self.state.full and self.state.skip:
            self.state.skip -= 1
            return self.real.write(bytes(data))
        if self.state.full == "half":
            self.state.full = True
            self.real.write(bytes(data)[:len(data) // 2])
            raise OSError(*ENOSPC)
        if self.state.full:
            raise OSError(*ENOSPC)
        return self.real.write(bytes(data))

    def fileno(self):
        return self.real.fileno()


def gateway_on_disk(monkeypatch, served, answers, home):
    """(url, upstream, ledger, disk): a gateway on the home's ledger, and the disk switch."""
    url, upstream, _memory = served(answers)
    monkeypatch.setattr(gateway, "_ROUTER_LEDGER", None)
    ledger = gateway._router_ledger()
    disk = types.SimpleNamespace(full=False, skip=0)
    ledger._file = Disk(ledger._file, disk)
    health = sys.modules.get("harness.gateway_ledger_health")
    if health is not None:              # a reopened segment is on the same full disk
        real = health._put

        def put(file, data):
            if disk.full and not isinstance(file, Disk):
                raise OSError(*ENOSPC)
            return real(file, data)
        monkeypatch.setattr(health, "_put", put)
        monkeypatch.setattr(health, "RETRY_SECONDS", 0.0)   # try to resume on every call
    return url, upstream, ledger, disk


def cleared(url, keys, raw, post, name: str = "ci-bot") -> None:
    """After the ledger resumed: the key whose call was in flight is suspended, because the
    call's end entry could not be written when it ended (the one suspension rule). Check
    that, then lift it as `flywheel gateway-key clear` does."""
    status, _headers, body = post(url, "/v1/messages", raw)
    assert status == 403, body
    assert "suspended" in body["error"]["message"] and "ledger" in body["error"]["message"]
    from harness.gateway_key_policy import clear
    clear(keys, name)                   # what the command runs


def rows(home) -> list:
    return [(segment["name"], entry.seq, entry.kind)
            for segment in gateway_ledger.check(home) for entry in segment["rows"]]


def kinds(home) -> list:
    return [kind for _name, _seq, kind in rows(home)]


def rows_call(home, index: int) -> str:
    """The call id of the started entry at `index` of the first segment."""
    entry = gateway_ledger.check(home)[0]["rows"][index]
    assert entry.kind == "endpoint_call_started"
    return entry.content


def late(home) -> list:
    """The end entries a resumed ledger appended for calls that were in flight."""
    return [entry for segment in gateway_ledger.check(home) for entry in segment["rows"]
            if entry.meta.get("late")]
