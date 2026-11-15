"""What a caller waits for the gateway, and how much of it is the gateway's own work.

Two budgets, both asserted, on medians of warm calls with the upstream's wait
taken out. Each call is sent straight to a loopback stub and through a real
gateway pointed at that stub (scripts/gateway_bench_rig.py); the stub holds
its first byte for 50 ms and its recorded wait is subtracted from every
sample. For a stream, the first byte means the first text delta a client can
read.

  TOTAL   what a caller waits: everything the gateway adds, the two disk
          commits of a call included (the started entry before the request
          leaves, the end entry before the reply is sent). Budget: TOTAL_BUDGET
          on the median of TOTAL_CALLS warm calls, to the first byte and to the
          end, for a plain and a streamed call with the gateway token and with
          a virtual key.
  OWN     the same with the seconds inside `os.fsync` taken out: the gateway's
          own work. Budget: 25 ms on the median of five warm calls, for
          /v1/messages and /v1/responses, streamed and not, and with a key.

Why two. A commit to the disk costs what the disk takes, and a CI runner's
disk sometimes takes 100 to 300 ms for one `os.fsync` (below). A single tight
budget over both failed on runners for the disk's reasons; a budget over the
gateway's own time alone, which the fifth review round left as the only one,
bounded nothing a caller could feel through the commits: the fourth
independent review planted 200 ms beside the commit and the gate passed. So
the total has its own budget, and the instrument was moved.

The instrument. The seconds inside `os.fsync` are taken by the rig's own
clock around the system call (`Rig.syscalls`). Until the sixth review round
they were taken from what the gateway's ledger reported about itself, so
anything the gateway did between its own two clock reads was counted as the
disk's. Now only the system call is the disk's. The ledger's own report is
compared with the rig's on every call and may differ by WINDOW_SLACK at most.
The number of commits per call is asserted (two).

Where the budgets come from.
  OWN, 25 ms: unchanged from the fifth round. Measured then: 1.3 to 3.4 ms on a
  Windows 11 machine, 1.4 to 3.5 ms on a Linux CI runner and 2.2 to 7.3 ms on
  a Windows CI runner (CI run 43683218626).
  TOTAL: see TOTAL_BUDGET below, with the measurement it was set from. If the
  total gate fails, read its message: it gives a bare commit measured in the
  same folder and says which it was. A slow disk (a bare commit's median of
  10 ms or more) is the runner's: say so and rerun that job once. Otherwise
  the gateway got slower: do not rerun it, and do not raise the budget
  without a measured cause.

What the figures leave out: the provider's network time and TLS, the system
credential store (the key store here is in memory), the first call's module
loading, and concurrency (one request at a time).

Controls, each a planted fault that must fail a budget:
  - 200 ms added inside the gateway: OWN and TOTAL fail;
  - 200 ms added to the ledger's write, just before the commit: both fail;
  - 200 ms hidden between the gateway's two clock reads around `os.fsync`
    (the fourth review's plant): OWN fails, TOTAL fails, and the ledger's
    report differs from the rig's clock by more than WINDOW_SLACK;
  - a disk whose commit takes 100 ms: OWN stays where it was, the commit
    figure shows it, and TOTAL fails, because a caller does wait for it;
  - a stub that waits four times as long leaves the overhead where it was.
A timing check that could not fail, or that counted the provider's wait as
the gateway's, would say nothing.
"""
import statistics
import time

import pytest

from scripts import gateway_bench_rig as bench

# Run by publish.yml against the built wheel before a release is published.
pytestmark = pytest.mark.release_gate

BUDGET_SECONDS = 0.025                  # OWN: the gateway's work, commits taken out
# TOTAL: what a caller waits, both commits included. Measured on GitHub's runners on
# 2026-11-15 by the test below (30 calls per case, four cases per job, 12 jobs,
# the "GATEWAY TOTAL" lines of the whole-suite logs): medians to the end of the reply
# 1.5 to 5.1 ms on Linux and 8.1 to 16.6 ms on Windows. On a Windows runner whose disk was busy
# the 90th percentile reached 105 ms and the slowest call 354 ms, with the median of
# that case still under 15 ms. 50 ms is three times the slowest median
# seen. On the reference Windows 11 machine the medians were 5.5 to 9.4 ms.
TOTAL_BUDGET = 0.050
TOTAL_CALLS = 30
WINDOW_SLACK = 0.005                    # the ledger's commit report against the rig's clock
SLOW_DISK = 0.010                       # a bare commit's median that marks a slow disk
STUB_DELAY = 0.050
CALLS, WARMUP = 5, 2
CASES = [(path, stream, False) for path in bench.PATHS for stream in (False, True)]
CASES += [("/v1/messages", False, True), ("/v1/responses", True, True)]
TOTAL_CASES = [("/v1/messages", False, False), ("/v1/messages", True, False),
               ("/v1/messages", False, True), ("/v1/responses", True, True)]


