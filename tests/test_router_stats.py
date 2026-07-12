"""test_router_stats.py — cost/quality-aware routing is correct and persisted.

Success criteria:
  - record updates the table; a success resets the failure streak.
  - score prefers higher success rate and cheaper cost; unseen gets an optimistic prior.
  - the circuit breaker opens after N consecutive failures and closes on a success.
  - order() puts the best provider first and circuit-open ones last.
  - stats persist across instances (JSON round-trip).
"""
from harness.router_stats import RouterStats


def test_record_and_success_rate():
    rs = RouterStats()
    rs.record("a", True, latency=0.5)
    rs.record("a", False, latency=1.5)
    s = rs.stats["a"]
    assert s.attempts == 2 and s.successes == 1 and s.failures == 1
    assert s.success_rate == 0.5 and s.mean_latency == 1.0


def test_success_resets_failure_streak():
    rs = RouterStats(circuit_threshold=3)
    for _ in range(2):
        rs.record("a", False)
    assert rs.stats["a"].consecutive_failures == 2
    rs.record("a", True)
    assert rs.stats["a"].consecutive_failures == 0


def test_unseen_provider_is_optimistic_and_cost_matters():
    rs = RouterStats(cost={"cheap": 1.0, "pricey": 2.0})
    assert rs.score("never-seen") == 1.0                 # optimistic prior at cost 1
    # equal outcomes, cheaper wins
    for _ in range(5):
        rs.record("cheap", True)
        rs.record("pricey", True)
    assert rs.score("cheap") > rs.score("pricey")


def test_score_prefers_higher_success_rate():
    rs = RouterStats()
    for _ in range(10):
        rs.record("good", True)
    for _ in range(10):
        rs.record("bad", False)
    assert rs.score("good") > rs.score("bad")


def test_circuit_breaker_opens_and_closes():
    rs = RouterStats(circuit_threshold=3)
    assert not rs.is_circuit_open("a")
    for _ in range(3):
        rs.record("a", False)
    assert rs.is_circuit_open("a")
    rs.record("a", True)
    assert not rs.is_circuit_open("a")


def test_order_best_first_and_tripped_last():
    rs = RouterStats(circuit_threshold=3)
    for _ in range(10):
        rs.record("b", True)
    for _ in range(10):
        rs.record("c", True)
    for _ in range(2):
        rs.record("c", False)          # c degraded but stays below the circuit threshold
    for _ in range(3):
        rs.record("a", False)          # a circuit-open
    order = rs.order(["a", "b", "c"])
    assert order == ["b", "c", "a"]    # best first, degraded next, circuit-open last


def test_stats_persist_across_instances(tmp_path):
    p = tmp_path / "router_stats.json"
    rs = RouterStats(p)
    rs.record("a", True)
    rs.record("a", False)
    reloaded = RouterStats(p)
    assert reloaded.stats["a"].attempts == 2
    assert reloaded.snapshot()["providers"]["a"]["success_rate"] == 0.5
