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


def test_persistence_is_atomic_and_thread_safe(tmp_path):
    import threading
    from harness.router_stats import RouterStats
    rs = RouterStats(path=tmp_path / "stats.json")
    def hammer(name):
        for _ in range(50):
            rs.record(name, True, 0.01)
    threads = [threading.Thread(target=hammer, args=(f"p{i%4}",)) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    # the file is always valid JSON (atomic replace, never a torn write)
    import json
    reloaded = RouterStats(path=tmp_path / "stats.json")
    assert sum(s.attempts for s in reloaded.stats.values()) == 400
    # no stray temp file left behind
    assert not (tmp_path / "stats.json.tmp").exists()


def test_corrupt_stats_file_is_quarantined_not_fatal(tmp_path):
    from harness.router_stats import RouterStats
    p = tmp_path / "stats.json"
    p.write_text("{ this is not valid json", encoding="utf-8")
    rs = RouterStats(path=p)        # must not raise
    assert rs.stats == {}
    assert p.with_suffix(".corrupt").exists()


def test_one_success_does_not_outrank_a_proven_provider():
    from harness.router_stats import RouterStats
    rs = RouterStats()
    # a provider with a single minted success
    rs.record("fresh", True)
    # a provider proven over 1000 attempts at 99.9%
    for _ in range(999):
        rs.record("proven", True)
    rs.record("proven", False)
    # the proven provider must not be outranked by one lucky/minted success:
    # the score uses a lower confidence bound, so thin evidence cannot leap
    # ahead of a long track record
    assert rs.score("proven") > rs.score("fresh"), (
        rs.score("proven"), rs.score("fresh"))
    # an entirely unseen provider still gets an optimistic prior (exploration)
    assert rs.score("unseen") >= rs.score("proven") * 0.5
