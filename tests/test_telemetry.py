"""Telemetry must count the checks actually performed on cache hits."""
from pathlib import Path
from harness.cache import ReceiptCache
from harness.loop import run_loop
from harness.oracle import PytestOracle
from harness.proposer import StubProposer
from harness.task import load_task
from harness.telemetry import signal_from_result


def test_cache_hit_counts_actual_oracle_invocation(tmp_path):
    class CountingOracle(PytestOracle):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def verify(self, candidate, task):
            self.calls += 1
            return super().verify(candidate, task)

    fixture = Path(__file__).resolve().parent.parent / "tasks" / "example_pass"
    task = load_task(fixture, workdir=tmp_path / "work")
    oracle, cache = CountingOracle(), ReceiptCache(tmp_path / "cache")
    kwargs = dict(cache=cache, envelopes_dir=tmp_path / "envelopes")
    first = run_loop(task, StubProposer("def add(a,b): return a+b"), oracle, **kwargs)
    before = oracle.calls
    repeat = run_loop(task, StubProposer("raise AssertionError('cache miss')"), oracle, **kwargs)
    assert first.accepted and repeat.cache_hit and repeat.accepted
    assert oracle.calls - before == 1
    signal = signal_from_result(repeat)
    assert signal.oracle_calls == oracle.calls - before == repeat.envelope.budget_spent["oracle_calls"]
    assert "cache" in signal.chain_stages and "verify" in signal.chain_stages
    assert signal.candidates == 0
