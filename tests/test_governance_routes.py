"""The governance routes: the tier vocabulary is published, and a word
outside it is the caller's mistake rather than the engine's failure.

A client that kept its own copy of the consequence vocabulary would drift the
day an override is added, and would offer the operator a token the engine
refuses. So the engine publishes the list, and the classify route answers 400
for an unknown word: left uncaught the ValueError surfaced as a 500, which
tells the operator the engine broke rather than that the word was wrong."""
import harness.gateway as gateway
from harness.governance.tadr_tier import (T2_OVERRIDES, T3_OVERRIDES,
                                          TADR_MODIFIERS)


class _H:
    def get(self, key, default=None):
        return "0" if key == "Content-Length" else default


def _get(path):
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = path
    handler.headers = _H()
    sent = {}
    handler._json = lambda body, code=200: sent.update(body=body, code=code)
    handler._get()
    return sent


def test_the_tier_route_publishes_the_vocabulary_the_engine_accepts():
    sent = _get("/api/governance/tiers")
    assert sent["code"] == 200
    body = sent["body"]
    assert body["t2_overrides"] == sorted(T2_OVERRIDES)
    assert body["t3_overrides"] == sorted(T3_OVERRIDES)
    assert body["modifiers"] == sorted(TADR_MODIFIERS)
    # Sorted, so a client rendering the list in order shows the same order on
    # every machine rather than whatever a set iteration happened to give.
    assert body["t3_overrides"] == sorted(body["t3_overrides"])
    assert set(body["t2_overrides"]).isdisjoint(body["t3_overrides"])


def test_every_published_override_actually_classifies():
    published = _get("/api/governance/tiers")["body"]
    for word in published["t3_overrides"]:
        sent = _get(f"/api/governance/classify?override={word}")
        assert sent["code"] == 200, word
        assert sent["body"]["tier"] == "T3", word
    for word in published["t2_overrides"]:
        sent = _get(f"/api/governance/classify?override={word}")
        assert sent["code"] == 200, word
        assert sent["body"]["tier"] == "T2", word


def test_no_override_is_t1_rather_than_an_error():
    sent = _get("/api/governance/classify")
    assert sent["code"] == 200 and sent["body"]["tier"] == "T1"


def test_a_word_outside_the_vocabulary_is_a_400_not_a_500():
    sent = _get("/api/governance/classify?override=make-it-fast")
    assert sent["code"] == 400
    assert "invalid consequence overrides" in sent["body"]["error"]
    assert "make-it-fast" in sent["body"]["error"]
