"""One gateway route call in a process that dies while the provider answers.

Run by tests/test_gateway_route_accounting.py as a child process:

    python -m tests.gateway_route_kill_child ROUTE HOME TMP

It marks the process as a gateway the way `gateway.main` does, points `ollama`
at a stub in this process, and calls the route's handler function. The stub
writes its reply and then ends the process with `os._exit`: no `finally`, no
`atexit`, no flush. Exit code 86 means it died there. No provider is called.
"""
import json
import os
import sys
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DIED = 86


class Stub(BaseHTTPRequestHandler):
    count = 0

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        Stub.count += 1
        body = json.dumps({"model": "stub-model", "choices": [{"message": {
            "role": "assistant", "content": "ok"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        print("requests", Stub.count, flush=True)
        os._exit(DIED)

    def log_message(self, *args):
        pass


def main(argv) -> int:
    name, home, tmp = argv
    os.environ["FLYWHEEL_HOME"] = home
    from harness import gateway, gateway_ledger_gate, providers
    server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    providers.REGISTRY["ollama"] = replace(
        providers.REGISTRY["ollama"], base_url=f"http://127.0.0.1:{server.server_address[1]}/v1")
    gateway_ledger_gate.startup(gateway._router_ledger, out=lambda *_: None)
    if name == "audit":
        from harness.audit_run_route import handle_audit_run
        handle_audit_run({"work_receipt": {"x": 1}, "artifact": "done", "endpoint": "ollama",
                          "model": "stub-model"}, Path(tmp) / "run")
    else:
        from harness.frontier import capability_probe
        capability_probe("ollama:stub-model")
    return 1                            # the call ended without the stub ending the process


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
