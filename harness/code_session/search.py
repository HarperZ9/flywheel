"""search.py -- the session's `web_search` tool.

Three sources, the first one configured wins:

  SEARXNG_URL     a SearXNG instance you run or trust (JSON API)
  BRAVE_API_KEY   Brave Search API
  (neither)       DuckDuckGo's HTML endpoint, no key needed

Returns up to 8 results as title, URL and snippet, and names the source used.
A search is a network call under the same permission as `web_fetch`: it asks in
ask and edit, runs in auto, and is refused in plan; rules match the query text
as `web_search:<pattern>`.
"""
from __future__ import annotations

import html
import json
import os
import re
import urllib.parse
import urllib.request

MAX_RESULTS = 8
TIMEOUT = 15
UA = {"User-Agent": "flywheel-code (web_search)"}


def _get(url: str, opener, headers=None) -> bytes:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with opener(req, timeout=TIMEOUT) as resp:
        return resp.read(1024 * 1024)


def _strip(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def searxng(query: str, base: str, opener) -> list:
    data = json.loads(_get(f"{base.rstrip('/')}/search?" + urllib.parse.urlencode(
        {"q": query, "format": "json"}), opener))
    return [(r.get("title", ""), r.get("url", ""), r.get("content", ""))
            for r in data.get("results", [])]


def brave(query: str, key: str, opener) -> list:
    data = json.loads(_get("https://api.search.brave.com/res/v1/web/search?" +
                           urllib.parse.urlencode({"q": query, "count": MAX_RESULTS}), opener,
                           {"X-Subscription-Token": key, "Accept": "application/json"}))
    return [(r.get("title", ""), r.get("url", ""), _strip(r.get("description", "")))
            for r in (data.get("web") or {}).get("results", [])]


def duckduckgo(query: str, opener) -> list:
    page = _get("https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query}),
                opener).decode("utf-8", "replace")
    out = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)'
                         r'(?:class="result__snippet"[^>]*>(.*?)</a>|$)', page, re.S):
        href = html.unescape(m.group(1))
        target = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query).get("uddg", [href])[0]
        out.append((_strip(m.group(2)), target, _strip(m.group(4) or "")))
    return out


def search(query: str, *, opener=urllib.request.urlopen, environ=None) -> "tuple[bool, str]":
    env = os.environ if environ is None else environ
    query = query.strip()
    if not query:
        return False, "[error] web_search needs a 'query'"
    try:
        if env.get("SEARXNG_URL"):
            source, rows = "searxng", searxng(query, env["SEARXNG_URL"], opener)
        elif env.get("BRAVE_API_KEY"):
            source, rows = "brave", brave(query, env["BRAVE_API_KEY"], opener)
        else:
            source, rows = "duckduckgo", duckduckgo(query, opener)
    except Exception as e:                      # a failed search is a result, not a crash
        return False, f"[error] search failed: {e.__class__.__name__}: {e}"[:300]
    rows = [r for r in rows if r[1]][:MAX_RESULTS]
    if not rows:
        return True, f"[{source}] no results for {query!r}"
    lines = [f"[{source}] {len(rows)} result(s) for {query!r}"]
    for i, (title, url, snippet) in enumerate(rows, 1):
        lines.append(f"{i}. {title}\n   {url}\n   {snippet[:240]}")
    return True, "\n".join(lines)
