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
            timer in the stub's sleep is not counted as gateway time.
  overhead() median gateway sample minus median stub sample.

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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

TOKEN = "bench-gateway-token-not-a-real-credential"
DELTAS = 20
PIECE = "word "
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
_MODELS = {"openai": "gpt-5.3-codex-spark", "anthropic": "claude-sonnet-5"}


def _sse(data: dict, event: str = "") -> bytes:
    head = f"event: {event}\n" if event else ""
    return f"{head}data: {json.dumps(data, separators=(',', ':'))}\n\n".encode()


def _openai(stream: bool) -> list:
    base = {"id": "chatcmpl-bench", "created": 1794268190, "model": _MODELS["openai"]}
    usage = {"prompt_tokens": 12, "completion_tokens": DELTAS,
             "total_tokens": 12 + DELTAS}
    if not stream:
        message = {"role": "assistant", "content": PIECE * DELTAS, "refusal": None}
        return [json.dumps({**base, "object": "chat.completion", "usage": usage, "choices": [
            {"index": 0, "message": message, "finish_reason": "stop"}]}).encode()]

    def chunk(delta, finish=None):
        return _sse({**base, "object": "chat.completion.chunk", "usage": None, "choices": [
            {"index": 0, "delta": delta, "finish_reason": finish}]})
    out = [chunk({"role": "assistant", "content": ""})]
    out += [chunk({"content": PIECE}) for _ in range(DELTAS)]
    out += [chunk({}, "stop"),
            _sse({**base, "object": "chat.completion.chunk", "choices": [], "usage": usage}),
            b"data: [DONE]\n\n"]
    return out


def _anthropic(stream: bool) -> list:
    base = {"id": "msg_bench", "type": "message", "role": "assistant",
            "model": _MODELS["anthropic"]}
    if not stream:
        return [json.dumps({**base, "content": [{"type": "text", "text": PIECE * DELTAS}],
                            "stop_reason": "end_turn", "stop_sequence": None,
                            "usage": {"input_tokens": 12, "output_tokens": DELTAS}}).encode()]

    def event(name, **fields):
        return _sse({"type": name, **fields}, name)
    out = [event("message_start", message={
        **base, "content": [], "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": 1}}),
        event("content_block_start", index=0, content_block={"type": "text", "text": ""})]
    out += [event("content_block_delta", index=0, delta={"type": "text_delta", "text": PIECE})
            for _ in range(DELTAS)]
    out += [event("content_block_stop", index=0),
            event("message_delta", delta={"stop_reason": "end_turn", "stop_sequence": None},
                  usage={"output_tokens": DELTAS}),
            event("message_stop")]
    return out


REPLIES = {"openai": _openai, "anthropic": _anthropic}


class Stub:
    """A loopback provider that holds its first byte for `delay` seconds."""

    def __init__(self, dialect: str, delay: float):
        stub = self
        self.dialect, self.delay, self.waits = dialect, delay, []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                arrived = time.perf_counter()
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                stream = bool(body.get("stream"))
                chunks = REPLIES[stub.dialect](stream)
                time.sleep(stub.delay)
                self.send_response(200)
                self.send_header("Content-Type",
                                 "text/event-stream" if stream else "application/json")
                if not stream:
                    self.send_header("Content-Length", str(len(chunks[0])))
                self.end_headers()
                stub.waits.append(time.perf_counter() - arrived)
                for chunk in chunks:
                    self.wfile.write(chunk)
                    self.wfile.flush()

            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def start(self) -> "Stub":
        threading.Thread(target=self.server.serve_forever, args=(0.05,), daemon=True).start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class MemoryStore:
    """The credential store as a dictionary. Nothing here reaches the system store."""

    def __init__(self):
        self.saved = {}

    def available(self) -> bool:
        return True

    def get(self, name):
        return self.saved.get(name)

    def set(self, name, secret):
        self.saved[name] = secret
        return {"stored": name}

    def delete(self, name):
        self.saved.pop(name, None)
        return {"deleted": name}


@dataclass
class Rig:
    gateway: str                        # the gateway's loopback URL
    stub: Stub
    credential: str                     # the gateway token, or the virtual key
    ledger: object
    keys: object = None                 # the key list, when the caller is a key


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
        gateway_delay: float = 0.0):
    """A stub and a real gateway pointed at it. `home` is an empty directory.

    `gateway_delay` sleeps that long inside the gateway on every call, before
    the upstream is contacted. The timing gate uses it as its control."""
    from harness import gateway, gateway_key_gate, gateway_keys, gateway_turn
    from harness.local_session import SessionLedger
    store, ledger, stub = MemoryStore(), SessionLedger(), Stub(dialect, delay).start()

    def make(name, model):
        time.sleep(gateway_delay)
        return dialect, _backend(dialect, stub.url)
    saved = (gateway._ROUTER_LEDGER, gateway_turn.make_backend, gateway_key_gate.open_keys,
             os.environ.get(gateway_turn.UPSTREAM_ENV))
    gateway._ROUTER_LEDGER, gateway_turn.make_backend = ledger, make
    gateway_key_gate.open_keys = lambda where: gateway_keys.Keys(where, store=store)
    os.environ[gateway_turn.UPSTREAM_ENV] = dialect
    server = _serve_gateway(home)
    try:
        made = Rig(f"http://127.0.0.1:{server.server_address[1]}", stub, TOKEN, ledger)
        if key:
            made.keys = gateway_keys.Keys(home, store=store)
            made.credential = made.keys.create(
                "bench", token_limit=10 ** 12, spend_limit=1e6, price_in=3, price_out=15)[0]
        yield made
    finally:
        server.shutdown()
        server.server_close()
        stub.stop()
        gateway._ROUTER_LEDGER, gateway_turn.make_backend, gateway_key_gate.open_keys = saved[:3]
        if saved[3] is None:
            os.environ.pop(gateway_turn.UPSTREAM_ENV, None)
        else:
            os.environ[gateway_turn.UPSTREAM_ENV] = saved[3]


def call(url: str, path: str, body: bytes, credential: str, mark: "bytes | None") -> tuple:
    """(seconds to first byte or first text delta, seconds to the end) for one POST.

    A fresh connection per call: the gateway closes the connection after a
    stream, so a client reconnects for every streamed request anyway."""
    parts = urlsplit(url)
    started = time.perf_counter()
    conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=30)
    try:
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

    Returns {"direct": [(first, total)], "gateway": [(first, total)]}, each
    with the stub's wait for that call subtracted. The two are taken in turns
    so a busy moment on the machine lands on both."""
    body = json.dumps({**BODIES[path], "stream": stream}).encode()
    marks = ((STUB_MARK[made.stub.dialect], GATEWAY_MARK[path]) if stream else (None, None))
    out = {"direct": [], "gateway": []}
    for index in range(warmup + calls):
        for name, url, credential, mark in (("direct", made.stub.url, "none", marks[0]),
                                            ("gateway", made.gateway, made.credential, marks[1])):
            first, total = call(url, path, body, credential, mark)
            wait = made.stub.waits[-1]
            if index >= warmup:
                out[name].append((first - wait, total - wait))
    return out


def overhead(samples: dict, which: int = 0) -> float:
    """Median gateway seconds minus median stub seconds. which: 0 first byte, 1 total."""
    return (statistics.median(row[which] for row in samples["gateway"])
            - statistics.median(row[which] for row in samples["direct"]))
