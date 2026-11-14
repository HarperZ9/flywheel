"""Helpers for the gateway Messages tests: fixtures, a stub upstream, a real gateway.

Fixtures live in fixtures/gateway_messages. `requests/` holds Messages request
bodies, `expected/` holds the Message objects, stream events and upstream
request bodies they must produce, and `upstream/` holds upstream replies that
fixtures/provider_streams does not already have (cache counts, no counts, a
stream cut mid-event, error bodies). All were written by hand in the
documented formats; no provider was called to make them or to replay them.

Wire formats, read 2026-11-13:
  https://platform.claude.com/docs/en/api/messages/create
  https://platform.claude.com/docs/en/build-with-claude/streaming
  https://platform.claude.com/docs/en/api/errors
  https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls
      (the Message usage object, with the cache fields)
"""
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from harness import gateway, gateway_turn
from harness.endpoints import AnthropicBackend, GeminiBackend, OpenAICompatBackend
from harness.endpoints_sse import events as sse_events
from harness.local_session import SessionLedger
from tests.hosted_stream_fixtures import backend as replay_backend

ROOT = Path(__file__).parent / "fixtures" / "gateway_messages"
TOKEN = "test-gateway-token-not-a-real-credential"
MODELS = {"openai": "gpt-5.3-codex-spark", "anthropic": "claude-sonnet-5",
          "gemini": "gemini-2.5-flash"}


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def raw(name: str) -> bytes:
    return (ROOT / name).read_bytes()


def events(body: bytes) -> list:
    """[[event name, data]] for an SSE body."""
    return [[name, data] for name, data in sse_events(body.splitlines(keepends=True))]


def joined(chunks) -> bytes:
    return b"".join(chunks)


def replayed(monkeypatch, provider: str, *, plain=(), streams=()):
    """Route every gateway model to a backend that replays recordings. No network."""
    made = replay_backend(provider, plain=plain, streams=streams)
    monkeypatch.setattr(gateway_turn, "make_backend", lambda name, model: (provider, made))
    monkeypatch.setenv(gateway_turn.UPSTREAM_ENV, provider)
    return made


def kinds(ledger) -> list:
    return [entry.kind for entry in ledger.entries]


class Upstream:
    """A loopback provider. Answers each POST with the next (status, type, body)
    or (status, type, body, extra headers)."""

    def __init__(self, answers):
        stub = self
        self.answers, self.requests = list(answers), []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                stub.requests.append({"path": self.path, "body": json.loads(body),
                                      "headers": {k.lower(): v for k, v in self.headers.items()}})
                status, content_type, payload, *extra = stub.answers.pop(0)
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                for name, value in (extra[0] if extra else {}).items():
                    self.send_header(name, value)
                if content_type == "application/json":
                    self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def json_answer(obj, status: int = 200) -> tuple:
    return status, "application/json", json.dumps(obj).encode()


def stream_answer(body: bytes) -> tuple:
    return 200, "text/event-stream", body


def point_at(monkeypatch, provider: str, url: str) -> None:
    """Send every gateway model to `provider` at a loopback url, over real HTTP."""
    made = {"openai": lambda: OpenAICompatBackend(name="openai", base_url=f"{url}/v1",
                                                  model=MODELS["openai"], api_key="test-key"),
            "anthropic": lambda: AnthropicBackend(name="anthropic", base_url=url,
                                                  model=MODELS["anthropic"], api_key="test-key"),
            "gemini": lambda: GeminiBackend(name="gemini", base_url=f"{url}/v1beta",
                                            model=MODELS["gemini"], api_key="test-key")}
    monkeypatch.setattr(gateway_turn, "make_backend",
                        lambda name, model: (provider, made[provider]()))
    monkeypatch.setenv(gateway_turn.UPSTREAM_ENV, provider)


@contextmanager
def gateway_server(monkeypatch, tmp_path, token: str = TOKEN):
    """A real gateway on a loopback port, with its own empty router ledger."""
    ledger = SessionLedger()
    monkeypatch.setattr(gateway, "_ROUTER_LEDGER", ledger)

    class Handler(gateway._Handler):
        pass
    Handler.flywheel_home = tmp_path / "home"
    Handler.run_root = str(tmp_path / "run")
    Handler.auth_token = token
    Handler.allowed_hosts = gateway.DEFAULT_HOSTS
    Handler.owner_ref = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", ledger
    finally:
        server.shutdown()
        server.server_close()
