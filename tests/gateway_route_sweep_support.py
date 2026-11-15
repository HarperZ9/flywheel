"""A real gateway, two counting upstreams and a socket trap, for the route sweep.

Used by tests/test_gateway_route_reach.py.

  World      one gateway HTTP server on a loopback port with its own home, an
             on-disk ledger, and the reach rule on, as `gateway.main` turns it
             on (gateway_ledger_gate.startup). Every roster endpoint is
             pointed at `provider`, a stub that counts requests by method and
             path. The local model server address is pointed at `local`, a
             second stub. Nothing else is reachable: a connection to an
             address that is not this machine is refused and written down.
  exercise   sends one request and returns what it caused: the status, the
             provider requests (model requests and others apart), the local
             requests, the ledger entries added, the refusals of the reach
             rule, and the outside addresses tried.
  granted    runs the per-operation grant flow over HTTP (prepare, approve
             once) and returns the final body for a route behind it.

No provider is called. The keys are test strings.
"""
import json
import socket
import sys
import threading
import time
from dataclasses import replace
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOKEN = "sweep-gateway-token-not-a-real-credential"
OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32
MODEL_PATHS = ("/chat/completions", "/embeddings", "/v1/messages", "/responses", "/generate",
               ":generateContent")
CHAT = {"id": "chatcmpl-sweep", "object": "chat.completion", "model": "stub-model",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": "FINAL: done"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}}
EMBED = {"object": "list", "model": "text-embedding-3-small",
         "data": [{"object": "embedding", "index": 0, "embedding": [0.0, 1.0]}],
         "usage": {"prompt_tokens": 1, "total_tokens": 1}}
MODELS = {"object": "list", "data": [{"id": "stub-model", "object": "model"}]}
LOCAL = {"text": "ok", "model_ref": "serve:stub", "seed": 0, "prompt_hash": "0" * 16,
         "cache": "miss", "status": "ok"}


class Counting:
    """A loopback HTTP stub that records (method, path) and answers by path."""

    def __init__(self, answer):
        stub = self
        self.requests = []

        class Handler(BaseHTTPRequestHandler):
            def _any(self):
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                stub.requests.append((self.command, self.path.split("?", 1)[0]))
                body = json.dumps(answer(self.command, self.path)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            do_GET = do_POST = do_PUT = do_DELETE = _any

            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def _is_model(row) -> bool:
    """Is this (method, path) a request that asks a provider to run a model?"""
    return row[0] == "POST" and any(mark in row[1] for mark in MODEL_PATHS) and (
        "count_tokens" not in row[1])


def _provider_answer(method, path):
    if "/embeddings" in path:
        return EMBED
    if method == "GET":
        return MODELS
    return CHAT


class Trap:
    """Refuses, and writes down, every connection to an address that is not this machine."""

    LOCAL = ("127.0.0.1", "::1", "localhost", "0.0.0.0")

    def __init__(self):
        self.outside = []
        self._connect, self._resolve = socket.socket.connect, socket.getaddrinfo

    def start(self):
        trap = self

        def connect(sock, address):
            host = address[0] if isinstance(address, tuple) else str(address)
            if isinstance(address, tuple) and host not in trap.LOCAL:
                trap.outside.append(f"{host}:{address[1]}")
                raise ConnectionRefusedError("the route sweep reaches no outside address")
            return trap._connect(sock, address)

        def resolve(host, *args, **kwargs):
            if host not in trap.LOCAL and host is not None:
                trap.outside.append(f"{host}:{args[0] if args else ''}")
                raise socket.gaierror("the route sweep resolves no outside name")
            return trap._resolve(host, *args, **kwargs)
        socket.socket.connect, socket.getaddrinfo = connect, resolve
        return self

    def stop(self):
        socket.socket.connect, socket.getaddrinfo = self._connect, self._resolve


class World:
    def __init__(self, base: Path, patch):
        from harness import (endpoints, eval_run_route, gateway, gateway_ledger,
                             gateway_ledger_gate, gateway_reach, gateway_turn, providers)
        from harness.endpoints import OpenAICompatBackend
        self.home, self.run_root, self.root = base / "home", base / "run", base / "workspace"
        for folder in (self.home, self.run_root, self.root):
            folder.mkdir(parents=True)
        (self.home / "owner.ref").write_text(OWNER, encoding="ascii")
        self.provider, self.local = Counting(_provider_answer), Counting(lambda m, p: LOCAL)
        self.refused, self.trap, self._serial = [], Trap(), 0
        patch.setenv("FLYWHEEL_HOME", str(self.home))
        patch.setenv("SWEEP_FAKE_KEY", "sk-sweep-not-a-real-key")
        patch.setenv("OPENAI_BASE_URL", f"{self.provider.url}/v1")    # a worker child inherits it
        patch.setenv("OPENAI_API_KEY", "sk-sweep-not-a-real-key")
        patch.setenv(gateway_turn.UPSTREAM_ENV, "openai")
        patch.setattr(gateway, "_ROUTER_LEDGER", None)
        for name, spec in list(providers.REGISTRY.items()):
            patch.setitem(providers.REGISTRY, name, replace(
                spec, base_url=f"{self.provider.url}/v1",
                api_key_env="" if spec.local else "SWEEP_FAKE_KEY"))
        self.roster = {"endpoints": [
            {"name": "ollama", "credential": "local-none", "kind": "openai-compat"},
            {"name": "openai", "credential": "present", "kind": "openai-compat"}],
            "usable_names": ["ollama", "openai"]}
        patch.setattr(gateway, "_unified_roster", lambda: self.roster)
        patch.setattr(eval_run_route, "unified_roster", lambda: self.roster)
        backend = lambda: OpenAICompatBackend(     # noqa: E731
            name="openai", base_url=f"{self.provider.url}/v1", model="stub-model",
            api_key="sk-sweep-not-a-real-key")
        patch.setattr(gateway_turn, "make_backend", lambda name, model: ("openai", backend()))
        patch.setattr(endpoints, "build_endpoints", lambda **kwargs: [backend()])
        real_check = gateway_reach.check

        def check(what):
            try:
                return real_check(what)
            except gateway_reach.Unaccounted:
                self.refused.append(f"{gateway_reach.route()}: {what}")
                raise
        patch.setattr(gateway_reach, "check", check)

        class Handler(gateway._Handler):
            pass
        Handler.root, Handler.run_root = self.root, str(self.run_root)
        Handler.flywheel_home, Handler.auth_token = self.home, TOKEN
        Handler.allowed_hosts, Handler.owner_ref = gateway.DEFAULT_HOSTS, None
        Handler.serve_url = Handler.ollama_url = self.local.url
        Handler.operation_service = Handler.operation_process_factory = None
        Handler.session_token_store = Handler._session_token_state_root = None
        self.handler = Handler
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        assert gateway_ledger_gate.startup(gateway._router_ledger, out=lambda *_: None)
        self._ledger_module = gateway_ledger
        self.trap.start()

    def close(self):
        self.trap.stop()
        self.server.shutdown()
        self.server.server_close()
        self.provider.close()
        self.local.close()
        reach = sys.modules.get("harness.gateway_reach")
        if reach is not None:
            reach.release()
        self._ledger_module.close_all()

    # --- requests ------------------------------------------------------------------------

    def request(self, method: str, path: str, body=None, timeout: float = 120.0) -> tuple:
        raw = None if body is None else (body if isinstance(body, bytes)
                                         else json.dumps(body).encode())
        headers = {"Authorization": f"Bearer {TOKEN}"}
        if raw is not None:
            headers["Content-Type"] = "application/json"
        conn = HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        try:
            conn.request(method, path, body=raw, headers=headers)
            response = conn.getresponse()
            data = response.read()
        except (OSError, TimeoutError) as exc:
            return -1, {"error": type(exc).__name__}
        finally:
            conn.close()
        try:
            return response.status, json.loads(data)
        except ValueError:
            return response.status, {}

    def entries(self) -> list:
        return [entry for segment in self._ledger_module.check(self.home)
                for entry in segment["rows"]]

    def trace_starts(self) -> int:
        """The started `model_inference` records in the private traces of this home's agent
        runs: what a gateway agent run writes before each provider request."""
        from harness.gateway_agent_trace import AgentTrace
        state, count = self.home / "state", 0
        for folder in (state / "gateway-agent-traces").glob("v1/owners/*/op_*"):
            try:
                rows = AgentTrace(state, OWNER, JOURNEY, folder.name).read()
            except Exception:    # noqa: BLE001 - a trace still being written is read next time
                continue
            count += sum(1 for row in rows if row["kind"] == "ledger"
                         and row["payload"]["kind"] == "model_inference"
                         and row["payload"]["meta"].get("phase") == "started")
        return count

    def granted(self, action: str, operation: dict) -> "bytes | None":
        """The final body for a route behind the grant flow, or None when the flow refused."""
        from harness.journey_store import JourneyStore, MutationCommand
        state = self.home / "state"
        store = JourneyStore(state)
        try:
            head = store.load(OWNER, JOURNEY)["event_head_sha256"]
        except Exception:    # noqa: BLE001 - the journey is made on first use
            store.create(MutationCommand(OWNER, JOURNEY, None, "create-sweep", "intake", {
                "legacy_label": None, "goal": "route sweep", "intake": {},
                "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))
            head = store.load(OWNER, JOURNEY)["event_head_sha256"]
        self._serial += 1
        operation = {"data_refs": [], "credential_refs": [], **operation}
        envelope = {"schema": "flywheel.gateway-operation/v1", "journey_ref": JOURNEY,
                    "expected_event_head": head, "client_request_id": f"sweep-{self._serial}"}
        status, proposal = self.request("POST", f"/api/gateway-grants/prepare/{action}",
                                        {**envelope, "operation": operation})
        if status != 200:
            return None
        status, approved = self.request("POST", "/api/gateway-grants/approve-once",
                                        {"proposal_ref": proposal["proposal_ref"]})
        if status != 200:
            return None
        return json.dumps({**envelope, "grant_ref": approved["grant_ref"], **operation},
                          separators=(",", ":")).encode()

    def exercise(self, method: str, path: str, body=None, settle=None) -> dict:
        """Send one request; return what it caused. `settle(world)` waits for work the
        route started and answered before (a swarm, an operation)."""
        seen = (len(self.provider.requests), len(self.local.requests), len(self.entries()),
                len(self.refused), len(self.trap.outside), self.trace_starts())
        status, answer = self.request(method, path, body)
        if settle is not None:
            settle(self, answer)
        time.sleep(0.02)
        provider = self.provider.requests[seen[0]:]
        added = self.entries()[seen[2]:]
        return {"method": method, "path": path, "status": status,
                "answer": json.dumps(answer, default=str)[:300],
                "provider_model": [row for row in provider if _is_model(row)],
                "provider_other": [row for row in provider if not _is_model(row)],
                "local": self.local.requests[seen[1]:],
                "started": [e.content for e in added if e.kind == "endpoint_call_started"],
                "ended": [e.meta.get("call") for e in added
                          if e.kind in ("endpoint_call", "endpoint_call_failed")],
                "refused": self.refused[seen[3]:], "outside": self.trap.outside[seen[4]:],
                "trace_started": self.trace_starts() - seen[5]}


def faults(result: dict) -> list:
    """What a route did that breaks the rule: a model request with no account."""
    out = [f"{result['method']} {result['path']}: the reach rule refused a model request "
           f"that had no account ({text})" for text in result["refused"]]
    model, started = len(result["provider_model"]), len(result["started"])
    if model > started:
        out.append(f"{result['method']} {result['path']}: {model} model request(s) reached the "
                   f"provider and the ledger gained {started} started entr(ies)")
    if sorted(result["started"]) != sorted(call for call in result["ended"] if call):
        out.append(f"{result['method']} {result['path']}: a call it started has no end entry, "
                   "or an end entry has no start")
    return out
