"""Live feeds must stay honest under partial failure: every feed fetch is
provenance-carrying gather output, a dead feed is a named error while the
rest arrive, and the domain roster is visible so coverage is never
silently capped."""

import json

from harness.live_feeds import FEED_ROSTER, SCHEMA, live_feeds

CATALOG = json.dumps({"items": [
    {"id": "a1", "title": "Fine line plotters", "url": "https://x/a1"},
    {"id": "a2", "title": "Scanline shaders", "url": "https://x/a2"},
]})


def _runner(fail_urls=()):
    def run(argv):
        url = argv[2]
        if url in fail_urls:
            return (1, "fetch failed: 429")
        return (0, CATALOG)
    return run


def test_roster_covers_the_operator_domains():
    for domain in ("science", "programming", "art", "design",
                   "marketing", "accountability"):
        assert FEED_ROSTER.get(domain), f"no feeds for {domain}"


def test_feeds_arrive_tagged_with_domain_and_feed():
    doc = live_feeds(domain="art", runner=_runner())
    assert doc["schema"] == SCHEMA
    assert doc["items"]
    assert all(i["domain"] == "art" for i in doc["items"])
    assert all(i["feed"] for i in doc["items"])
    assert doc["errors"] == {}


def test_dead_feed_is_named_while_the_rest_arrive():
    urls = [u for _, u in FEED_ROSTER["programming"]]
    doc = live_feeds(domain="programming", runner=_runner(fail_urls={urls[0]}))
    assert len(doc["errors"]) == 1
    assert doc["items"]  # the surviving feed still delivered


def test_unknown_domain_is_a_named_error():
    doc = live_feeds(domain="astrology", runner=_runner())
    assert "error" in doc
    assert "astrology" in doc["error"]
