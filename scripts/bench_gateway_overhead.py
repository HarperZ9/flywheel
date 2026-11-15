"""bench_gateway_overhead.py -- what the gateway adds to one model call.

    python scripts/bench_gateway_overhead.py            # table + JSON record
    python scripts/bench_gateway_overhead.py --calls 100 --out my-run.json

For each case the same request is sent straight to a loopback stub provider
and through a real gateway HTTP server pointed at that stub, in turns, one
request at a time. The stub waits a fixed time before its first byte and notes
how long it held each request; that wait is taken out of each call, so the
difference of the two medians is what a caller waits for the gateway: its HTTP
server, the credential check, parsing, the second connection, rendering, the
two ledger entries of a call, each committed to the disk (the started entry
before the request leaves, the end entry before the reply is sent), and, for
a virtual key, the key lookup and the debit. The record also gives the two
commits on their own, what is left without them, and what a bare commit costs
on the same disk.

Two times per call: to the first byte (for a stream, to the first text delta
a client can read) and to the end of the body. Warm-up calls are thrown away.
The first call after a gateway starts also pays for modules the gateway loads
on first use; it is measured in a fresh process and reported on its own.

What this leaves out: the provider's network time and TLS, the real system
credential store (the key store here is in memory), any hosted provider, and
concurrency. It is a single client, so the figures are not comparable with
figures other gateways publish at a request rate.

No provider is called and nothing is spent. The record goes to
docs/benchmarks/gateway-overhead.json; `python scripts/build_benchmark_page.py`
then renders it into docs/BENCHMARKS.md.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts import gateway_bench_rig as bench  # noqa: E402
from scripts.gateway_bench_machine import machine  # noqa: E402

RECORD = REPO / "docs" / "benchmarks" / "gateway-overhead.json"
STUB_DELAY = 0.05
# (path, upstream dialect, caller). Messages to an Anthropic upstream is the
# pass-through path; every other pair is translated.
GROUPS = (("/v1/messages", "openai", "owner"), ("/v1/messages", "anthropic", "owner"),
          ("/v1/responses", "openai", "owner"), ("/v1/messages", "openai", "key"),
          ("/v1/responses", "openai", "key"))
# What the breakdown times: label -> (module, owner class or None, attribute).
PARTS = {
    "key lookup": ("gateway_key_gate", None, "admits"),
    "request body read and JSON parse": ("gateway_interfaces", None, "_body"),
    "limit and allow-list check": ("gateway_key_gate", None, "enter"),
    "upstream choice": ("gateway_turn", None, "resolve_upstream"),
    "upstream connect, send and wait, plain (includes the stub delay)":
        ("gateway_turn_call", None, "_post"),
    "upstream connect, send and wait, stream (includes the stub delay)":
        ("gateway_turn_call", None, "_open"),
    "reply read into the neutral form": ("gateway_turn_call", None, "read"),
    "started entry, committed before the request leaves": ("gateway_calls", None, "begin"),
    "key debit": ("gateway_key_gate", "Bill", "settle"),
    "end entry, with the debit inside it": ("gateway_turn", None, "record"),
    "receipt": ("gateway_turn", None, "receipt"),
    "whole handler, from the body read to the last byte written":
        ("gateway_interfaces", None, "serve"),
}


def _ms(seconds: float) -> float:
    return round(seconds * 1000, 2)


def _p95(values: list) -> float:
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def summarize(samples: dict) -> dict:
    """Milliseconds for one case, each sample net of the stub's wait: the two
    medians, their difference, and the gateway's slow calls less the stub median."""
    commits = [row[1] for row in samples["commit"]]
    out = {"calls": len(samples["gateway"]),
           "commits_per_call": sorted({row[2] for row in samples["commit"]}),
           "commits_median_ms": _ms(statistics.median(commits)),
           "commits_p95_ms": _ms(_p95(commits)),
           "own_total_median_ms": _ms(bench.overhead(samples, 1, own=True))}
    for which, name in ((0, "first"), (1, "total")):
        direct = statistics.median(row[which] for row in samples["direct"])
        through = [row[which] for row in samples["gateway"]]
        alone = [row[which] for row in samples["direct"]]
        out[name] = {"stub_median_ms": _ms(direct),
                     "stub_p95_over_its_median_ms": _ms(_p95(alone) - direct),
                     "gateway_median_ms": _ms(statistics.median(through)),
                     "overhead_median_ms": _ms(statistics.median(through) - direct),
                     "overhead_p95_ms": _ms(_p95(through) - direct),
                     "overhead_max_ms": _ms(max(through) - direct)}
    return out


