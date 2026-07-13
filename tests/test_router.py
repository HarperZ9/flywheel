"""capability-router falsifier — friction goes to the best-in-class cog, every time.

The router is the connective tissue: each known friction category routes to a
distinct organ; unknown friction routes to triage (never a guessed handler); every
route carries a receipt binding friction -> handler.
"""
import pytest

from harness.router import (classify, route, flow, Friction, HANDLERS,
                            handled_categories, UNKNOWN)


CASES = [
    ({"stage": "oracle", "rc": 127}, "ENV_ERROR", "escalation"),
    ({"stage": "oracle", "compile_failed": True}, "SYNTAX_FAIL", "escalation.CompileOracle"),
    ({"stage": "oracle", "passed": False}, "LOGIC_FAIL", "search.best_of_n"),
    ({"stage": "search", "correlation": 0.95}, "LOW_DIVERSITY", "budget_control.steer"),
    ({"stage": "witness", "verdict": "DRIFT"}, "STALE_KNOWLEDGE", "wiki.verify"),
    ({"stage": "witness", "verdict": "UNVERIFIABLE"}, "UNVERIFIABLE", "transitive_witness.verify_frontier"),
    ({"stage": "cache", "cache_stale": True}, "STALE_CACHE", "cache.knowledge_hash"),
    ({"stage": "loop", "repeat_of": "abc123"}, "REPEAT_FAILURE", "failure_corpus.record_if_rejected"),
    ({"stage": "cal", "oracle_false_accept": True}, "UNCALIBRATED_ORACLE", "calibration.require_calibrated"),
    ({"stage": "cache", "cache_hit": True}, "REPEAT_TASK", "proof_cache.proof_lookup"),
]


@pytest.mark.parametrize("signal,cat,handler", CASES, ids=[c[1] for c in CASES])
def test_friction_routes_to_best_in_class_cog(signal, cat, handler):
    f = classify(signal)
    assert f.category == cat, f"{signal} -> {f.category}, expected {cat}"
    r = route(f)
    assert r.handler == handler and r.receipt


def test_every_known_category_has_a_distinct_handler():
    handlers = [h for h, _ in HANDLERS.values()]
    assert len(set(handlers)) == len(handlers), "two categories share a handler (not best-in-class)"


def test_unknown_friction_triages_never_guesses():
    r = route(classify({"stage": "?", "mystery": True}))
    assert r.category == "UNKNOWN" and r.handler == UNKNOWN[0]  # triage, not a wrong route


def test_accepted_signal_routes_to_noop():
    r = route(classify({"stage": "oracle", "passed": True}))
    assert r.category == "NONE" and r.handler == "none"


def test_flow_routes_a_mixed_stream_each_to_its_cog():
    signals = [c[0] for c in CASES]
    routes = flow(signals)
    assert [r.handler for r in routes] == [c[2] for c in CASES]
    # receipts are unique per distinct friction
    assert len({r.receipt for r in routes}) == len(routes)


def test_receipt_binds_friction_to_handler():
    r1 = route(Friction("LOGIC_FAIL", "oracle", "x"))
    r2 = route(Friction("LOGIC_FAIL", "oracle", "x"))
    r3 = route(Friction("LOGIC_FAIL", "search", "x"))   # different stage
    assert r1.receipt == r2.receipt and r1.receipt != r3.receipt
