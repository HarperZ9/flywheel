"""gateway.py -- the superapp's one origin (SUPERAPP.md increment 2, zero-dep).

A single stdlib HTTP server unifying static shell, health probes, projected world,
and model/tool APIs. Non-dispatch bodies live in focused `harness/gateway_*.py`
modules loaded lazily to keep the reviewed source-tool closure intact.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness.gateway_bind import ExclusiveThreadingHTTPServer  # no second socket can share the port (N-23)
from harness.run_paths import run_root_default
from harness.gateway_custody import is_private, is_signed
from harness.gateway_lane_calls import _forum_mcp_call, _relay_mcp_call, _relay_start_not_admitted
from harness.gateway_auth import (
    authenticate_owner as _auth_owner, load_or_create_owner_ref,
    load_or_create_token, check as _auth_check, DEFAULT_HOSTS,
)
from harness import gateway_openai_route as _openai_route
from harness.plan_run_store import forge_recheck, persist_forge_seal
from harness.gateway_body_drain import BodyDrainMixin

RECEIPT_CATALOG = (
    "artifacts/flywheel-local-coder-14b-benchmark-ci.json",
    "artifacts/flywheel-local-coder-14b-benchmark-m7-hard-scorecard.json",
    "artifacts/exe/model_release_readiness.local.json",
    "tasks/curated/hard_v2.jsonl",
    "demos/index.json",
)
SPINE = ("flywheel", "local-model", "telos", "index", "forum", "gather",
         "crucible", "learn", "mneme", "relay", "plexus")


def _resolve_credential(key_env: str) -> str:
    from harness.gateway_state import resolve_credential
    return resolve_credential(key_env)


def _probe(url: str, timeout: float = 2.0) -> tuple[bool, dict]:
    """GET a local health URL. Returns (healthy, parsed_json_or_empty)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
        try:
            return True, json.loads(body)
        except Exception:
            return True, {}
    except Exception:
        return False, {}


def endpoint_roster(serve_url: str, ollama_url: str) -> dict:
    from harness.gateway_state import endpoint_roster as _er
    return _er(serve_url, ollama_url, probe_fn=_probe, resolve_credential_fn=_resolve_credential)


def world_state(root: Path, catalog=RECEIPT_CATALOG) -> dict:
    from harness.gateway_state import world_state as _ws
    return _ws(root, catalog, SPINE)


def receipts_ledger(root: Path, run_root: Path | str) -> dict:
    from harness.gateway_state import receipts_ledger as _rl
    return _rl(root, run_root, world_state_fn=world_state)


def _workspace_root_allowlist() -> list[str]:
    from harness.gateway_state import workspace_root_allowlist
    return workspace_root_allowlist()


def _qs_value(qs: str, key: str) -> str:
    for part in qs.split("&"):
        if part.startswith(key + "="):
            return part[len(key) + 1:]
    return ""


def _qs_int(qs: str, key: str, default: int) -> int:
    try:
        return int(_qs_value(qs, key))
    except ValueError:
        return default


def _resolve_workspace_root(requested, default: Path) -> tuple[Path, str | None]:
    from harness.gateway_state import resolve_workspace_root
    return resolve_workspace_root(requested, default, allowlist_fn=_workspace_root_allowlist)


def _unified_roster() -> dict:
    from harness.gateway_state import unified_roster
    return unified_roster()


def _relay_remote_state() -> dict:
    from harness.gateway_state import relay_remote_state
    return relay_remote_state(_relay_mcp_call)


def _projected_world(root: Path) -> dict:
    from harness.gateway_state import projected_world
    return projected_world(root, world_state_fn=world_state)


def _training_status(run_root: str) -> dict:
    from harness.gateway_state import training_status
    return training_status(run_root)


def _countersign_run(result: dict) -> dict:
    from harness.gateway_state import countersign_run
    return countersign_run(result)


def _countersign_workflow(doc: dict) -> dict:
    from harness.gateway_state import countersign_workflow
    return countersign_workflow(doc)


def _forge(goal: str, **kw) -> dict:
    from harness.gateway_state import forge
    return forge(goal, **kw)


class _MemoryProofCache:
    """In-process verified-result cache for the gateway's lifetime."""
    def __init__(self): self.store: dict = {}
    def get(self, key): return self.store.get(key)
    def put(self, key, value): self.store[key] = value


_COMPANION_SEAT = None


def _companion_task(prompt: str, solution_sig: str = ""):
    from harness.gateway_state import companion_task
    return companion_task(prompt, solution_sig)


def get_companion_seat(serve_url: str):
    global _COMPANION_SEAT
    if _COMPANION_SEAT is not None:
        return _COMPANION_SEAT
    try:
        from harness.companion import CompanionSeat
        from harness.proposer import ServeProposer
    except Exception:
        return None
    _COMPANION_SEAT = CompanionSeat(
        ServeProposer(base_url=serve_url), oracle=None, cache=_MemoryProofCache(),
        escalation_endpoint="anthropic", initial_n=4, max_n=16)
    return _COMPANION_SEAT


def companion_answer(seat, prompt: str, solution_sig: str = "", effort: str | None = None) -> dict:
    from harness.gateway_state import companion_answer as _ca
    return _ca(seat, prompt, solution_sig, effort)


