"""gateway_bench_stub.py -- the loopback provider the gateway overhead rig measures against.

  Stub          a loopback provider. It reads the request, waits `delay` seconds,
                then answers in its dialect: one JSON object, or `DELTAS` text
                events written one by one with no pause between them. It notes
                how long it held each request, on the clock the client uses.
  MemoryStore   the credential store as a dictionary.

Used by scripts/gateway_bench_rig.py. No provider is called.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DELTAS = 20
PIECE = "word "
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