def run_cases(calls: int, warmup: int) -> list:
    rows = []
    for path, dialect, caller in GROUPS:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            with bench.rig(Path(tmp) / "home", dialect, STUB_DELAY,
                           key=caller == "key") as made:
                for stream in (False, True):
                    samples = bench.measure(made, path, stream, calls, warmup)
                    rows.append({"interface": path, "upstream": dialect, "caller": caller,
                                 "stream": stream, **summarize(samples)})
    return rows


def cold(path: str, stream: bool) -> float:
    """Seconds the first call through a fresh gateway takes beyond the stub's median."""
    body = json.dumps({**bench.BODIES[path], "stream": stream}).encode()
    marks = (bench.STUB_MARK["openai"], bench.GATEWAY_MARK[path]) if stream else (None, None)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        with bench.rig(Path(tmp) / "home", "openai", STUB_DELAY) as made:
            direct = [bench.call(made.stub.url, path, body, "none", marks[0])[1]
                      - made.stub.waits[-1] for _ in range(5)]
            first = bench.call(made.gateway, path, body, made.credential, marks[1])[1]
            return first - made.stub.waits[-1] - statistics.median(direct)


def run_cold() -> list:
    """The first call's cost, each in its own interpreter so nothing is loaded yet."""
    rows = []
    for path in bench.PATHS:
        for stream in (False, True):
            done = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--cold", path,
                 "--stream" if stream else "--plain"],
                capture_output=True, text=True, timeout=120, check=True)
            rows.append({"interface": path, "stream": stream,
                         "first_call_overhead_ms": _ms(float(done.stdout.strip()))})
    return rows


def breakdown(path: str, stream: bool, calls: int) -> dict:
    """Median milliseconds inside the named gateway functions, for a virtual key."""
    import importlib
    spent, undo = collections.defaultdict(list), []

    def timed(owner, attr, label):
        inner = getattr(owner, attr)

        def outer(*args, **kwargs):
            started = time.perf_counter()
            try:
                return inner(*args, **kwargs)
            finally:
                spent[label].append(time.perf_counter() - started)
        setattr(owner, attr, outer)
        undo.append((owner, attr, inner))
    for label, (module, cls, attr) in PARTS.items():
        owner = importlib.import_module(f"harness.{module}")
        timed(getattr(owner, cls) if cls else owner, attr, label)
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            with bench.rig(Path(tmp) / "home", "openai", STUB_DELAY, key=True) as made:
                bench.measure(made, path, stream, 0, warmup=3)
                spent.clear()
                samples = bench.measure(made, path, stream, calls, warmup=0)
    finally:
        for owner, attr, inner in undo:
            setattr(owner, attr, inner)
    return {"interface": path, "stream": stream, "caller": "key", "calls": calls,
            "overhead_total_median_ms": _ms(bench.overhead(samples, 1)),
            "parts_median_ms": {label: _ms(statistics.median(spent[label]))
                                for label in PARTS if spent[label]}}