_ROUTER_LEDGER = None


def _router_ledger():
    if _ROUTER_LEDGER is not None:
        return _ROUTER_LEDGER
    from harness.gateway_ledger import for_home
    return for_home(os.environ.get("FLYWHEEL_HOME", str(Path.home() / ".flywheel")))


def route_answer(prompt: str, endpoint: str, proposer, *, credential: str = "local-none") -> dict:
    from harness.gateway_state import route_answer as _ra
    return _ra(prompt, endpoint, proposer, credential=credential)


def route_request(prompt: str, endpoint: str, model: str = "") -> tuple[dict, int]:
    return _openai_route.route_request(
        prompt, endpoint, model, unified_roster=_unified_roster,
        router_ledger=_router_ledger, route_answer=route_answer)


def _flatten_messages(messages) -> tuple[str, str]:
    return _openai_route.flatten_messages(messages)


def _resolve_proposer(model: str, serve_url: str, credential_bindings=None):
    return _openai_route.resolve_proposer(
        model, serve_url, credential_bindings,
        unified_roster=_unified_roster, router_ledger=_router_ledger)


def _chat_receipt(prompt, system, max_tokens, temperature, seed, out):
    return _openai_route.chat_receipt(prompt, system, max_tokens, temperature, seed, out)


def openai_embeddings(req: dict):
    from harness import gateway_embeddings, providers
    return gateway_embeddings.openai_embeddings(
        req, providers_registry=providers.REGISTRY, urllib_module=urllib,
        resolve_credential=_resolve_credential, ledger_of=_router_ledger)


_ROUTER_STATS = None


def get_router_stats():
    global _ROUTER_STATS
    if _ROUTER_STATS is None:
        from harness.router_stats import RouterStats
        _ROUTER_STATS = RouterStats(Path(run_root_default()) / "router_stats.json")
    return _ROUTER_STATS


def openai_chat(req: dict, serve_url: str, credential_bindings=None):
    return _openai_route.openai_chat(
        req, serve_url, credential_bindings, flatten_messages=_flatten_messages,
        resolve_proposer=_resolve_proposer, get_router_stats=get_router_stats,
        chat_receipt=_chat_receipt)


def openai_models() -> dict:
    return _openai_route.openai_models(unified_roster=_unified_roster)


