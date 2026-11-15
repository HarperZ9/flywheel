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
More than one call in twenty took 20 to 27 ms: on Windows a socket connect
made with a timeout sometimes comes back about 15 ms late, and the gateway
connects to its upstream that way. The budget sits above the slowest warm
calls in the published run, so a median would need most calls to be slower
than the worst ones measured, and it is a quarter of the 200 ms the control
adds.

On CI (2026-11-14, four runs) Linux runners measured medians of 1.1 to 3.9
ms. Windows runners measured 2.1 to 7.0 ms in one run and 11.6 to 23.6 ms in
three. Each case prints what it measured, on a pass too, so a job log shows
the room that was left.

The Windows tail, and what was done about each of its two causes (2026-11-15).
This gate failed on Windows runners three times in two days with medians of
52 to 88 ms, on pull requests that changed no gateway code.

  1. The late connect, before the first byte. A Python socket with a timeout
     connects without blocking and then waits; on Windows that wait is a
     timer tick late in a quarter to a half of loopback connects. The gateway
     connected to its upstream that way. Fixed in the gateway: a loopback
     upstream is now connected blocking (harness/endpoints_connect.py, with
     the measurement).
  2. The disk commit, in the record step. In the failing run 43674784134 a
     streamed call showed its first text delta after 2.3 ms and its end after
     306.8 ms. Everything between the two is the ledger entry: one append and
     one `os.fsync`. The gateway commits each entry to the disk before it goes
     on, twice per call since the started entry was added, and how long the
     operating system takes inside `os.fsync` is the disk's time, not the
     gateway's. So the gate now measures the two apart. The ledger notes the
     seconds spent inside `os.fsync` (gateway_ledger_health), each call's
     sample has its own commit seconds taken out, and the 50 ms budget
     applies to what is left: the gateway's own work. The commit time is
     printed beside it with what a bare append-and-commit costs in the same
     folder with no gateway code involved, and the number of commits per call
     is asserted (two), so an added commit fails here.

What the figure leaves out: the provider's network time and TLS, the system
credential store (the key store here is in memory), the first call's module
loading, concurrency (one request at a time), and the time the operating
system spends inside `os.fsync`, which is reported and not budgeted.

