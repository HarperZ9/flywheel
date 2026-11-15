"""gateway_bench_rig.py -- a real gateway, a stub upstream and one HTTP client.

The overhead benchmark (scripts/bench_gateway_overhead.py) and its timing gate
(tests/test_gateway_overhead_timing.py) both measure with this module, so the
published figure and the CI budget come from the same code.

  Stub      a loopback provider. It reads the request, waits `delay` seconds,
            then answers in its dialect: one JSON object, or `DELTAS` text
            events written one by one with no pause between them. It notes
            how long it held each request, on the clock the client uses.
  rig()     starts a stub and a real gateway HTTP server on loopback ports and
            points every gateway model at the stub. It can add a virtual key
            held in an in-memory store, and a sleep on the gateway's side.
  call()    one POST over a fresh connection with `http.client`; returns the
            seconds to the first byte (or the first text delta of a stream)
            and to the end of the body.
  measure() the same request sent straight to the stub and through the
            gateway, in turns, after warm-up calls that are thrown away. Each
            sample has the stub's own wait for that call taken out, so a late
            timer in the stub's sleep is not counted as gateway time. For each
            gateway call it also notes the ledger's disk commits: how many,
            and the seconds the operating system spent inside `os.fsync`
            before the first byte and in all. Those seconds are taken by the
            rig's own clock around the system call (`Rig.syscalls`), not from
            what the gateway reports, so gateway work placed next to the
            commit is not counted as the disk's. What the gateway reports is
            kept beside it ("reported") so the two can be compared.
  overhead() median gateway sample minus median stub sample: what a caller
            waits, both commits included. With `own=True` each gateway
            sample first has its disk commit seconds taken out: what is left
            is the gateway's own work.
  commit_cost() what one bare append-and-commit costs in a folder, with no
            gateway code involved: the disk's share, measured on its own.

No provider is called. The system credential store is never opened: the key
store here is a dictionary.
"""
from __future__ import annotations

import http.client
import json
import os
import statistics
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit

from scripts.gateway_bench_stub import (  # noqa: F401  (part of this module's surface)
    _MODELS, DELTAS, PIECE, REPLIES, MemoryStore, Stub)

TOKEN = "bench-gateway-token-not-a-real-credential"
PATHS = ("/v1/messages", "/v1/responses")
BODIES = {
    "/v1/messages": {"model": "claude-sonnet-5", "max_tokens": 256,
                     "messages": [{"role": "user", "content": "What changed?"}]},
    "/v1/responses": {"model": "gpt-5.3-codex", "input": "What changed?"},
}
# The text that marks the first text delta a client can read, per wire format.
GATEWAY_MARK = {"/v1/messages": b"content_block_delta",
                "/v1/responses": b"response.output_text.delta"}
STUB_MARK = {"openai": b'"delta":{"content"', "anthropic": b"content_block_delta"}


@dataclass
class Rig:
    gateway: str                        # the gateway's loopback URL
    stub: Stub
    credential: str                     # the gateway token, or the virtual key
    ledger: object
    keys: object = None                 # the key list, when the caller is a key
    syscalls: list = None               # seconds of each `os.fsync`, taken around the call


def _backend(dialect: str, url: str):
    from harness.endpoints import AnthropicBackend, OpenAICompatBackend
    if dialect == "anthropic":
        return AnthropicBackend(name="anthropic", base_url=url, model=_MODELS[dialect],
                                api_key="test-key")
    return OpenAICompatBackend(name="openai", base_url=f"{url}/v1", model=_MODELS[dialect],
                               api_key="test-key")


def _serve_gateway(home):
    from harness import gateway

    class Handler(gateway._Handler):
        pass
    Handler.flywheel_home = home
    Handler.run_root = str(home.parent / "run")
    Handler.auth_token = TOKEN
    Handler.allowed_hosts = gateway.DEFAULT_HOSTS
    Handler.owner_ref = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    return server


@contextmanager
def rig(home, dialect: str = "openai", delay: float = 0.05, key: bool = False,
        gateway_delay: float = 0.0, disk_delay: float = 0.0):
    """A stub and a real gateway pointed at it. `home` is an empty directory.

    `gateway_delay` sleeps that long inside the gateway on every call, before
    the upstream is contacted. `disk_delay` makes every `os.fsync` take that
    much longer, inside the timed system call: a slow disk. The timing gate
    uses both as controls."""
    from harness import gateway, gateway_key_gate, gateway_keys, gateway_turn
    from harness.gateway_ledger import GatewayLedger
    store, stub = MemoryStore(), Stub(dialect, delay).start()
    ledger = GatewayLedger(home)            # on disk, committed per entry, as a gateway runs

    def make(name, model):
        time.sleep(gateway_delay)
        return dialect, _backend(dialect, stub.url)
    saved = (gateway._ROUTER_LEDGER, gateway_turn.make_backend, gateway_key_gate.open_keys,
             os.environ.get(gateway_turn.UPSTREAM_ENV))
    gateway._ROUTER_LEDGER, gateway_turn.make_backend = ledger, make
    gateway_key_gate.open_keys = lambda where: gateway_keys.Keys(where, store=store)
    os.environ[gateway_turn.UPSTREAM_ENV] = dialect
    server, syscalls, real_fsync = _serve_gateway(home), [], os.fsync

    def fsync(fd):                      # the rig's clock, at the system call itself
        began = time.perf_counter()
        try:
            if disk_delay:
                time.sleep(disk_delay)
            return real_fsync(fd)
        finally:
            syscalls.append(time.perf_counter() - began)
    os.fsync = fsync
    try:
        made = Rig(f"http://127.0.0.1:{server.server_address[1]}", stub, TOKEN, ledger,
                   syscalls=syscalls)
        if key:
            made.keys = gateway_keys.Keys(home, store=store)
            made.credential = made.keys.create(
                "bench", token_limit=10 ** 12, spend_limit=1e6, price_in=3, price_out=15)[0]
        yield made
    finally:
        os.fsync = real_fsync
        server.shutdown()
        server.server_close()
        stub.stop()
        ledger.close()
        gateway._ROUTER_LEDGER, gateway_turn.make_backend, gateway_key_gate.open_keys = saved[:3]
        if saved[3] is None:
            os.environ.pop(gateway_turn.UPSTREAM_ENV, None)
        else:
            os.environ[gateway_turn.UPSTREAM_ENV] = saved[3]