class _Handler(BodyDrainMixin, BaseHTTPRequestHandler):
    root = REPO
    serve_url = "http://127.0.0.1:8765"
    ollama_url = "http://127.0.0.1:11434"
    run_root = run_root_default()
    MAX_BODY = 32 * 1024 * 1024
    cors = False
    auth_token = ""
    allowed_hosts = DEFAULT_HOSTS
    flywheel_home = Path(os.environ.get("FLYWHEEL_HOME", str(Path.home() / ".flywheel")))
    owner_ref, clock = None, staticmethod(lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    operation_service = operation_process_factory = native_codex_components = native_codex_lifecycle = None
    codex_account_manager = native_codex_config = session_token_store = _session_token_state_root = None

    def log_message(self, *a): pass

    def _cors(self):
        if self.cors:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.send_header("Content-Length", "0"); self.end_headers()

    def _content_length(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            return None
        return None if n < 0 or n > self.MAX_BODY else n

    def _json_req(self):
        from harness.evidence_public import parse_json
        length = self._content_length()
        if length is None:
            return None, ({"schema": "flywheel.evidence-transport-error/v1",
                           "error": {"code": "INVALID_LENGTH", "message": "request length is invalid"}}, 400)
        try:
            return parse_json(self.rfile.read(length)), None
        except Exception:
            return {}, None

    def _raw(self, body: bytes, content_type: str, code: int = 200, extra_headers=None):
        self.send_response(code); self.send_header("Content-Type", content_type)
        for key, value in {"Content-Length": str(len(body)), **(extra_headers or {})}.items():
            self.send_header(key, str(value))
        self._cors(); self.end_headers()
        if getattr(self, "command", "") != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        error = obj.get("error") if isinstance(obj, dict) else None
        error_code = error.get("code") if isinstance(error, dict) else None
        public_boundary = isinstance(obj, dict) and (
            obj.get("code") in {"CAPABILITY_NOT_ADMITTED", "GATEWAY_ROUTE_MALFORMED", "GATEWAY_ROUTE_MISMATCH",
                                "NOT_IN_BUILD", "LANE_SETUP_REQUIRED", "LANE_CANNOT_LAUNCH",
                                "LANE_TIMEOUT", "LANE_TOOL_ERROR"} or error_code == "MODEL_SELECTION_REQUIRED")
        if (getattr(self, "_gateway_guarded", False) and error_code != "PERMISSION_REQUIRED"
                and not (isinstance(obj, dict) and obj.get("governance_denied") is True)
                and not public_boundary and (code >= 400 or error_code)):
            from harness.gateway_provider_adapter import fixed_external_failure
            obj, code = fixed_external_failure()
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self._cors(); self.end_headers()
        if getattr(self, "command", "") != "HEAD":
            self.wfile.write(body)

    def _operation_components(self):
        state_root, current = self.flywheel_home / "state", type(self).native_codex_components
        if current is None or current.state_root != state_root:
            current = type(self)._configure_operation_components(state_root)
        return current.operation_service, current.operation_process_factory

    @classmethod
    def _configure_operation_components(cls, state_root):
        from harness.codex_managed_gateway_config import configure_managed_gateway_components
        return configure_managed_gateway_components(cls, state_root)

    def _session_tokens(self):
        state_root, cls = self.flywheel_home / "state", type(self)
        if cls.session_token_store is None or cls._session_token_state_root != state_root:
            from harness.credential_handles import CredentialHandleStore
            from harness.keychain import keychain_get
            from harness.session_token import SessionTokenStore
            cls.session_token_store = SessionTokenStore(CredentialHandleStore(state_root, keychain_get=keychain_get))
            cls._session_token_state_root = state_root
        return cls.session_token_store

    def _operation_response(self, response):
        if response.stream is None:
            return self._json(response.body, response.status)
        self.send_response(response.status); self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache"); self._cors(); self.end_headers()
        try:
            for chunk in response.stream:
                self.wfile.write(chunk); self.wfile.flush()
        except (BrokenPipeError, ConnectionError, OSError):
            pass

    def _route_operation(self, method):
        path = self.path.split("?", 1)[0]
        is_operation = (path in {"/api/agent", "/api/output/check"}  # start or read a governed operation
                        or path.startswith("/api/provider-sessions/")  # native session bindings and approvals
                        or path.startswith("/api/operations/"))  # one long-running operation
        if not is_operation:
            return False
        from harness.gateway_operation_route import route_gateway_operation
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        raw, content = b"", ""
        if method == "POST":
            length = self._content_length()
            raw = self.rfile.read(length) if length is not None else b""
            content = (self.headers.get("Content-Type", "") or "").split(";", 1)[0].strip()
        service, factory = self._operation_components()
        self._operation_response(route_gateway_operation(
            method, path, query=query, content_type=content, owner_ref=self.owner_ref,
            raw=raw, service=service, process_factory=factory))
        return True

    def _sse_chat(self, req: dict):
        from harness.gateway_state import stream_sse_chat
        return stream_sse_chat(self, req, flatten_fn=_flatten_messages, openai_chat_fn=openai_chat)

    def _proxy(self, target: str):
        length = self._content_length()
        if length is None:
            return self._json({"error": "invalid or oversized Content-Length"}, 400)
        data = self.rfile.read(length) if length else None
        req = urllib.request.Request(target, data=data, method=self.command,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                body, code = r.read(), r.status
        except Exception as exc:
            return self._json({"error": f"upstream unreachable: {exc}"}, 502)
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def _static(self, path: str):
        from harness.gateway_static import serve_static
        return serve_static(self, path)

    def _safe_500(self, e):
        try:
            from harness.gateway_read_timeout import uncaught
            self._json(*uncaught(self, e))
        except Exception:
            pass

    def _req_json(self):
        admitted = getattr(self, "_gateway_operation", None)
        if admitted is not None:
            del self._gateway_operation
            return admitted, None
        length = self._content_length()
        if length is None:
            return None, self._json({"error": "invalid or oversized Content-Length"}, 400)
        try:
            return (json.loads(self.rfile.read(length) or b"{}") if length else {}), None
        except Exception:
            return {}, None

    def _authorized(self) -> bool:
        path = self.path.split("?", 1)[0]
        from harness.gateway_key_gate import admits
        from harness.gateway_reach import at
        at(path)
        if is_signed(path) or admits(self, path):
            return True
        private = is_private(path)
        if not self.auth_token and not private:
            return True
        if private:
            owner, reason = ((None, "no_token") if not self.auth_token else _auth_owner(
                self.headers, self.command, self.auth_token, self.flywheel_home, allowed_hosts=self.allowed_hosts))
            ok = owner is not None
            if ok:
                self.owner_ref = owner
        else:
            ok, reason = _auth_check(self.headers, self.command, self.auth_token, allowed_hosts=self.allowed_hosts)
        if ok:
            return True
        refusal = ({"schema": "flywheel.evidence-transport-error/v1", "error": {
            "code": "AUTH_REQUIRED", "message": "gateway authentication is required"}}
            if private else {"error": "unauthorized", "reason": reason})
        body = json.dumps(refusal).encode()
        self.send_response(401); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        return False

    def _gateway_method(self, method, fallback=None):
        if not self._authorized():
            return
        try:
            if not self._route_operation(method):
                (fallback or (lambda: self.send_error(501)))()
        except BaseException as e:  # noqa: BLE001
            self._safe_500(e)

    def do_GET(self): self._gateway_method("GET", self._get)
    def do_POST(self): self._gateway_method("POST", self._post)
    def do_PUT(self): self._gateway_method("PUT")
    def do_DELETE(self): self._gateway_method("DELETE")
    def do_HEAD(self): self._gateway_method("HEAD")

    def _get(self):
        from harness import gateway_get_handlers as g
        p = self.path.split("?", 1)[0]
        qs = self.path.split("?", 1)[1] if "?" in self.path else ""
        if p.startswith("/api/traces/"): from harness.trace_routes import route_get; return route_get(self, p, qs)  # trace custody: capture channel hello, ping, status, export and deletion
        if p.startswith("/api/codex/"): from harness.codex_account_gateway_mount import account_get; return account_get(self, p)  # Private Codex account status and login result
        if p == "/api/import/inspect" or p.startswith("/api/import/inspect/"): from harness.import_route import handle_import_get; return self._json(*handle_import_get(p, self, qs))  # list or reopen owner-bound Inspect evidence
        if p == "/api/operations": return g.handle_operations(self, p, qs)  # discover owner/Journey operation metadata
        if p in ("/openapi.json",  # OpenAPI 3.1 for every route, generated
                 "/llms.txt",  # the same inventory, in the llmstxt.org shape
                 "/.well-known/flywheel.json"):  # the card pointing at both
            if g.handle_discovery(self, p): return
        if p.startswith("/api/writing/"): from harness.writing_route import writing_get; return self._json(*writing_get(self.path, owner_ref=self.owner_ref, state_root=self.flywheel_home / "state", clock=self.clock))  # private Writing workspace
        if p.startswith("/api/hooks"): from harness.hooks_route import handle_hooks_get; return self._json(*handle_hooks_get(p, run_root=Path(self.run_root)))  # hook definitions and their fire history
        if p.startswith("/api/subagents"): from harness.subagents_route import handle_subagents_get; return self._json(*handle_subagents_get(p, qs, run_root=self.run_root))  # the subagent roster and one agent record
        if p == "/api/schedule": from harness.schedule_route import handle_schedule_get; return self._json(*handle_schedule_get(p, run_root=self.run_root, clock=self.clock))  # schedules, what they owe, chain verdict
        if p.startswith("/api/peer-sessions"): from harness.peer_sessions_route import handle_peer_sessions_get; return self._json(*handle_peer_sessions_get(p, qs, state_root=self.flywheel_home / "state", clock=self.clock))  # local Claude Code and Codex sessions, read-only
        if p == "/api/scan/vulnerabilities": from harness.scan_route import handle_scan_get; return self._json(*handle_scan_get(p, root=self.root, run_root=self.run_root, clock=self.clock))  # the last code scan, re-checked
        if p == "/api/skills": from harness.skill_route import handle_skills_get; return self._json(*handle_skills_get(p, run_root=self.run_root))  # installed skills, read off disk
        if p.startswith("/api/runners"): from harness.runner_route import handle_runners_get; return self._json(*handle_runners_get(p, run_root=self.run_root, clock=self.clock))  # the operator's own machines, and the work they hold
        if p.startswith("/api/browser"): from harness.browser_route import handle_browser_get; return self._json(*handle_browser_get(p, run_root=self.run_root, clock=self.clock))  # sessions driving a browser or a desktop
        if p == "/api/pm/roadmap": from harness.pm_roadmap_route import handle_pm_get; return self._json(*handle_pm_get(p, run_root=self.run_root, clock=self.clock, journeys_state_root=self.flywheel_home / "state", owner_ref=self.owner_ref))  # the roadmap, derived from journeys and grants
        if p.startswith("/api/packs"): from harness.pack_admission_route import handle_pack_get; return self._json(*handle_pack_get(p, run_root=self.run_root))  # domain packs and their admission state
        if p == "/api/endpoints/health": return self._json(endpoint_roster(self.serve_url, self.ollama_url))  # every configured endpoint, probed
        if p == "/api/endpoints": return self._json(_unified_roster())  # the full universal-router roster
        if p == "/api/models": return g.handle_models(self, qs)  # one endpoint's model roster
        if p == "/api/world": return self._json(_projected_world(self.root))  # the projected world state, hashed
        if p == "/api/lanes": return g.handle_lanes_and_desktop(self, p, qs)  # the lane roster (umbrella layer)
        if p == "/api/desktop/status": return g.handle_lanes_and_desktop(self, p, qs)  # read-only connection facts
        if p.startswith("/api/studio/body/"): from harness.studio_body_route import handle_body_get; return self._json(*handle_body_get(p))  # Studio body status and delivery refs
        if p.startswith("/api/live-screen/"): from harness.live_screen_gateway_mount import live_screen_get; return live_screen_get(self, p)  # native live-screen status, sources, events, preview bytes
        if p == "/api/forum/status": return self._json(_forum_mcp_call("forum.status", {}))  # forum lane status (via MCP)
        if p == "/api/forum/ledger": return self._json(_forum_mcp_call("forum.ledger.summary", {}))  # forum ledger summary
        if p == "/api/forum/gates": return self._json(_forum_mcp_call("gate_list", {}))  # pending approval gates
        if p == "/api/forum/run-room": return self._json(_forum_mcp_call("forum.run.room", {}))  # the current run room snapshot
        if p in ("/api/relay/status", "/api/relay/result"): return g.handle_relay_run(self, p, qs, _relay_mcp_call)  # a relay run, via the exec lane
        if p == "/api/relay/runs": return self._json(_relay_mcp_call("local_agent_runs", {}))  # recent relay runs (survive a restart)
        if p == "/api/relay/sessions": return self._json(_relay_mcp_call("local_agent_sessions", {}))  # saved relay sessions (follow you)
        if p == "/api/relay/remote": return self._json(_relay_remote_state())  # can a phone reach this workstation
        if p == "/api/lessons": return g.handle_lessons(self, p)  # the organizational learning loop
        if p == "/api/lessons/patterns": return g.handle_lessons(self, p)  # recurring patterns for human admission
        if p == "/api/governance/tiers": return g.handle_governance(self, p, qs)  # TADR tier definitions
        if p == "/api/governance/compliance": return g.handle_governance(self, p, qs)  # control baseline compliance check
        if p == "/api/governance/classify": return g.handle_governance(self, p, qs)  # classify a system (GET with query params)
        if p.startswith("/api/lanes/") or p == "/api/settings/node_path": from harness.lane_console_route import console_get; return self._json(*console_get(p))  # lane console: GET callable, <lane>/setup, local-model/root, node_path; POST install, <lane>/check, <lane>/tools (plugin.probe grant)
        if p == "/api/training/status": return self._json(_training_status(self.run_root))  # training lane status, read-only
        if p == "/api/train/duel": return g.handle_misc_get(self, p, qs)  # verified-inference duel summary (read-only)
        if p == "/api/train/loop": return g.handle_train_loop(self)  # the loop-closure self-audit (on demand)
        if p == "/api/loops": return g.handle_misc_get(self, p, qs)  # which candidate loops close? measured, not drawn
        if p == "/api/tension": return g.handle_misc_get(self, p, qs)  # measurement disagreements, kept re-checkable
        if (p == "/api/infra/trust-model"  # who is trusted here, and for what
                or p == "/api/infra/bom"  # the run bill of materials
                or p == "/api/infra/egress"):  # the live egress table, scanned
            from harness.infra_route import handle_infra_get; return self._json(*handle_infra_get(p))
        if p == "/api/instruments": return g.handle_misc_get(self, p, qs)  # the evaluation-engineering register
        if p == "/api/typeface/gallery": return g.handle_typeface_get(self, p, qs)  # the marketplace of published faces (metadata)
        if p == "/api/typeface/face": return g.handle_typeface_get(self, p, qs)  # one published face, bytes included
        if p == "/api/academy": return g.handle_misc_get(self, p, qs)  # the curriculum, derived from the live code
        if p == "/api/frontier": return g.handle_frontier(self)  # the RAM/compute frontier, measured here
        if p == "/api/retention": return g.handle_query_views(self, p, qs)  # what is still held, not what was once shown
        if p == "/api/comprehension": return g.handle_query_views(self, p, qs)  # ownership from checked evidence, not blame
        if p == "/api/readiness": return g.handle_misc_get(self, p, qs)  # release readiness, measured not felt
        if p == "/api/credo": return g.handle_misc_get(self, p, qs)  # the belief, content-addressed and retrievable
        if p == "/api/feeds": return g.handle_query_views(self, p, qs)  # cross-domain live feeds through gather
        if p == "/api/uplift": return g.handle_misc_get(self, p, qs)  # bare-vs-wrapped uplift bench (read-only roster)
        if p == "/api/graph": return g.handle_query_views(self, p, qs)  # cross-surface knowledge graph + context plan
        if p in ("/api/usage", "/api/usage/live"): from harness.usage_route import handle_usage_get; return self._json(*handle_usage_get(p, qs, self.run_root))  # summary or private live counters
        if p == "/api/receipts": return self._json(receipts_ledger(self.root, self.run_root))  # the receipts ledger (catalog + envelopes)
        if p == "/api/receipts/proof": return g.handle_receipts_proof(self, qs, receipts_ledger)  # prove one receipt is in the log
        if p == "/api/profiles": return g.handle_misc_get(self, p, qs)  # profile manifests over the one substrate
        if p == "/api/workflows": return g.handle_misc_get(self, p, qs)  # workflow definitions + recent runs
        if p == "/api/workflow/run": return g.handle_misc_get(self, p, qs)  # one run's stored trace, chain-reverified
        if p == "/api/science/runs": return g.handle_misc_get(self, p, qs)  # eval history, chain-reverified
        if p == "/api/science/run": return g.handle_misc_get(self, p, qs)  # one stored science run
        if p in ("/api/agent/runs", "/api/agent/run"): from harness.agent_run_reader import route_agent_history; return self._json(*route_agent_history(p, qs, self.run_root))  # private bounded history
        if p == "/api/memory": return g.handle_misc_get(self, p, qs)  # durable memory stats (fold index)
        if p == "/api/memory/list": return g.handle_misc_get(self, p, qs)  # browse stored spans, verbatim
        if p.startswith("/api/agent/mcp/"): from harness.gateway_agent_mcp_route import agent_mcp_get; return self._json(*agent_mcp_get(p, owner_ref=self.owner_ref, state_root=self.flywheel_home / "state"))  # Registered MCP tools and owner-scoped discovery receipts
        if p == "/api/plugins": return g.handle_misc_get(self, p, qs)  # every mounted capability, one manifest shape
        if p == "/api/parity": return g.handle_misc_get(self, p, qs)  # the capability matrix, witnessed not asserted
        if p == "/api/projects": return g.handle_misc_get(self, p, qs)  # the registered project/directory roster
        if p == "/api/store": return g.handle_store_get(self, p, qs)  # verifiable substrate stats
        if p == "/api/store/verify": return g.handle_store_get(self, p, qs)  # walk the chain AND re-check the records
        if p == "/api/store/audit": return g.handle_store_get(self, p, qs)  # the hash-chained audit tail
        if p == "/api/marketplace": return g.handle_misc_get(self, p, qs)  # curated catalog over the plugin registry
        if p == "/api/auth": return g.handle_misc_get(self, p, qs)  # subscription sign-in roster
        if p == "/api/keychain": return g.handle_misc_get(self, p, qs)  # credential names + presence, never values
        if p == "/api/bulletin-identity": return g.handle_misc_get(self, p, qs)  # native Bulletin identity presence
        if p == "/api/credential-handles": return g.handle_misc_get(self, p, qs)  # handles held for this owner, presence only
        if p == "/api/session-tokens": return g.handle_misc_get(self, p, qs)  # session tokens issued to this owner
        if p == "/api/plugins/probe": return g.handle_misc_get(self, p, qs)  # spawn a plugin's server, report its real tools
        if p == "/api/router/stats": return self._json(get_router_stats().snapshot())  # observed per-provider success/cost
        if p == "/v1/models": return self._json(openai_models())  # OpenAI-compatible model list (the roster)
        if (p.startswith("/v1/")  # OpenAI-compatible, proxied to the endpoint
                or p == "/generate"  # the raw generate call, proxied
                or p == "/health"):  # is the model endpoint answering
            return self._proxy(self.serve_url.rstrip("/") + p)
        return self._static(p)

    def _plan_request(self, path):
        from harness.plan_run_route import gateway_plan_request
        return gateway_plan_request(self, path, resolve_root=_resolve_workspace_root, countersign=_countersign_workflow)

    def _post(self):
        from harness import gateway_post_core as pc, gateway_post_custody as cu, gateway_post_studio as ps
        p = self.path.split("?", 1)[0]
        if p == "/api/scaffold" or p.startswith("/api/traces/"): from harness.trace_routes import route_post; return route_post(self, p)  # turn guarantee and trace custody
        if p.startswith("/api/codex/"): from harness.codex_account_gateway_mount import account_post; return account_post(self, p)  # Explicit Codex login, cancellation, and logout requests
        if p == "/api/import/inspect": from harness.import_route import handle_import_post; return self._json(*handle_import_post(p, self))  # raw exact-byte Inspect upload
        if p.startswith("/api/plan/"): return self._plan_request(p)  # a plan request, private custody
        if p.startswith("/api/session-tokens/"): return cu.post_session_tokens(self, p)  # mint or revoke a session token
        if p == "/api/enterprise-envs/service-desk-incident/review": return cu.post_service_desk_review(self, p)  # review ServiceDesk incident evidence
        if p == "/api/incident-sim/process-audit/review": return cu.post_process_audit_review(self, p)  # review incident-sim process-audit packet
        if p.startswith("/api/evidence/"): return cu.post_custody_route(self, p, _resolve_workspace_root)  # append to the evidence ledger
        if p.startswith("/api/journeys/extensions/"): return cu.post_custody_route(self, p, _resolve_workspace_root)  # contextual extensions, fail-closed
        if p.startswith("/api/journeys/"): return cu.post_custody_route(self, p, _resolve_workspace_root)  # advance a journey, receipted
        if p.startswith("/api/source-context/"): return cu.post_custody_route(self, p, _resolve_workspace_root)  # attach readable selected context
        if p.startswith("/api/context-memory/"): return cu.post_custody_route(self, p, _resolve_workspace_root)  # capture/preflight against Canon context store
        if p.startswith("/api/agent/mcp/"): return cu.post_custody_route(self, p, _resolve_workspace_root)  # Admit owner-bound MCP discovery receipts
        if p == "/api/continuation/preview": return cu.post_custody_route(self, p, _resolve_workspace_root)  # preview selected context and repository state
        if p.startswith("/api/continuation/"): return cu.post_custody_route(self, p, _resolve_workspace_root)  # preview/import health, then start a Journey
        if p.startswith("/api/grants/"): return cu.post_custody_route(self, p, _resolve_workspace_root)  # request or answer a capability grant
        if p.startswith("/api/writing/"): return cu.post_custody_route(self, p, _resolve_workspace_root)  # private Writing workspace
        if p.startswith("/api/gateway-grants/"): return cu.post_custody_route(self, p, _resolve_workspace_root)  # grants scoped to the gateway itself
        if p.startswith("/api/credential-handles/"): return cu.post_custody_route(self, p, _resolve_workspace_root)  # bind a handle, presence only
        if p.startswith("/api/hooks/"): return cu.post_hooks(self, p)  # define, edit or fire a hook
        if p.startswith("/api/subagents/"): return cu.post_subagents(self, p)  # run a subagent, recorded
        if p.startswith("/api/schedule/"): return cu.post_json_surface(self, p)  # define a schedule, or tick the clock
        if p == "/api/scan/vulnerabilities": return cu.post_json_surface(self, p)  # run a scan, append it to the chain
        if p.startswith("/api/runners/"): return cu.post_json_surface(self, p)  # mint, enroll, dispatch, claim, complete
        if p.startswith("/api/browser/"): return cu.post_json_surface(self, p)  # open a session, or attempt one act in it
        if p.startswith("/api/skills/"): return cu.post_json_surface(self, p)  # install or invoke a skill
        if cu.authorize_post_action(self, p, _auth_owner): return
        if p == "/v1/chat/completions": return pc.post_chat_completions(self, flatten_fn=_flatten_messages, openai_chat_fn=openai_chat)  # OpenAI-compatible, routes to ANY provider
        if p == "/api/bench/run": return pc.post_bench_or_packs(self, p)  # private verified benchmark
        if p == "/api/packs/admit": return pc.post_bench_or_packs(self, p)  # admit a domain pack
        if p == "/v1/embeddings": req, bad = self._req_json(); return bad if bad else self._json(*openai_embeddings(req))  # OpenAI-compatible, routed to a provider
        if p in ("/v1/messages", "/v1/messages/count_tokens", "/v1/responses"): from harness.gateway_interfaces import serve; return serve(self, p, _router_ledger())  # Messages and Responses, answered here
        if p.startswith("/v1/") or p == "/generate": return self._proxy(self.serve_url.rstrip("/") + p)  # OpenAI-compatible and raw generate, proxied to the endpoint
        if p == "/api/relay/start": return _relay_start_not_admitted(self)  # Relay run launch is not admitted in the bundled release
        if p == "/api/forge": return pc.post_forge(self, forge_fn=_forge, persist_seal_fn=persist_forge_seal)  # goal -> verified PRP (the studio)
        if p == "/api/academy/complete": return pc.post_science_or_retrieve(self, p, resolve_root_fn=_resolve_workspace_root)  # bind a passed receipt to a lesson
        if p == "/api/forge/recheck": return pc.post_forge_recheck(self, recheck_fn=forge_recheck)  # did an arm drift since the forge?
        if p == "/api/science": return pc.post_science_or_retrieve(self, p, resolve_root_fn=_resolve_workspace_root)  # evidence -> spec -> witnessed judgment, one chain
        if p == "/api/retrieve": return pc.post_science_or_retrieve(self, p, resolve_root_fn=_resolve_workspace_root)  # retrieval that cites its evidence
        if p == "/api/snapshot": return pc.post_verification_tools(self, p)  # the citation, frozen: bytes as the receipt
        if p == "/api/import": from harness.import_route import handle_import_post; return self._json(*handle_import_post(p, self))  # arrive with your whole setup, keep the proof
        if p == "/api/lean": return pc.post_verification_tools(self, p)  # the apex oracle: the kernel decides
        if p == "/api/invent": return pc.post_verification_tools(self, p)  # generation under witness: propose, judge, keep
        if p == "/api/suite": return pc.post_verification_tools(self, p)  # can this acceptance suite refuse wrong code?
        if p == "/api/tension": return pc.post_verification_tools(self, p)  # bank a measurement pair with frozen sources
        if p == "/api/capability": return pc.post_verification_tools(self, p)  # probe a model on THIS machine
        if p == "/api/retention": return pc.post_verification_tools(self, p)  # bank an unaided retest outcome, linked
        if p == "/api/explain": return pc.post_verification_tools(self, p)  # the teach-back as a receipt (engagement, mechanical)
        if p == "/api/attest": return pc.post_verification_tools(self, p)  # ownership made checkable: sign-off bound to the walk
        if p == "/api/route": return pc.post_route_and_companion(self, p, route_request_fn=route_request, get_seat_fn=get_companion_seat, answer_fn=companion_answer)  # universal router: send to ANY provider, with a receipt
        if p == "/api/companion": return pc.post_route_and_companion(self, p, route_request_fn=route_request, get_seat_fn=get_companion_seat, answer_fn=companion_answer)  # the seat: answer local, escalate the hard slice
        if p == "/api/workflow": return pc.post_workflow(self, resolve_root_fn=_resolve_workspace_root, countersign_fn=_countersign_workflow)  # staged run with a chained receipt, any endpoint
        if p == "/api/memory/recall": return ps.post_lsp_and_memory(self, p, resolve_root_fn=_resolve_workspace_root)  # verbatim recall from the fold index
        if p in ("/api/auth/login",  # begin a subscription sign-in
                 "/api/auth/token",  # hand back a pasted token, never logged
                 "/api/auth/cancel",  # cancel local completion only
                 "/api/auth/logout"):  # sign out of a provider
            return pc.post_auth_and_keys(self, p)
        if p == "/api/keychain/set": return pc.post_auth_and_keys(self, p)  # store a secret in the OS keychain
        if p == "/api/keychain/delete": return pc.post_auth_and_keys(self, p)  # remove a stored secret
        if p == "/api/bulletin-identity/create": return pc.post_auth_and_keys(self, p)  # create native identity in keychain only
        if p == "/api/bulletin-identity/register": return pc.post_auth_and_keys(self, p)  # register native identity at fixed Bulletin origin
        if p == "/api/store/entity": return ps.post_store_and_projects(self, p, resolve_root_fn=_resolve_workspace_root)  # store a content-addressed entity
        if p == "/api/store/query": return ps.post_store_and_projects(self, p, resolve_root_fn=_resolve_workspace_root)  # query entities by kind/project
        if p == "/api/projects/add": return ps.post_store_and_projects(self, p, resolve_root_fn=_resolve_workspace_root)  # register a project directory
        if p == "/api/projects/remove": return ps.post_store_and_projects(self, p, resolve_root_fn=_resolve_workspace_root)  # unregister a project directory
        if p == "/api/lint": return ps.post_store_and_projects(self, p, resolve_root_fn=_resolve_workspace_root)  # native receipt-carrying linter over a project
        if (p == "/api/index"  # project Index summary routes
                or p == "/api/index/summary"  # project Index summary routes
                or p.startswith("/api/index/workspace-map/")):  # project Index jobs
            return ps.post_store_and_projects(self, p, resolve_root_fn=_resolve_workspace_root)
        if p == "/api/discourse": return ps.post_discourse_and_learn(self, p)  # drive the chorus satellite over a gathered corpus
        if p == "/api/discourse/corpora": return ps.post_discourse_and_learn(self, p)  # discover gather corpora as discourse sources
        if p == "/api/learn/animate": return ps.post_discourse_and_learn(self, p)  # a lesson -> a runnable manim scene (academy)
        if p == "/api/discourse/digests": return ps.post_discourse_and_learn(self, p)  # what the chorus daemon has synthesized
        if p == "/api/robustness/inject": return ps.post_discourse_and_learn(self, p)  # measure the gated tool loop's injection containment
        if p in ("/api/typeface",  # mint a typeface
                 "/api/typeface/publish",  # publish one
                 "/api/typeface/family",  # derive a family
                 "/api/typeface/variable"):  # derive a variable font
            return ps.post_studio(self, p)
        if p == "/api/studio/poster": return ps.post_studio(self, p)  # plate + minted face + copy, one receipt
        if p.startswith("/api/lanes/") or p == "/api/settings/node_path": from harness.lane_console_route import console_post_mount; return console_post_mount(self, p)  # lane console POST routes
        if p == "/api/telos/kernel": return ps.post_studio(self, p)  # run a bridged telos creative kernel
        if p == "/api/studio/graph": return ps.post_studio(self, p)  # branching creative DAG, Merkle receipt
        if p == "/api/studio/pipeline": return ps.post_studio(self, p)  # ordered stages, one chained receipt
        if p == "/api/telos/raster": return ps.post_studio(self, p)  # dither / pixel-sort over a plate or PNG
        if p == "/api/studio/brandkit": return ps.post_studio(self, p)  # one seed + a name -> a whole identity
        if p == "/api/studio/sound": return ps.post_studio(self, p)  # the seeded chime study, score = receipt
        if p.startswith("/api/live-screen/"): from harness.live_screen_gateway_mount import live_screen_post; return live_screen_post(self, p)  # authority-bound live-screen lifecycle and event polling
        if p.startswith("/api/studio/body/"): req, bad = self._req_json(); from harness.studio_body_route import handle_body_gateway_post; return bad if bad else self._json(*handle_body_gateway_post(p, req, self))  # Studio body snapshots and authority-gated actions
        if p == "/api/lsp": return ps.post_lsp_and_memory(self, p, resolve_root_fn=_resolve_workspace_root)  # editor intelligence over any LSP server
        if p == "/api/memory/note": return ps.post_lsp_and_memory(self, p, resolve_root_fn=_resolve_workspace_root)  # durable content-addressed note
        if p == "/api/lessons/admit": return ps.post_lesson_transition(self, "admitted")  # transition a lesson to admitted
        if p == "/api/lessons/retire": return ps.post_lesson_transition(self, "retired")  # transition a lesson to retired
        if p == "/api/eval/run": return ps.post_eval_audit_lane_infra(self, p)  # a real eval -> a sealed, offline-verifiable receipt
        if p == "/api/eval/verify": return ps.post_eval_audit_lane_infra(self, p)  # re-check a receipt offline; the verdict is the answer
        if p == "/api/audit/run": return ps.post_eval_audit_lane_infra(self, p)  # a post-work review -> a receipt chained onto the work receipt
        if p == "/api/audit/verify": return ps.post_eval_audit_lane_infra(self, p)  # re-check an audit receipt (and its chain) offline
        if p == "/api/usage/verify": return ps.post_eval_audit_lane_infra(self, p)  # re-check a usage receipt offline; the verdict is the answer
        if p.startswith("/api/lane/"): return ps.post_eval_audit_lane_infra(self, p)  # generic lane caller
        if (p == "/api/infra/credential-scan"  # scan for exposed credentials
                or p == "/api/infra/isolation"  # run the isolation test
                or p == "/api/infra/kill"):  # the kill switch
            return ps.post_eval_audit_lane_infra(self, p)
        return self._json({"error": "not found"}, 404)


def _build_parser() -> argparse.ArgumentParser:
    from harness.gateway_cli import build_parser
    return build_parser(REPO)


def _resolve_hosts(requested):
    from harness.gateway_cli import resolve_hosts
    return resolve_hosts(requested)


def _bind_hosts(hosts, port, *, strict=False):
    from harness.gateway_cli import bind_hosts
    return bind_hosts(hosts, port, _Handler, strict=strict)


def _serve_all(servers):
    from harness.gateway_cli import serve_all
    return serve_all(servers, _Handler)


def main(argv=None) -> int:
    from harness.gateway_cli import run_main
    return run_main(
        argv, _Handler, build_parser_fn=_build_parser, resolve_hosts_fn=_resolve_hosts,
        bind_hosts_fn=_bind_hosts, serve_all_fn=_serve_all, load_token_fn=load_or_create_token,
        router_ledger_fn=_router_ledger)


if __name__ == "__main__":
    raise SystemExit(main())