COMMITS_PER_CALL = 2                    # the started entry and the end entry


def within_budget(samples: dict) -> bool:
    """OWN: the gateway's own time, with each call's `os.fsync` seconds taken out."""
    return (bench.overhead(samples, 0, own=True) < BUDGET_SECONDS
            and bench.overhead(samples, 1, own=True) < BUDGET_SECONDS)


def within_total(samples: dict) -> bool:
    """TOTAL: what a caller waits, to the first byte and to the end, commits included."""
    return (bench.overhead(samples, 0) < TOTAL_BUDGET
            and bench.overhead(samples, 1) < TOTAL_BUDGET)


def honest_window(samples: dict) -> bool:
    """The ledger reports as commit time what the system call took, and no more."""
    return all(abs(reported - commit[1]) < WINDOW_SLACK and count == commit[2]
               for (reported, count), commit in zip(samples["reported"], samples["commit"]))


def commit_ms(samples: dict) -> list:
    return [round(total * 1000, 1) for _first, total, _count in samples["commit"]]


def shown(samples: dict) -> dict:
    """The samples in milliseconds, for an assertion message."""
    return {name: [tuple(round(value * 1000, 1) if isinstance(value, float) else value
                         for value in row) for row in rows]
            for name, rows in samples.items()}


def _spread(values: list) -> str:
    ranked = sorted(values)
    return (f"median {statistics.median(ranked) * 1000:.1f}, p90 "
            f"{ranked[int(0.9 * (len(ranked) - 1))] * 1000:.1f}, slowest "
            f"{ranked[-1] * 1000:.1f} ms")


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
    # Two commits per call, no more, counted at the system call. A third commit fails here.
    assert [count for _first, _total, count in samples["commit"]] == [COMMITS_PER_CALL] * CALLS
    # The ledger's own report of its commit time is the system call's time: nothing else
    # the gateway does is counted as the disk's.
    assert honest_window(samples), shown(samples)
    # Every gateway call reached the stub and was recorded: a call answered
    # without the upstream would be fast and would not be the thing measured.
    assert served == ["endpoint_call_started", "endpoint_call"] * (CALLS + WARMUP)
    assert len(waits) == 2 * (CALLS + WARMUP) and min(waits) >= STUB_DELAY * 0.9
    assert bench.overhead(samples, 0, own=True) > -0.010
    assert bench.overhead(samples, 1, own=True) > -0.010
    if key:
        assert charged == CALLS + WARMUP


@pytest.mark.parametrize("path,stream,key", TOTAL_CASES)
def test_what_a_caller_waits_with_both_commits_is_within_the_total_budget(
        tmp_path, no_real_store, capsys, path, stream, key):
    """TOTAL: the median of TOTAL_CALLS warm calls, both disk commits included."""
    with bench.rig(tmp_path / "home", "openai", STUB_DELAY, key=key) as made:
        samples = bench.measure(made, path, stream, TOTAL_CALLS, WARMUP)
        bare = bench.commit_cost(tmp_path / "home", 100)
    direct = [statistics.median(row[which] for row in samples["direct"]) for which in (0, 1)]
    first = [row[0] - direct[0] for row in samples["gateway"]]
    total = [row[1] - direct[1] for row in samples["gateway"]]
    with capsys.disabled():             # the measurement the budget is set from, on every run
        print(f"\n  GATEWAY TOTAL {path} {'stream' if stream else 'plain'} "
              f"{'key' if key else 'token'} ({TOTAL_CALLS} calls, budget "
              f"{TOTAL_BUDGET * 1000:.0f} ms on the median): first {_spread(first)}; end "
              f"{_spread(total)}; the two commits of a call "
              f"{_spread([row[1] for row in samples['commit']])}; own end "
              f"{bench.overhead(samples, 1, own=True) * 1000:.1f} ms; a bare commit here "
              f"(100): {_spread(bare)}", end="")
    assert [count for _first, _total, count in samples["commit"]] == (
        [COMMITS_PER_CALL] * TOTAL_CALLS)
    slow_disk = statistics.median(bare) >= SLOW_DISK
    assert within_total(samples), (
        "what a caller waits is over the total budget. A bare commit in the same folder took "
        f"a median of {statistics.median(bare) * 1000:.1f} ms: "
        + ("the disk was slow during this run. Say so and rerun this job once."
           if slow_disk else "the disk was not slow, so the gateway is. Do not rerun."),
        shown(samples))
    assert within_budget(samples) and honest_window(samples), shown(samples)


