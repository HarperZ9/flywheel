"""bench_gateway_overhead.py -- what the gateway adds to one model call.

    python scripts/bench_gateway_overhead.py            # table + JSON record
    python scripts/bench_gateway_overhead.py --calls 100 --out my-run.json

For each case the same request is sent straight to a loopback stub provider
and through a real gateway HTTP server pointed at that stub, in turns, one
request at a time. The stub waits a fixed time before its first byte and notes
how long it held each request; that wait is taken out of each call, so the
difference of the two medians is the gateway's own share: its HTTP server, the
credential check, parsing, the second connection, rendering, the ledger entry
and, for a virtual key, the key lookup and the debit.

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
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts import gateway_bench_rig as bench  # noqa: E402

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
    "key debit": ("gateway_key_gate", "Bill", "settle"),
    "ledger entry, with the debit inside it": ("gateway_turn", None, "record"),
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
    out = {"calls": len(samples["gateway"])}
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


def _cpu() -> str:
    try:
        if sys.platform == "win32":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        if sys.platform == "darwin":
            return subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], text=True,
                                  capture_output=True, timeout=10).stdout.strip()
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"cpu model not read ({type(exc).__name__})", file=sys.stderr)
    return platform.processor() or "unknown"


def _ram_gb() -> "float | None":
    try:
        if sys.platform == "win32":
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                    (name, ctypes.c_ulonglong) for name in
                    ("total", "free", "page", "page_free", "virt", "virt_free", "ext")]
            status = Status(length=ctypes.sizeof(Status))
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return round(status.total / 2 ** 30, 1)
        import os
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30, 1)
    except (OSError, ValueError, AttributeError) as exc:
        print(f"memory size not read ({type(exc).__name__})", file=sys.stderr)
        return None


def machine() -> dict:
    """The machine, with nothing that names its owner: no host, user or path."""
    return {"cpu": _cpu(), "logical_cpus": __import__("os").cpu_count(), "ram_gb": _ram_gb(),
            "os": f"{platform.system()} {platform.release()} (build {platform.version()})",
            "python": platform.python_version()}


def table(rows: list) -> str:
    lines = ["interface      upstream   caller  mode    first ms  total ms  p95 ms  max ms"]
    for row in rows:
        lines.append(
            f"{row['interface']:<14} {row['upstream']:<10} {row['caller']:<7} "
            f"{'stream' if row['stream'] else 'plain':<7} "
            f"{row['first']['overhead_median_ms']:>8.2f}  "
            f"{row['total']['overhead_median_ms']:>8.2f}  "
            f"{row['total']['overhead_p95_ms']:>6.2f}  {row['total']['overhead_max_ms']:>6.2f}")
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
              "cases": run_cases(args.calls, args.warmup), "first_call": run_cold(),
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
