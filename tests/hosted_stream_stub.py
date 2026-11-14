"""A loopback stand-in for a hosted provider that delays its first byte.

The stub answers every POST with a recorded stream from
fixtures/provider_streams, after waiting `delay` seconds. It notes when each
request arrived and when its first byte went out, on the same clock the
client uses, so a test can subtract the provider's share of the wait from the
time a person waited for the first text.

    overhead = (first text shown - turn started) - (first byte sent - request arrived)

The overhead is Flywheel's own time: everything a turn does before the request
leaves, plus reading the first events and handing the text to the display.
"""
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from harness.code_session.backends import build_agent
from harness.code_session.session import new_session
from harness.code_session.streaming import streamed_send
from harness.endpoints import AnthropicBackend, GeminiBackend, OpenAICompatBackend
from harness.endpoints_sse import open_stream
from tests.hosted_stream_fixtures import stream_bytes

MAKE = {
    "openai": lambda url: OpenAICompatBackend(name="openai", base_url=f"{url}/v1",
                                              model="gpt-5.3-codex-spark", api_key="test-key"),
    "anthropic": lambda url: AnthropicBackend(name="anthropic", base_url=url,
                                              model="claude-sonnet-5", api_key="test-key"),
    "gemini": lambda url: GeminiBackend(name="gemini", base_url=f"{url}/v1beta",
                                        model="gemini-2.5-flash", api_key="test-key"),
}


class Stub:
    """Serve `body` to every POST, `delay` seconds after the request arrives."""

    def __init__(self, body: bytes, delay: float):
        stub = self
        self.body, self.delay, self.waits = body, delay, []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                arrived = time.perf_counter()
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                time.sleep(stub.delay)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                stub.waits.append(time.perf_counter() - arrived)
                self.wfile.write(stub.body)

            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5.0)


def overheads(provider: str, root: str, *, delay: float, turns: int,
              client_delay: float = 0.0) -> list:
    """Flywheel's own seconds before the first text, for `turns` streamed turns.

    One turn is run first and left out, so module imports are not counted.
    `client_delay` adds a sleep on Flywheel's side of the wire; the timing
    test uses it to show that the budget fails when the client gets slower.
    """
    def slowed(method, url, headers, body, timeout):
        time.sleep(client_delay)
        return open_stream(method, url, headers, body, timeout)

    out = []
    with Stub(stream_bytes(provider, "turn2"), delay) as stub:
        for index in range(turns + 1):
            made = MAKE[provider](stub.url)
            if client_delay:
                made.stream_transport = slowed
            session = new_session(build_agent([made]), root, mode="auto",
                                  runner=lambda cmd, root: (True, "[exit 0]"))
            first = []

            def shown(piece):
                if not first:
                    first.append(time.perf_counter())
            started = time.perf_counter()
            with streamed_send(session.agent, shown):
                result = session.turn("what changed?")
            assert result.final == "Wrote n.txt.\nNothing else changed." and first
            if index:
                out.append((first[0] - started) - stub.waits[-1])
    return out
