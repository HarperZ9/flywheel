"""live_feeds.py -- fresh signal across every operator domain, with provenance.

The intake half that feeds.py (the normalization layer + domain map) was
always waiting for: a curated roster of public feeds per domain, fetched
through the gather lane so every item carries provenance, and tagged with
the domain it serves. Art, science, accountability, programming, design,
marketing -- the same surface a person, a model, and the desktop all read.

Honesty mechanics: a dead feed is a NAMED error while the rest arrive; the
roster itself ships in the payload so coverage is visible, never silently
capped; and nothing here fetches until a caller asks (a fetch is a request,
not a heartbeat)."""
from __future__ import annotations

import json
import subprocess

SCHEMA = "flywheel.feeds/v1"
_TIMEOUT = 60

# The curated per-domain roster. Public feeds only; extend deliberately.
FEED_ROSTER: dict = {
    "science": [
        ("arxiv cs.AI", "https://rss.arxiv.org/rss/cs.AI"),
        ("arxiv cs.SE", "https://rss.arxiv.org/rss/cs.SE"),
    ],
    "programming": [
        ("hacker news", "https://news.ycombinator.com/rss"),
        ("lobsters", "https://lobste.rs/rss"),
    ],
    "art": [
        ("colossal", "https://www.thisiscolossal.com/feed/"),
    ],
    "design": [
        ("smashing magazine", "https://www.smashingmagazine.com/feed/"),
    ],
    "marketing": [
        ("seth godin", "https://seths.blog/feed/"),
    ],
    "accountability": [
        ("lesswrong", "https://www.lesswrong.com/feed.xml"),
        ("alignment forum", "https://www.alignmentforum.org/feed.xml"),
    ],
}


def _shell(argv: list) -> tuple:
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           timeout=_TIMEOUT, shell=False)
        return (p.returncode, p.stdout or p.stderr or "")
    except subprocess.TimeoutExpired:
        return (124, f"timed out after {_TIMEOUT}s")
    except OSError as e:
        return (127, f"{type(e).__name__}: {e}")


def _items(raw: str) -> list:
    try:
        doc = json.loads(raw)
    except ValueError:
        return []
    rows = None
    if isinstance(doc, dict):
        for key in ("items", "catalog", "results", "entries"):
            if isinstance(doc.get(key), list):
                rows = doc[key]
                break
    elif isinstance(doc, list):
        rows = doc
    return [r for r in rows or [] if isinstance(r, dict)]


def live_feeds(domain: "str | None" = None, *, runner=None,
               max_items: int = 8) -> dict:
    """Fetch the roster (one domain, or all) through gather's feed verb.
    Items: {id, title, url, feed, domain}. Errors: {feed name: message}."""
    runner = runner or _shell
    if domain is not None and domain not in FEED_ROSTER:
        return {"error": f"unknown domain '{domain}'; roster: "
                         f"{sorted(FEED_ROSTER)}"}
    domains = [domain] if domain else sorted(FEED_ROSTER)
    items, errors = [], {}
    for d in domains:
        for name, url in FEED_ROSTER[d]:
            rc, raw = runner(["gather", "feed", url, "--json"])
            if rc != 0:
                errors[name] = raw.strip()[-200:]
                continue
            for r in _items(raw)[:max_items]:
                items.append({"id": str(r.get("id", "")),
                              "title": str(r.get("title", "")),
                              "url": str(r.get("url", r.get("ref", ""))),
                              "feed": name, "domain": d})
    return {"schema": SCHEMA, "domains": domains,
            "roster": {d: [n for n, _ in FEED_ROSTER[d]] for d in domains},
            "items": items, "errors": errors,
            "note": "items carry gather provenance; a dead feed is a named "
                    "error, never a silent gap"}