def test_the_stub_wait_is_subtracted_not_counted(tmp_path):
    """A stub four times slower leaves the gateway's share where it was."""
    with bench.rig(tmp_path / "a", "openai", STUB_DELAY) as made:
        short = bench.measure(made, "/v1/messages", True, CALLS, 1)
    with bench.rig(tmp_path / "b", "openai", STUB_DELAY * 4) as made:
        long = bench.measure(made, "/v1/messages", True, CALLS, 1)
        waited = statistics.median(made.stub.waits)
    assert waited >= STUB_DELAY * 4 * 0.9           # the calls really took four times as long
    assert within_budget(long), shown(long)
    # The stub gained 150 ms. A measurement that counted it would move by that much. The
    # comparison is on the gateway's own time: with the commits in it, five calls on a
    # Windows runner whose disk took 51 to 329 ms for the two commits of a call moved the
    # figure by 45 ms with no fault present (CI job 132804066113, 2026-11-15).
    for which in (0, 1):
        moved = abs(bench.overhead(long, which, own=True) - bench.overhead(short, which, own=True))
        assert moved < BUDGET_SECONDS, (shown(short), shown(long))


@pytest.mark.parametrize("path,stream", [("/v1/messages", False), ("/v1/responses", True)])
def test_the_budget_fails_when_the_gateway_adds_200_ms(tmp_path, path, stream):
    with bench.rig(tmp_path / "home", "openai", STUB_DELAY, gateway_delay=0.200) as made:
        samples = bench.measure(made, path, stream, 3, 1)
    assert not within_budget(samples), shown(samples)
    assert not within_total(samples), shown(samples)
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
    assert not within_total(samples), shown(samples)
    assert bench.overhead(samples, 1, own=True) >= 0.380      # two entries, 200 ms each


@pytest.mark.parametrize("stream", [False, True])
def test_200_ms_hidden_inside_the_commit_window_fails_every_gate(tmp_path, stream):
    """The fourth review's plant. 200 ms of gateway time placed between the two clock
    reads the ledger takes around `os.fsync` used to be counted as the disk's: the gate
    passed with 400 ms added to every call. The rig's clock is at the system call now."""
    import os
    with bench.rig(tmp_path / "home", "openai", STUB_DELAY) as made:
        at_the_system_call = os.fsync   # the rig's timed call

        def padded(fd):                 # what the gateway calls: slow work, then the commit
            time.sleep(0.200)
            return at_the_system_call(fd)
        os.fsync = padded
        try:
            samples = bench.measure(made, "/v1/messages", stream, 3, 1)
        finally:
            os.fsync = at_the_system_call
    assert not within_budget(samples), shown(samples)
    assert not within_total(samples), shown(samples)
    assert not honest_window(samples), shown(samples)
    assert bench.overhead(samples, 1, own=True) >= 0.380      # two commits, 200 ms beside each
    assert bench.overhead(samples, 0, own=True) >= (0.190 if stream else 0.380)


def test_a_slow_disk_commit_is_the_disks_time_and_still_breaks_what_a_caller_waits(tmp_path):
    """A commit that takes 100 ms. OWN stays where it was and the commit figure shows the
    disk; TOTAL fails, because the caller waits for both commits."""
    with bench.rig(tmp_path / "quick", "openai", STUB_DELAY) as made:
        quick = bench.measure(made, "/v1/messages", True, CALLS, 1)
    with bench.rig(tmp_path / "slow", "openai", STUB_DELAY, disk_delay=0.100) as made:
        slow = bench.measure(made, "/v1/messages", True, CALLS, 1)
    assert within_budget(slow) and honest_window(slow), shown(slow)
    assert all(total >= 0.190 and count == COMMITS_PER_CALL
               for _first, total, count in slow["commit"]), slow["commit"]
    assert bench.overhead(slow, 1) >= 0.190                   # the whole figure does move
    assert bench.overhead(slow, 0) >= 0.090                   # one commit before the first byte
    assert not within_total(slow), shown(slow)
    for which in (0, 1):                                      # the gateway's own does not
        moved = abs(bench.overhead(slow, which, own=True) - bench.overhead(quick, which, own=True))
        assert moved < BUDGET_SECONDS, (shown(quick), shown(slow))
