"""N-11: the Stop path reuses the freeze envelope stored at prompt time and
fetches nothing."""
import os

from harness.capture_hooks.protocol import commitment
from turn_fixtures import SESSION, receipts, turn_store


def test_the_stop_path_makes_zero_fetches(tmp_path, monkeypatch):
    from harness import web_fetch_pinned
    fetched = []
    monkeypatch.setattr(web_fetch_pinned, "fetch_pinned", lambda url, **kw: fetched.append(url) or (
        200, {"Content-Type": "text/plain"}, b"page", url))
    with turn_store(tmp_path, freeze_urls="on") as store:
        salt = os.urandom(32)
        store.prompt("claude-code", SESSION, "pid-1",
                     commitment=commitment("prompt", salt, "see https://a.example/x"), salt=salt)
        manifest = store.freeze("claude-code", SESSION, "pid-1", ["https://a.example/x"])
        assert fetched == ["https://a.example/x"] and manifest["frozen"] == 1
        store.stop("claude-code", SESSION, "pid-1",
                   commitment=commitment("answer", salt, "done"), salt=salt)
    assert fetched == ["https://a.example/x"]
    data = receipts(tmp_path)[-1]["data"]
    assert data["frozen_urls"] == 1 and data["freeze_commitment"]


def test_freezing_without_a_pending_prompt_fetches_nothing(tmp_path, monkeypatch):
    from harness import web_fetch_pinned
    fetched = []
    monkeypatch.setattr(web_fetch_pinned, "fetch_pinned",
                        lambda url, **kw: fetched.append(url))
    with turn_store(tmp_path, freeze_urls="on") as store:
        manifest = store.freeze("claude-code", SESSION, "pid-none", ["https://a.example/x"])
    assert fetched == [] and manifest == {"frozen": 0, "refused": 0, "failed": 0,
                                          "sources": [], "reason": "NO_PENDING_PROMPT"}