def call(url: str, path: str, body: bytes, credential: str, mark: "bytes | None") -> tuple:
    """(seconds to first byte or first text delta, seconds to the end) for one POST.

    A fresh connection per call: the gateway closes the connection after a
    stream, so a client reconnects for every streamed request anyway. The
    connect is blocking and the timeout is set after it. On Windows a Python
    socket that has a timeout connects without blocking and then waits, and
    that wait came back about 15 ms late in a third of loopback connects
    (measured 2026-11-14). It would land on this client, not on the gateway."""
    parts = urlsplit(url)
    started = time.perf_counter()
    conn = http.client.HTTPConnection(parts.hostname, parts.port)
    try:
        conn.connect()
        conn.sock.settimeout(30)
        conn.request("POST", path, body, {"Content-Type": "application/json",
                                          "x-api-key": credential})
        response = conn.getresponse()
        first = time.perf_counter() if mark is None else None
        if mark is None:
            rest = response.read()
        else:
            rest = b""
            for line in response:
                if first is None and mark in line:
                    first = time.perf_counter()
                rest = line or rest
        done = time.perf_counter()
    finally:
        conn.close()
    if response.status != 200 or first is None or not rest:
        raise RuntimeError(f"{path} answered {response.status} without the expected reply")
    return first - started, done - started


def measure(made: Rig, path: str, stream: bool, calls: int, warmup: int = 3) -> dict:
    """Seconds for `calls` warm requests, straight to the stub and through the gateway.

    Returns {"direct": [(first, total)], "gateway": [(first, total)],
    "commit": [(before first byte, total, count)], "reported": [(total, count)]}.
    The first two have the stub's wait for that call subtracted, and are taken
    in turns so a busy moment on the machine lands on both. "commit" is one row
    per gateway call: the seconds its `os.fsync` calls took on the rig's clock
    and how many there were. A plain reply is sent after both of its entries
    are committed; a stream's first byte comes after the started entry's
    commit, the first of the call. "reported" is what the gateway's ledger
    says the same commits took (gateway_ledger_health)."""
    body = json.dumps({**BODIES[path], "stream": stream}).encode()
    marks = ((STUB_MARK[made.stub.dialect], GATEWAY_MARK[path]) if stream else (None, None))
    out = {"direct": [], "gateway": [], "commit": [], "reported": []}
    for index in range(warmup + calls):
        for name, url, credential, mark in (("direct", made.stub.url, "none", marks[0]),
                                            ("gateway", made.gateway, made.credential, marks[1])):
            before, seen = list(_commits(made.ledger)), len(made.syscalls)
            first, total = call(url, path, body, credential, mark)
            wait, after = made.stub.waits[-1], _commits(made.ledger)
            if index >= warmup:
                out[name].append((first - wait, total - wait))
                if name == "gateway":
                    took = made.syscalls[seen:]
                    out["commit"].append((sum(took[:1]) if stream else sum(took), sum(took),
                                          len(took)))
                    out["reported"].append((after[1] - before[1], after[0] - before[0]))
    return out


def _commits(ledger) -> list:
    return getattr(ledger, "commits", None) or [0, 0.0, 0.0]


def overhead(samples: dict, which: int = 0, own: bool = False) -> float:
    """Median gateway seconds minus median stub seconds. which: 0 first byte, 1 total.

    `own` takes each call's disk commit seconds out of its gateway sample first."""
    rows = [row[which] for row in samples["gateway"]]
    if own:
        rows = [row - commit[which] for row, commit in zip(rows, samples["commit"])]
    return statistics.median(rows) - statistics.median(row[which] for row in samples["direct"])


_FSYNC = os.fsync                       # the system call, whatever a rig put in its place


def commit_cost(folder, count: int = 40) -> list:
    """Seconds for each of `count` bare commits: append 300 bytes to a file in `folder`,
    then `os.fsync`. No gateway code runs, so this is what the disk alone costs here."""
    took = []
    with open(os.path.join(str(folder), "commit-probe.bin"), "ab", buffering=0) as probe:
        for _ in range(count):
            probe.write(b"x" * 299 + b"\n")
            began = time.perf_counter()
            _FSYNC(probe.fileno())
            took.append(time.perf_counter() - began)
    return took
