"""Falsifiers for the web_search tool: sources, parsing, permission class."""
import io
import json

from harness.code_session import search
from harness.code_session.backends import build_agent
from harness.code_session.policy import tool_class
from harness.code_session.session import new_session
from tests.test_code_session import ScriptBackend

DDG = b'''<div class="result"><a rel="nofollow" class="result__a"
href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F3%2F&amp;rut=x">Python <b>docs</b></a>
<a class="result__snippet" href="x">The official &amp; complete docs.</a></div>'''


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(body, seen=None):
    def open_(req, timeout):
        if seen is not None:
            seen.append((req.full_url, dict(req.header_items())))
        return Resp(body)
    return open_


def test_duckduckgo_without_any_key():
    ok, out = search.search("python docs", opener=_opener(DDG), environ={})
    assert ok and out.startswith("[duckduckgo] 1 result(s)")
    assert "https://docs.python.org/3/" in out and "Python docs" in out
    assert "The official & complete docs." in out


def test_brave_when_a_key_is_set():
    seen = []
    body = json.dumps({"web": {"results": [{"title": "T", "url": "https://t.example",
                                            "description": "<b>d</b>"}]}}).encode()
    ok, out = search.search("q", opener=_opener(body, seen), environ={"BRAVE_API_KEY": "bk"})
    assert ok and "[brave]" in out and "https://t.example" in out
    assert seen[0][0].startswith("https://api.search.brave.com/")
    assert ("X-subscription-token", "bk") in seen[0][1].items()


def test_searxng_wins_when_configured():
    body = json.dumps({"results": [{"title": "S", "url": "https://s.example", "content": "c"}]}).encode()
    ok, out = search.search("q", opener=_opener(body),
                            environ={"SEARXNG_URL": "https://sx.local", "BRAVE_API_KEY": "bk"})
    assert ok and out.startswith("[searxng]")


def test_failures_are_results_and_empty_query_is_refused():
    def boom(req, timeout):
        raise OSError("offline")
    assert search.search("q", opener=boom, environ={})[0] is False
    assert search.search("  ", opener=boom, environ={})[0] is False


def test_search_is_a_network_call_for_the_permission_mode(tmp_path):
    assert tool_class("web_search") == "network"
    s = new_session(build_agent([ScriptBackend(['TOOL web_search {"query": "x"}', "ok"])]),
                    str(tmp_path), mode="plan")
    s.turn("look it up")
    result = [e.content for e in s.ledger.entries if e.kind == "tool_result"][0]
    assert result.startswith("[denied]")