def warm_compare(calls: int, warmup: int) -> list:
    """A virtual key's overhead with the key list's warm-up after a debit off and on."""
    from harness import gateway_keys
    rows, before = [], gateway_keys.WARM
    try:
        for warm in (False, True):
            gateway_keys.WARM = warm
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
                with bench.rig(Path(tmp) / "home", "openai", STUB_DELAY, key=True) as made:
                    for stream in (False, True):
                        got = summarize(bench.measure(made, "/v1/messages", stream, calls, warmup))
                        rows.append({"warm_up": warm, "stream": stream,
                                     "first_ms": got["first"]["overhead_median_ms"],
                                     "total_ms": got["total"]["overhead_median_ms"]})
    finally:
        gateway_keys.WARM = before
    return rows


def disk(count: int = 200) -> dict:
    """What a bare append-and-commit costs in a temporary folder on this disk."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        took = bench.commit_cost(tmp, count)
    return {"commits": count, "median_ms": _ms(statistics.median(took)),
            "p95_ms": _ms(_p95(took)), "max_ms": _ms(max(took)),
            "what": "append 300 bytes to a file, then os.fsync; no gateway code"}


def table(rows: list) -> str:
    lines = ["interface      upstream   caller  mode    first ms  total ms  p95 ms  max ms  "
             "2 commits ms"]
    for row in rows:
        lines.append(
            f"{row['interface']:<14} {row['upstream']:<10} {row['caller']:<7} "
            f"{'stream' if row['stream'] else 'plain':<7} "
            f"{row['first']['overhead_median_ms']:>8.2f}  "
            f"{row['total']['overhead_median_ms']:>8.2f}  "
            f"{row['total']['overhead_p95_ms']:>6.2f}  {row['total']['overhead_max_ms']:>6.2f}  "
            f"{row['commits_median_ms']:>12.2f}")
    return "\n".join(lines)


def main(argv: "list | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--calls", type=int, default=30, help="warm calls per case (default 30)")
    ap.add_argument("--warmup", type=int, default=3, help="calls thrown away first")
    ap.add_argument("--out", default=str(RECORD), help="where the JSON record goes")
    ap.add_argument("--cold", metavar="PATH", help=argparse.SUPPRESS)
    ap.add_argument("--stream", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--plain", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.cold:
        print(cold(args.cold, args.stream))
        return 0
    record = {"schema": "flywheel.gateway-overhead/v1", "date": time.strftime("%Y-%m-%d"),
              "machine": machine(),
              "method": {"stub_delay_ms": _ms(STUB_DELAY), "stream_text_events": bench.DELTAS,
                         "warm_calls": args.calls, "warmup_calls": args.warmup,
                         "client": "http.client, one request at a time, a fresh connection "
                                   "per call", "clock": "time.perf_counter"},
              "disk": disk(), "cases": run_cases(args.calls, args.warmup),
              "first_call": run_cold(),
              "breakdown": [breakdown("/v1/messages", stream, args.calls)
                            for stream in (False, True)],
              "key_warm_up": warm_compare(args.calls, args.warmup)}
    report(record)
    Path(args.out).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8",
                              newline="\n")
    print(f"wrote {Path(args.out).name}")
    return 0


def report(record: dict) -> None:
    print(table(record["cases"]))
    print(f"a bare commit on this disk: median {record['disk']['median_ms']} ms, p95 "
          f"{record['disk']['p95_ms']} ms over {record['disk']['commits']}")
    for row in record["first_call"]:
        print(f"first call {row['interface']} {'stream' if row['stream'] else 'plain'}: "
              f"{row['first_call_overhead_ms']:.1f} ms over the stub")
    for part in record["breakdown"]:
        print(f"breakdown {part['interface']} {'stream' if part['stream'] else 'plain'} "
              f"(key, {part['overhead_total_median_ms']} ms): {part['parts_median_ms']}")
    for row in record["key_warm_up"]:
        print(f"key warm-up {'on ' if row['warm_up'] else 'off'} "
              f"{'stream' if row['stream'] else 'plain '}: first {row['first_ms']} ms, "
              f"total {row['total_ms']} ms")


if __name__ == "__main__":
    raise SystemExit(main())