Controls: 200 ms added inside the gateway must break the budget; so must 200
ms added to the ledger's write, just before the commit; a commit that takes
100 ms must leave the budgeted figure where it was and show up as commit
time; and a stub that waits four times as long must leave the overhead where
it was. A timing check that could not fail, or that counted the provider's
wait or the disk's as the gateway's, would say nothing.
"""
import statistics
import time

import pytest

from scripts import gateway_bench_rig as bench

# Run by publish.yml against the built wheel before a release is published.
pytestmark = pytest.mark.release_gate

BUDGET_SECONDS = 0.050
STUB_DELAY = 0.050
CALLS, WARMUP = 5, 2
CASES = [(path, stream, False) for path in bench.PATHS for stream in (False, True)]
CASES += [("/v1/messages", False, True), ("/v1/responses", True, True)]


COMMITS_PER_CALL = 2                    # the started entry and the end entry


def within_budget(samples: dict) -> bool:
    """The gateway's own time, with each call's disk commit seconds taken out."""
    return (bench.overhead(samples, 0, own=True) < BUDGET_SECONDS
            and bench.overhead(samples, 1, own=True) < BUDGET_SECONDS)


def commit_ms(samples: dict) -> list:
    return [round(total * 1000, 1) for _first, total, _count in samples["commit"]]


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
def test_the_gateway_adds_less_than_the_budget(tmp_path, no_real_store, capsys, path, stream,
                                               key):
    with bench.rig(tmp_path / "home", "openai", STUB_DELAY, key=key) as made:
        samples = bench.measure(made, path, stream, CALLS, WARMUP)
        served = [entry.kind for entry in made.ledger.entries]
        waits = list(made.stub.waits)
        charged = made.keys.row("bench")["totals"]["calls"] if key else None
        bare = sorted(bench.commit_cost(tmp_path / "home"))
    assert len(samples["gateway"]) == len(samples["direct"]) == CALLS
    spent = commit_ms(samples)
    with capsys.disabled():             # shown on a pass too: the room left on this runner
        print(f"\n  gateway overhead {path} {'stream' if stream else 'plain'} "
              f"{'key' if key else 'token'}: own first "
              f"{bench.overhead(samples, 0, own=True) * 1000:.1f} ms, own end "
              f"{bench.overhead(samples, 1, own=True) * 1000:.1f} ms (budget "
              f"{BUDGET_SECONDS * 1000:.0f}); with the disk's commits first "
              f"{bench.overhead(samples, 0) * 1000:.1f}, end "
              f"{bench.overhead(samples, 1) * 1000:.1f}; commits per call {spent} ms; a bare "
              f"commit here: median {statistics.median(bare) * 1000:.1f}, slowest "
              f"{bare[-1] * 1000:.1f} ms", end="")
    assert within_budget(samples), shown(samples)
    # Two commits per call, no more: the time inside them is not budgeted, so their
    # number is. A third commit added to a call fails here.
    assert [count for _first, _total, count in samples["commit"]] == [COMMITS_PER_CALL] * CALLS
    # Every gateway call reached the stub and was recorded: a call answered
    # without the upstream would be fast and would not be the thing measured.
    assert served == ["endpoint_call_started", "endpoint_call"] * (CALLS + WARMUP)
    assert len(waits) == 2 * (CALLS + WARMUP) and min(waits) >= STUB_DELAY * 0.9
    assert bench.overhead(samples, 0, own=True) > -0.010
    assert bench.overhead(samples, 1, own=True) > -0.010
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
    assert bench.overhead(samples, 0, own=True) >= 0.190
    assert bench.overhead(samples, 1, own=True) >= 0.190


def test_the_budget_fails_when_the_ledger_write_before_the_commit_adds_200_ms(
        tmp_path, monkeypatch):
    """Only the seconds inside `os.fsync` are the disk's. The write before it is budgeted."""
    from harness import gateway_ledger_health as health
    real = health._put

    def slow_put(file, data):
        time.sleep(0.200)
        return real(file, data)
    monkeypatch.setattr(health, "_put", slow_put)
    with bench.rig(tmp_path / "home", "openai", STUB_DELAY) as made:
        samples = bench.measure(made, "/v1/messages", False, 3, 1)
    assert not within_budget(samples), shown(samples)
    assert bench.overhead(samples, 1, own=True) >= 0.380      # two entries, 200 ms each


def test_a_slow_disk_commit_is_reported_and_not_counted_as_the_gateways_time(
        tmp_path, monkeypatch):
    """A commit that takes 100 ms: the budgeted figure stays, the commit figure shows it."""
    from harness import gateway_ledger_health as health
    real = health.os.fsync

    def slow_fsync(fd):
        time.sleep(0.100)
        return real(fd)
    with bench.rig(tmp_path / "home", "openai", STUB_DELAY) as made:
        quick = bench.measure(made, "/v1/messages", True, CALLS, 1)
        monkeypatch.setattr(health.os, "fsync", slow_fsync)
        slow = bench.measure(made, "/v1/messages", True, CALLS, 1)
    assert within_budget(slow), shown(slow)
    assert all(total >= 0.190 and count == COMMITS_PER_CALL
               for _first, total, count in slow["commit"]), slow["commit"]
    assert bench.overhead(slow, 1) >= 0.190                   # the whole figure does move
    for which in (0, 1):                                      # the gateway's own does not
        moved = abs(bench.overhead(slow, which, own=True) - bench.overhead(quick, which, own=True))
        assert moved < BUDGET_SECONDS, (shown(quick), shown(slow))
