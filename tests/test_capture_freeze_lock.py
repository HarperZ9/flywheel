"""URL freezing fetches without the custody lock: a slow page named in a
prompt must not block capture, key writes or deletion. The snapshots and the
envelope are written under the lock, and only while the prompt still waits."""
import pytest

from delete_fixtures import OWNER, SESSION
from harness import web_fetch_pinned
from harness.trace_capture_settings import DEFAULTS
from harness.trace_custody_lock import is_held
from harness.trace_turn_store import TurnStore
from trace_enc_fakes import StreamTestProvider, using

URL = "https://example.org/page"


@pytest.fixture
def store(tmp_path):
    with using(StreamTestProvider()):
        (tmp_path / "state").mkdir()
        yield TurnStore(tmp_path, OWNER, settings={**DEFAULTS, "freeze_urls": "on"})


def _snaps(store):
    return list((store.state / "capture-snapshots").rglob("snap_*.enc"))


def test_the_fetch_runs_without_the_custody_lock(store, monkeypatch):
    held = []

    def fetch(url, **kw):
        held.append(is_held(store.state))
        return 200, {"Content-Type": "text/plain"}, b"page", url
    monkeypatch.setattr(web_fetch_pinned, "fetch_pinned", fetch)
    store.prompt("claude-code", SESSION, "pid-1", text="see " + URL)
    manifest = store.freeze("claude-code", SESSION, "pid-1", [URL])
    assert held == [False] and manifest["frozen"] == 1 and len(_snaps(store)) == 1


def test_a_prompt_paired_during_the_fetch_gets_no_snapshot(store, monkeypatch):
    def fetch(url, **kw):
        store.stop("claude-code", SESSION, "pid-1", text="answered meanwhile")
        return 200, {"Content-Type": "text/plain"}, b"page", url
    monkeypatch.setattr(web_fetch_pinned, "fetch_pinned", fetch)
    store.prompt("claude-code", SESSION, "pid-1", text="see " + URL)
    manifest = store.freeze("claude-code", SESSION, "pid-1", [URL])
    assert manifest.get("reason") == "PROMPT_NO_LONGER_WAITING" and _snaps(store) == []
