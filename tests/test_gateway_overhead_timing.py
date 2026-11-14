"""The gateway's own time per call, with the upstream's wait taken out.

Budget: 50 ms of gateway time, to the first byte and to the end of the reply,
as the median of five warm calls after two warm-up calls. It holds for
/v1/messages and /v1/responses, streamed and not, with the gateway token, and
for one plain and one streamed call with a virtual key. Each call is sent
straight to a loopback stub and through a real gateway pointed at that stub
(scripts/gateway_bench_rig.py); the stub holds its first byte for 50 ms and
its recorded wait is subtracted from every sample. For a stream, the first
byte means the first text delta a client can read.

Where the budget comes from: 30 warm calls per case on Windows 11 with Python
3.12.10, measured 2026-11-14 while other work ran on the machine
(scripts/bench_gateway_overhead.py; figures in docs/BENCHMARKS.md). Medians
were 1 to 2 ms with the gateway token and 1.5 to 3.5 ms with a virtual key.
About one call in ten took 13 to 25 ms longer, and so did calls sent to the
stub alone: opening a connection to a threaded standard-library HTTP server
has that tail on that machine. The budget sits above the slowest warm calls
in the published run, so a median would need most calls to be slower than the
worst ones measured, and it is a quarter of the 200 ms the control adds. A
shared CI runner several times slower than the measured machine still fits.

What the figure leaves out: the provider's network time and TLS, the system
credential store (the key store here is in memory), the first call's module
loading, and concurrency (one request at a time).

Controls: 200 ms added inside the gateway must break the budget, and a stub
that waits four times as long must leave the overhead where it was. A timing
check that could not fail, or that counted the provider's wait as the
gateway's, would say nothing.
"""
import statistics

import pytest

from scripts import gateway_bench_rig as bench

BUDGET_SECONDS = 0.050
STUB_DELAY = 0.050
CALLS, WARMUP = 5, 2
CASES = [(path, stream, False) for path in bench.PATHS for stream in (False, True)]
CASES += [("/v1/messages", False, True), ("/v1/responses", True, True)]


def within_budget(samples: dict) -> bool:
    return (bench.overhead(samples, 0) < BUDGET_SECONDS
            and bench.overhead(samples, 1) < BUDGET_SECONDS)


def shown(samples: dict) -> dict:
    """The samples in milliseconds, for an assertion message."""
    return {name: [(round(first * 1000, 1), round(total * 1000, 1)) for first, total in rows]
            for name, rows in samples.items()}


@pytest.fixture
def no_real_store(monkeypatch):
    """A test that reached the system credential store would fail, not write to it."""
    from harness import keychain

    def reached(*args, **kwargs):
        raise AssertionError("a test reached the real credential store")
    for name in ("keychain_get", "keychain_set", "keychain_delete"):
        monkeypatch.setattr(keychain, name, reached)


@pytest.mark.parametrize("path,stream,key", CASES)
def test_the_gateway_adds_less_than_the_budget(tmp_path, no_real_store, path, stream, key):
    with bench.rig(tmp_path / "home", "openai", STUB_DELAY, key=key) as made:
        samples = bench.measure(made, path, stream, CALLS, WARMUP)
        served = [entry.kind for entry in made.ledger.entries]
        waits = list(made.stub.waits)
        charged = made.keys.row("bench")["totals"]["calls"] if key else None
    assert len(samples["gateway"]) == len(samples["direct"]) == CALLS
    print("overhead ms", path, stream, key, round(bench.overhead(samples, 0) * 1000, 2),
          round(bench.overhead(samples, 1) * 1000, 2))
    assert within_budget(samples), shown(samples)
    # Every gateway call reached the stub and was recorded: a call answered
    # without the upstream would be fast and would not be the thing measured.
    assert served == ["endpoint_call"] * (CALLS + WARMUP)
    assert len(waits) == 2 * (CALLS + WARMUP) and min(waits) >= STUB_DELAY * 0.9
    assert bench.overhead(samples, 0) > -0.010 and bench.overhead(samples, 1) > -0.010
    if key:
        assert charged == CALLS + WARMUP


def test_the_stub_wait_is_subtracted_not_counted(tmp_path):
    """A stub four times slower leaves the gateway's share where it was."""
    with bench.rig(tmp_path / "a", "openai", STUB_DELAY) as made:
        short = bench.measure(made, "/v1/messages", True, CALLS, 1)
    with bench.rig(tmp_path / "b", "openai", STUB_DELAY * 4) as made:
        long = bench.measure(made, "/v1/messages", True, CALLS, 1)
        waited = statistics.median(made.stub.waits)
    assert waited >= STUB_DELAY * 4 * 0.9           # the calls really took four times as long
    assert within_budget(long), shown(long)
    # The stub gained 150 ms. A measurement that counted it would move by that much.
    for which in (0, 1):
        moved = abs(bench.overhead(long, which) - bench.overhead(short, which))
        assert moved < BUDGET_SECONDS, (shown(short), shown(long))


@pytest.mark.parametrize("path,stream", [("/v1/messages", False), ("/v1/responses", True)])
def test_the_budget_fails_when_the_gateway_adds_200_ms(tmp_path, path, stream):
    with bench.rig(tmp_path / "home", "openai", STUB_DELAY, gateway_delay=0.200) as made:
        samples = bench.measure(made, path, stream, 3, 1)
    assert not within_budget(samples), shown(samples)
    assert bench.overhead(samples, 0) >= 0.190 and bench.overhead(samples, 1) >= 0.190
