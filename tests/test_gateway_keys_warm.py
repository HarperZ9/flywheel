"""After a debit the key list is opened once, off the request path.

Measured 2026-11-14 on Windows 11 with real-time file scanning on: the first
open of gateway-keys.json after a debit changed it took about 6 ms, and that
open was the next call's key check, before anything went upstream. `Keys.debit`
now starts a thread that opens the file once (`Keys._warm`), so the wait is
paid between calls. These tests pin what that thread may and may not do: it
runs apart from the caller, it changes nothing a check reads, the debit is on
disk before `debit` returns whether or not the thread has run, and a file
that has gone is not an error.
"""
import json
import threading
from pathlib import Path

import pytest

from harness import gateway_keys
from scripts.gateway_bench_rig import MemoryStore


@pytest.fixture
def keys(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway_keys, "WARM", True)
    made = gateway_keys.Keys(tmp_path / "home", store=MemoryStore())
    made.raw = made.create("ci-bot", token_limit=1000)[0]
    return made


def _on_disk(keys) -> dict:
    return json.loads(keys.path.read_text(encoding="utf-8"))["keys"]["ci-bot"]["totals"]


def test_a_debit_opens_the_key_list_on_another_thread(keys, monkeypatch):
    ran, inner = [], gateway_keys.Keys._warm
    done = threading.Event()

    def warm(self):
        inner(self)
        ran.append(threading.get_ident())
        done.set()
    monkeypatch.setattr(gateway_keys.Keys, "_warm", warm)
    keys.debit("ci-bot", {"input": 10, "output": 5})
    assert done.wait(5.0)
    assert len(ran) == 1 and ran[0] != threading.get_ident()


def test_the_debit_is_on_disk_before_the_warm_up_runs(keys, monkeypatch):
    """`debit` returns with the totals written while the thread is still held back."""
    release, started = threading.Event(), threading.Event()

    def held(self):
        started.set()
        release.wait(5.0)
    monkeypatch.setattr(gateway_keys.Keys, "_warm", held)
    try:
        row = keys.debit("ci-bot", {"input": 600, "output": 400})
        assert row["totals"]["tokens"] == 1000 and _on_disk(keys)["tokens"] == 1000
        # The next check reads the file and sees the key at its limit.
        found = keys.authenticate(keys.raw)
        assert gateway_keys.over(found[1])[0] == "token_limit"
    finally:
        release.set()
    assert started.wait(5.0)


def test_a_check_after_the_warm_up_still_reads_the_file(keys, monkeypatch):
    """Nothing is kept from the warm-up: a change made by another process is seen."""
    done, inner = threading.Event(), gateway_keys.Keys._warm

    def warm(self):
        inner(self)
        done.set()
    monkeypatch.setattr(gateway_keys.Keys, "_warm", warm)
    keys.debit("ci-bot", {"input": 10})
    assert done.wait(5.0)
    index = json.loads(keys.path.read_text(encoding="utf-8"))
    index["keys"]["ci-bot"]["totals"]["tokens"] = 999       # as another process would
    keys.path.write_text(json.dumps(index), encoding="utf-8")
    assert keys.authenticate(keys.raw)[1]["totals"]["tokens"] == 999


def test_no_thread_is_started_where_the_warm_up_is_off(keys, monkeypatch):
    monkeypatch.setattr(gateway_keys, "WARM", False)
    ran = []
    monkeypatch.setattr(gateway_keys.Keys, "_warm", lambda self: ran.append(1))
    keys.debit("ci-bot", {"input": 10})
    assert ran == []
    assert _on_disk(keys)["tokens"] == 10


def test_a_key_list_that_has_gone_is_not_an_error(keys):
    keys.path.unlink()
    keys._warm()                        # logs at debug and returns
    assert not keys.path.exists()


def test_the_warm_up_is_on_only_where_it_was_measured():
    import os
    import subprocess
    import sys
    said = subprocess.run([sys.executable, "-c",
                           "from harness import gateway_keys; print(gateway_keys.WARM)"],
                          capture_output=True, text=True, timeout=60, check=True,
                          cwd=Path(__file__).resolve().parent.parent)
    assert said.stdout.strip() == str(os.name == "nt")
