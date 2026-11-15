"""The shipped gateway entry point in a fresh process, then model requests outside an account.

Run by tests/test_gateway_reach_default.py as a child process, and usable by
hand against an installed package:

    python tests/gateway_reach_default_child.py HOME ROOT

It calls `harness.gateway.main([...])` as `flywheel up` does: the real parser,
the real bind, the real `_serve_all`. No test fixture runs in this process and
nothing here turns the reach rule on. When the port answers, it makes one model
request through each transport from a thread that holds no ledger account, at
a loopback stub that counts what arrives, and prints one JSON line:

    before     whether the rule was on before `main` ran (expected false)
    enforced   whether it is on while `main` serves (expected true)
    outcomes   per transport, the exception type raised, or "sent"
    arrivals   requests the stub received (expected 0)
    commands   command lines the command-line backend's runner was handed (0)

Two pieces of machine state are pointed into HOME so that a run on a
workstation leaves the owner's files alone: FLYWHEEL_HOME, and the per-user
home pointer that `main` rewrites when it binds. Neither is read by the reach
rule. No provider is called and no key is read.
"""
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPLY = json.dumps({"id": "x", "model": "stub-model", "choices": [
    {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()


def counting_stub():
    """(server, arrivals): a loopback server that answers every POST and lists each path."""
    arrivals = []

    class Stub(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            arrivals.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(REPLY)))
            self.end_headers()
            self.wfile.write(REPLY)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, arrivals


def url_of(server) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}"


def transports(url: str, commands: list) -> dict:
    """name -> a function that makes one model request through that transport."""
    from harness import endpoints_http, proposer
    from harness.endpoints import CliBackend, OpenAICompatBackend

    def post():
        return urllib.request.Request(f"{url}/v1/chat/completions", data=b"{}", method="POST",
                                      headers={"Content-Type": "application/json"})

    def runner(cmd):
        commands.append(list(cmd))
        return 0, b"ok", b""

    def chat(backend):
        return backend.chat([{"role": "user", "content": "hi"}], system="", max_tokens=8,
                            temperature=0, seed=0)

    return {
        "endpoints_http.send": lambda: endpoints_http.send(post(), 10).read(),
        "proposer._send": lambda: proposer._send(post(), 10).read(),
        "OpenAICompatBackend.chat": lambda: chat(OpenAICompatBackend(
            name="openai", base_url=f"{url}/v1", model="stub-model", api_key="test-key")),
        "EnterpriseProposer.generate": lambda: proposer.EnterpriseProposer(
            base_url=f"{url}/v1", model="stub-model", api_key="test-key").generate(
                "hi", seed=0, temperature=0, max_new_tokens=8),
        "CliBackend.chat": lambda: chat(CliBackend(
            name="claude", argv=["claude", "-p", "{prompt}"], runner=runner)),
    }


def attempt(send) -> str:
    """Run `send` in a new thread (no account, no exemption) and name how it ended."""
    ended = []

    def run():
        try:
            send()
            ended.append("sent")
        except BaseException as exc:    # noqa: BLE001  (the type is the result)
            ended.append(type(exc).__name__)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(60)
    return ended[0] if ended else "no answer in 60 s"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _answers(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/.well-known/flywheel.json",
                               timeout=2).read()
    except urllib.error.HTTPError:
        return True                     # an HTTP answer of any status: the gateway serves
    except OSError:
        return False
    return True


def main(argv) -> int:
    home, root = argv
    os.environ["FLYWHEEL_HOME"] = home
    Path(home).mkdir(parents=True, exist_ok=True)
    from harness import gateway, gateway_endpoint_file, gateway_reach
    from harness.capture_hooks import home as hook_home
    pointer = Path(home) / "pointer" / "home.json"
    hook_home.pointer_path = gateway_endpoint_file.pointer_path = lambda: pointer
    server, arrivals = counting_stub()
    commands: list = []
    before = gateway_reach.enforced()
    port = _free_port()
    threading.Thread(target=lambda: gateway.main(
        ["--port", str(port), "--root", root, "--run-root", str(Path(root) / "run")]),
        daemon=True).start()
    deadline = time.monotonic() + 90
    serving = False
    while not serving and time.monotonic() < deadline:
        serving = _answers(port)
        serving or time.sleep(0.2)
    enforced = gateway_reach.enforced()
    outcomes = {name: attempt(send)
                for name, send in transports(url_of(server), commands).items()} if serving else {}
    print(json.dumps({"before": before, "serving": serving, "enforced": enforced,
                      "outcomes": outcomes, "arrivals": arrivals,
                      "commands": len(commands)}), flush=True)
    os._exit(0)                         # the gateway thread serves until the process ends


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
