"""gateway.py — the superapp's one origin (SUPERAPP.md increment 2, zero-dep).

A single stdlib HTTP server that unifies the shell and its live state:

  static           the showcase shell + demos + artifacts, one origin, so the
                   page's fetches (increment 1) hit same-origin paths.
  /api/endpoints/health   the unified endpoint roster. LOCAL tiers (serve.py,
                   ollama) get a real health probe; ENTERPRISE providers report
                   a credential-present BOOLEAN only, never a key value and
                   never a network call (SUPERAPP boundary: env-presence, not
                   secrets).
  /api/world       v0 of the projected world both person and model read: the
                   flagship spine roster plus a receipt catalog with a root hash
                   over the cataloged files. Tamper one byte of a receipt and
                   the root hash moves.
  /v1/*, /generate proxied to serve.py so the local model is reachable through
                   the same origin.

Two falsifiers (the verifier must be able to fail):
  - kill serve.py: the local 14B tier in /api/endpoints/health must flip to
    unhealthy on the next request. If it stays healthy, the probe is fake.
  - touch a cataloged receipt: /api/world root_hash must change. If it does
    not, the catalog is not actually reading the files.

Usage:
  python harness/gateway.py --port 8799 --root .   # serve the repo
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
# Ensure `from harness.X import ...` resolves even when run as `python
# harness/gateway.py` (script mode puts harness/ on the path, not the repo root),
# so the on-demand endpoint_registry / context_forge imports work in both modes.
if str(REPO) not in sys.path: sys.path.insert(0, str(REPO))
from harness.run_paths import run_root_default
from harness.gateway_auth import (authenticate_owner as _auth_owner,
    load_or_create_owner_ref, load_or_create_token, check as _auth_check, DEFAULT_HOSTS)
from harness import gateway_openai_route as _openai_route
from harness.plan_run_store import forge_recheck, persist_forge_seal
def _resolve_credential(key_env: str) -> str:
    """Env first, OS keychain second; '' when neither. Import is lazy so a
    stripped deployment without keychain.py still serves env-only."""
    try:
        from harness.keychain import resolve_credential
        return resolve_credential(key_env)
    except Exception:
        return os.environ.get(key_env or "", "")
# Receipt catalog: in-repo, re-checkable artifacts that define the world state.
# Relative to the served root. Missing files are reported honestly as absent.
RECEIPT_CATALOG = (
    "artifacts/flywheel-local-coder-14b-benchmark-ci.json",
    "artifacts/flywheel-local-coder-14b-benchmark-m7-hard-scorecard.json",
    "artifacts/exe/model_release_readiness.local.json",
    "tasks/curated/hard_v2.jsonl",
    "demos/index.json",
)

# The flagship spine. Flywheel is the platform; the rest are lanes inside it
# (organs of the reconcile), not peers. local-model is the trained-model lane.
SPINE = ("flywheel", "local-model", "telos", "index", "forum", "gather",
         "crucible", "learn", "mneme", "relay", "plexus")
def _probe(url: str, timeout: float = 2.0) -> tuple[bool, dict]:
    """GET a local health URL. Returns (healthy, parsed_json_or_empty).
    Any error is unhealthy — a down endpoint must read as down."""
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
    """Local tiers get a live probe; enterprise providers report credential
    presence only (no network, no value)."""
    local = []
    ok, info = _probe(serve_url.rstrip("/") + "/health")
    local.append({"name": "flywheel-serve", "tier": "local", "kind": "serve",
                  "healthy": ok, "model_ref": info.get("model_ref", "")})
    ok, info = _probe(ollama_url.rstrip("/") + "/api/version")
    local.append({"name": "flywheel-ollama", "tier": "local", "kind": "ollama",
                  "healthy": ok, "version": info.get("version", "")})

    enterprise = []
    try:
        from harness.endpoints import PROVIDERS
    except Exception:
        try:
            from endpoints import PROVIDERS  # standalone run
        except Exception:
            PROVIDERS = {}
    for name, spec in PROVIDERS.items():
        key_env = spec.get("key", "")
        enterprise.append({
            "name": name, "tier": "enterprise", "model": spec.get("model", ""),
            "credential_present": bool(key_env and _resolve_credential(key_env)),
            "key_env": key_env,   # the NAME only, never the value
        })
    healthy_local = sum(1 for e in local if e["healthy"])
    return {"schema": "flywheel.endpoint-roster/v1",
            "local": local, "enterprise": enterprise,
            "local_healthy": healthy_local, "local_total": len(local),
            "enterprise_configured": sum(1 for e in enterprise if e["credential_present"])}
def world_state(root: Path, catalog=RECEIPT_CATALOG) -> dict:
    """The projected world v0: spine roster + receipt catalog with a root hash.
    Root hash is a sha256 over sorted 'path:filehash' lines, so any file change
    (or appearance/disappearance) moves it."""
    receipts = []
    lines = []
    for rel in catalog:
        p = (root / rel)
        if p.is_file():
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            receipts.append({"path": rel, "sha256": h, "size": p.stat().st_size,
                             "present": True})
        else:
            h = "MISSING"
            receipts.append({"path": rel, "sha256": h, "present": False})
        lines.append(f"{rel}:{h}")
    root_hash = hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()
    return {"schema": "flywheel.world/v0",
            "spine": list(SPINE),
            "receipts": receipts,
            "receipt_count": len(receipts),
            "present_count": sum(1 for r in receipts if r["present"]),
            "root_hash": root_hash}
def receipts_ledger(root: Path, run_root: Path | str) -> dict:
    """The receipts ledger: the in-repo receipt catalog (re-hashed on every
    read) plus the accepted proof envelopes under the run root. Every entry
    is re-checkable — catalog entries by re-hashing the file, envelopes by
    their recorded content hash. An unreadable envelope is reported as
    UNREADABLE, never dropped."""
    catalog = world_state(root)["receipts"]
    env_dir = Path(run_root) / "envelopes"
    envelopes = []
    if env_dir.is_dir():
        for p in sorted(env_dir.glob("*.json")):
            entry = {"name": p.name, "size": p.stat().st_size,
                     "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
                entry["verdict"] = str(doc.get("verdict", "?"))
                entry["task_id"] = str(doc.get("task_id", ""))
            except Exception:
                entry["verdict"] = "UNREADABLE"
                entry["task_id"] = ""
            envelopes.append(entry)
    passes = sum(1 for e in envelopes if e["verdict"] == "PASS")
    # a Merkle commitment over the ordered envelope hashes: a stranger can
    # prove one receipt is in this log without holding the whole ledger
    from harness.transparency_log import merkle_root
    leaves = [e["sha256"] for e in envelopes]
    root_hash = merkle_root(leaves) if leaves else ""
    return {"schema": "flywheel.receipts/v1",
            "catalog": catalog,
            "catalog_present": sum(1 for r in catalog if r["present"]),
            "envelopes": envelopes,
            "envelope_count": len(envelopes),
            "pass_count": passes,
            "merkle_root": root_hash,
            "merkle_note": "root over the ordered envelope hashes; GET "
                           "/api/receipts/proof?leaf=<sha256> returns an "
                           "inclusion proof re-checkable offline"}
def _workspace_root_allowlist() -> "list[str]":
    """Permitted workspace-root prefixes, normalized for prefix comparison.
    Read from FLYWHEEL_WORKSPACE_ROOTS (os.pathsep-separated). Empty = open
    resolution (any existing directory), preserving the prior default; set it
    to confine agent runs to named trees."""
    import os
    raw = os.environ.get("FLYWHEEL_WORKSPACE_ROOTS", "")
    roots = []
    for part in raw.split(os.pathsep):
        part = part.strip()
        if not part: continue
        try:
            roots.append(str(Path(part).expanduser().resolve()))
        except (OSError, ValueError):
            continue
    return roots
def _qs_value(qs: str, key: str) -> str:
    """First value for `key` in a raw query string, '' when absent."""
    for part in qs.split("&"):
        if part.startswith(key + "="): return part[len(key) + 1:]
    return ""


def _qs_int(qs: str, key: str, default: int) -> int:
    try:
        return int(_qs_value(qs, key))
    except ValueError:
        return default


def _resolve_workspace_root(requested, default: Path) -> "tuple[Path, str | None]":
    """Resolve the workspace root an agent run operates in. The caller may
    name any EXISTING directory (the desktop IDE points at an open project);
    the ToolExecutor then sandboxes reads and gated writes to that root. A
    missing or non-directory path is refused, never silently substituted.

    When FLYWHEEL_WORKSPACE_ROOTS is set, existence is not enough: the resolved
    root must equal or sit under an allowlisted prefix, else it is refused BY
    NAME. Existence is not authorization -- without this a request could scope
    the executor to a home or credentials directory just by naming it."""
    if not requested: return default, None
    try:
        p = Path(str(requested)).expanduser().resolve()
    except (OSError, ValueError) as e:
        return default, f"invalid root: {e}"
    if not p.is_dir():
        return default, f"root is not an existing directory: {requested}"
    allow = _workspace_root_allowlist()
    if allow:
        rp = str(p)
        if not any(rp == a or rp.startswith(a + os.sep) for a in allow):
            return default, (f"root is not under an allowlisted workspace "
                             f"prefix: {requested}")
    return p, None


def _unified_roster() -> dict:
    """The full universal-router roster (endpoint_registry): every provider,
    credential-presence only. Graceful if the module is unavailable."""
    try:
        from harness.endpoint_registry import unified_roster
    except Exception:
        try:
            from endpoint_registry import unified_roster  # standalone run
        except Exception as e:
            return {"error": f"endpoint_registry unavailable: {e}"}
    try:
        return unified_roster()
    except Exception as e:                    # a runtime failure must degrade, not crash the handler
        return {"error": f"unified_roster failed: {e}"}


def _forum_mcp_call(tool: str, args: dict) -> dict:
    """Call one forum MCP tool, gracefully degraded.

    Spawns the forum lane's MCP server, calls the named tool, and returns the
    parsed JSON. If the forum lane is down or slow, returns an honest error
    dict so the desktop view can render a 'forum offline' state.
    """
    from harness.mcp_client import MCPClient, MCPError
    from harness.lanes import resolve_mcp_launch
    try:
        command = resolve_mcp_launch("forum")
        with MCPClient(command, timeout=20, client_name="flywheel-forum-proxy") as c:
            res = c.call_text(tool, args)
            if not res["ok"]:
                return {"error": f"forum {tool} error: {res['text'][:200]}"}
            import json as _json
            try:
                return _json.loads(res["text"])
            except _json.JSONDecodeError:
                return {"raw": res["text"][:500]}
    except (MCPError, FileNotFoundError, OSError) as e:
        return {"error": f"forum lane unavailable: {e}"}


def _relay_mcp_call(tool: str, args: dict) -> dict:
    """Call one relay MCP tool, gracefully degraded.

    relay is the execution lane (an accountable, witnessed coding agent). Forwarding
    to it here makes the gateway the single phone-facing origin: a phone drives the
    gateway (one auth, one tunnel), and a relay-backed run comes back with relay's
    verifiable run_id and ledger checkpoint, the same receipts a desktop run gets.
    """
    from harness.lanes import resolve_mcp_launch
    from harness.mcp_client import MCPClient, MCPError
    try:
        command = resolve_mcp_launch("relay")
        with MCPClient(command, timeout=30, client_name="flywheel-relay-proxy") as c:
            res = c.call_text(tool, args)
            if not res["ok"]:
                return {"error": f"relay {tool} error: {res['text'][:200]}"}
            import json as _json
            try:
                return _json.loads(res["text"])
            except _json.JSONDecodeError:
                return {"raw": res["text"][:500]}
    except (MCPError, FileNotFoundError, OSError) as e:
        return {"error": f"relay lane unavailable: {e}"}


def _projected_world(root: Path) -> dict:
    """The full projected world (world.py: roster + findings + cursor, root-hashed).
    Falls back to the inline v0 receipt catalog if world.py is unavailable."""
    try:
        from harness.world import project_world
        return project_world(repo_root=root)
    except Exception:
        return world_state(root)


def _training_status(run_root: str) -> dict:
    """Read-only 32B supervisor status (training_lane): log-derived state +
    screen liveness + checkpoint progress. Graceful if the module is unavailable."""
    try:
        from harness.training_lane import training_status
    except Exception:
        try:
            from training_lane import training_status  # standalone run
        except Exception as e:
            return {"error": f"training_lane unavailable: {e}"}
    try:
        return training_status(run_root)
    except Exception as e:                    # e.g. an unreadable/locked log -> honest error, no crash
        return {"error": f"training_status failed: {e}"}


def _countersign_run(result: dict) -> dict:
    """Build 5 from the dossier (the Sello requirement): the receiving side
    countersigns. The gateway, not the agent, writes the run's summary into
    the verifiable store, so the evidence trail does not depend on the
    agent's own honesty. Store failure is named, never silent."""
    import hashlib as _h
    summary = {
        "checkpoint": str(result.get("checkpoint", "")),
        "verified": bool(result.get("verified")),
        "integrity_clean": bool((result.get("integrity") or {}).get("clean")),
        "review_sha256": _h.sha256(json.dumps(
            result.get("review") or {}, sort_keys=True).encode()).hexdigest(),
        "manifest_sha256": _h.sha256(json.dumps(
            result.get("context_manifest") or {},
            sort_keys=True).encode()).hexdigest(),
        "high_risk_edits": len((result.get("risk_review") or {})
                               .get("demands") or []),
    }
    try:
        from harness.store import put_entity
        stored = put_entity("agent-run", summary)
        return {**summary, "stored": stored.get("eid", ""),
                "chain_hash": stored.get("chain_hash", "")}
    except Exception as e:
        return {**summary, "stored": f"store unavailable: {type(e).__name__}"}


def _countersign_workflow(doc: dict) -> dict:
    """The workflow analogue of _countersign_run: the gateway banks the staged
    run's identity into the verifiable store, so a workflow gets the same
    receiving-side witness every other run surface gets, not only a loose
    receipt file. Store failure is named, never silent."""
    summary = {
        "kind": "workflow-run",
        "workflow": str(doc.get("workflow", "")),
        "endpoint": str(doc.get("endpoint", "")),
        "status": str(doc.get("status", "")),
        "chain_hash": str(doc.get("chain_hash", "")),
        "n_steps": len(doc.get("steps") or []),
    }
    try:
        from harness.store import put_entity
        stored = put_entity("workflow-run", summary)
        return {**summary, "stored": stored.get("eid", ""),
                "store_chain_hash": stored.get("chain_hash", "")}
    except Exception as e:
        return {**summary, "stored": f"store unavailable: {type(e).__name__}"}


def _forge(goal: str, **kw) -> dict:
    """Goal -> a verified PRP (context_forge): criterion-bearing spec + validation
    gates + confidence grounded in external-checkability. The studio front door."""
    try:
        from harness.context_forge import forge_prp
    except Exception:
        try:
            from context_forge import forge_prp
        except Exception as e:
            return {"error": f"context_forge unavailable: {e}"}
    try:
        return forge_prp(goal, **kw).to_dict()
    except Exception as e:                    # a malformed goal must not crash the handler
        return {"error": f"forge failed: {e}"}


class _MemoryProofCache:
    """The seat's verified-result cache for the gateway's lifetime: duck-typed
    .get(key)/.put(key, value). ONLY oracle-verified (LOCAL_VERIFIED) answers are
    ever written here (the seat's _maybe_cache gate) -- a consensus or escalate
    result is never cached as if it were verified. In-process by design: nothing
    is persisted to disk without the config-driven store the packaging increment
    introduces (SUPERAPP storage discipline)."""

    def __init__(self):
        self.store: dict = {}

    def get(self, key):
        return self.store.get(key)

    def put(self, key, value):
        self.store[key] = value


# One seat for the gateway's lifetime, so the proof cache and the routing ledger
# ACCUMULATE across requests (the cache-hit falsifier needs a repeated ask to hit).
_COMPANION_SEAT = None


def _companion_task(prompt: str, solution_sig: str = ""):
    """A duck-typed Task the seat/selector consume: they read .task_id/.prompt
    (routing + key) and .max_new_tokens/.system (generation). Content-addressed
    id so the same prompt keys the same cache slot."""
    from types import SimpleNamespace
    tid = hashlib.sha256(f"{prompt}|{solution_sig}".encode()).hexdigest()[:16]
    return SimpleNamespace(task_id=tid, prompt=prompt, max_new_tokens=512, system="")


def get_companion_seat(serve_url: str):
    """Lazily build the gateway's single CompanionSeat over the local 14B (serve).
    No oracle on this generic route: without something to verify against, the seat
    can only reach consensus or escalate -- it never manufactures a PASS. A caller
    with a real oracle uses the seat directly. Graceful: returns None if the seat
    cannot be constructed (the route then reports the reason honestly)."""
    global _COMPANION_SEAT
    if _COMPANION_SEAT is not None: return _COMPANION_SEAT
    try:
        from harness.companion import CompanionSeat
        from harness.proposer import ServeProposer
    except Exception:
        return None
    _COMPANION_SEAT = CompanionSeat(
        ServeProposer(base_url=serve_url), oracle=None, cache=_MemoryProofCache(),
        escalation_endpoint="anthropic", initial_n=4, max_n=16)
    return _COMPANION_SEAT


def companion_answer(seat, prompt: str, solution_sig: str = "") -> dict:
    """Route one task through the seat and shape a JSON response. The frontier tier
    is only NAMED on escalate (escalate_to); it is never called from here -- routing
    to it is the caller's gated action, so a cache hit provably triggers no frontier
    call (SUPERAPP increment-5 falsifier)."""
    res = seat.answer(_companion_task(prompt, solution_sig), solution_sig=solution_sig)
    out = res.to_dict()
    out["text"] = res.text
    out["best_effort_text"] = res.best_effort_text
    out["ledger_len"] = len(seat.ledger)
    return out


# One ledger for the gateway's lifetime so every routed call across every provider
# chains into ONE tamper-evident record: the whole session is a single audit trail.
_ROUTER_LEDGER = None


def _router_ledger():
    global _ROUTER_LEDGER
    if _ROUTER_LEDGER is None:
        try:
            from harness.local_session import SessionLedger
        except Exception:
            try:
                from local_session import SessionLedger
            except Exception:
                return None
        _ROUTER_LEDGER = SessionLedger()
    return _ROUTER_LEDGER


def route_answer(prompt: str, endpoint: str, proposer, *, credential: str = "local-none") -> dict:
    """Send ONE prompt to a chosen provider's proposer and mint a re-checkable
    receipt binding the response to the endpoint and its model_ref. This is the
    universal router other routers are, plus the verify layer they are not: the
    receipt_id recomputes from (request, prompt, model_ref, response), and provider
    provenance rides the receipt. Same call shape for a local model or any hosted
    provider -- one path behind all of them."""
    from harness.messages_api import make_receipt
    out = proposer.generate(prompt, seed=0, temperature=0.0, max_new_tokens=512, system="")
    gen = {"text": out.text, "seed": getattr(out, "seed", 0),
           "prompt_hash": getattr(out, "prompt_hash", "")}
    receipt = make_receipt(
        {"prompt": prompt, "system": "", "max_new_tokens": 512, "temperature": 0.0, "seed": 0},
        gen, out.model_ref)
    return {"schema": "flywheel.route-result/v1", "endpoint": endpoint,
            "model_ref": out.model_ref, "text": out.text, "receipt": receipt,
            "credential": credential, "usage": getattr(out, "usage", None)}


def route_request(prompt: str, endpoint: str, model: str = "") -> tuple[dict, int]:
    """Validate + route a request to a named endpoint. Returns (body, http_code).
    `model` overrides the endpoint's default_model; empty keeps the default.
    Credential PRESENCE gate: an endpoint with no key present is refused honestly
    (never a silent local fallback), and no key value is ever read or returned."""
    return _openai_route.route_request(
        prompt, endpoint, model, unified_roster=_unified_roster,
        router_ledger=_router_ledger, route_answer=route_answer)


# --- OpenAI-compatible surface: /v1/chat/completions + /v1/models ---------------
# Any OpenAI SDK or client can point its base_url at this gateway and route to ANY
# provider by naming it in `model` ("anthropic", "openai:gpt-4o", or a local name),
# getting back a standard ChatCompletion PLUS an `x_receipt` extension OpenAI clients
# ignore. Drop-in compatibility: the same wire protocol existing tools already speak,
# with the verify layer and the receipt riding along.

def _flatten_messages(messages) -> tuple[str, str]:
    """OpenAI messages -> (system, prompt). System turns concatenate. A single user
    turn passes through as the bare prompt (unchanged). A multi-turn conversation is
    rendered as a labelled transcript ending with an open `Assistant:` turn, so the
    model sees the history instead of only the last line. Content may be a string or
    the OpenAI content-parts array. (Structured passthrough to a provider's own chat
    template is a future refinement; the proposer seam is single-prompt today.)"""
    return _openai_route.flatten_messages(messages)


def _resolve_proposer(model: str, serve_url: str, credential_bindings=None):
    """Resolve one local or explicitly credential-bound proposer."""
    return _openai_route.resolve_proposer(
        model, serve_url, credential_bindings,
        unified_roster=_unified_roster, router_ledger=_router_ledger)


def _chat_receipt(prompt, system, max_tokens, temperature, seed, out):
    return _openai_route.chat_receipt(
        prompt, system, max_tokens, temperature, seed, out)


def openai_embeddings(req: dict):
    """POST /v1/embeddings, routed to an embeddings-capable provider named by the
    `model` field ("openai" or "openai:text-embedding-3-small"). Flywheel forwards
    the request with the provider's key (present-only, from the env, never stored or
    logged), so any OpenAI embeddings client works through the same surface. Flywheel
    is zero-dep and computes no embeddings itself; it routes. Returns (body, code)."""
    from harness import providers
    return _openai_route.openai_embeddings(
        req, providers_registry=providers.REGISTRY, urllib_module=urllib,
        resolve_credential=_resolve_credential)


_ROUTER_STATS = None


def get_router_stats():
    """Lazily-loaded persisted router stats (under the run root). Read-only callers
    use snapshot(); the failover path records outcomes when adaptive routing is on."""
    global _ROUTER_STATS
    if _ROUTER_STATS is None:
        from harness.router_stats import RouterStats
        from harness.run_paths import run_root_default
        _ROUTER_STATS = RouterStats(Path(run_root_default()) / "router_stats.json")
    return _ROUTER_STATS


def openai_chat(req: dict, serve_url: str, credential_bindings=None):
    """Return one routed completion plus its receipt and provenance."""
    return _openai_route.openai_chat(
        req, serve_url, credential_bindings,
        flatten_messages=_flatten_messages, resolve_proposer=_resolve_proposer,
        get_router_stats=get_router_stats, chat_receipt=_chat_receipt)


def openai_models() -> dict:
    """GET /v1/models: the roster as OpenAI model objects, so a client's model
    picker lists every provider it can route to. `flywheel` is the verified local seat."""
    return _openai_route.openai_models(unified_roster=_unified_roster)


class _Handler(BaseHTTPRequestHandler):
    root = REPO
    serve_url = "http://127.0.0.1:8765"
    ollama_url = "http://127.0.0.1:11434"
    run_root = run_root_default()

    MAX_BODY = 32 * 1024 * 1024               # 32 MiB ceiling on any request body
    cors = False                              # opt-in (--cors) so browser OpenAI clients can call in
    auth_token = ""                           # set by main(); "" leaves the check off
    allowed_hosts = DEFAULT_HOSTS
    flywheel_home = Path(os.environ.get("FLYWHEEL_HOME", str(Path.home() / ".flywheel")))
    owner_ref, clock = None, staticmethod(
        lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    operation_service = operation_process_factory = None
    session_token_store = _session_token_state_root = None
    def log_message(self, *a):  # quiet
        pass

    def _cors(self):
        """Emit permissive CORS headers only when the operator opted in with --cors.
        Off by default: the gateway binds 127.0.0.1, and enabling CORS lets any web
        page in the browser reach it, so it is a deliberate choice, not a default."""
        if self.cors:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):                     # CORS preflight
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _content_length(self):
        """Parse Content-Length defensively: a non-numeric, negative, or oversized
        value returns None so the caller answers 400 instead of the handler thread
        dying on an uncaught ValueError or reading unbounded bytes into memory."""
        try:
            n = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            return None
        return None if n < 0 or n > self.MAX_BODY else n

    def _json(self, obj, code=200):
        error = obj.get("error") if isinstance(obj, dict) else None
        error_code = error.get("code") if isinstance(error, dict) else None
        if (getattr(self, "_gateway_guarded", False)
                and error_code != "PERMISSION_REQUIRED"
                and (code >= 400 or error_code)):
            from harness.gateway_provider_adapter import fixed_external_failure
            obj, code = fixed_external_failure()
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        if getattr(self, "command", "") != "HEAD": self.wfile.write(body)

    def _operation_components(self):
        state_root = self.flywheel_home / "state"
        service = type(self).operation_service
        if service is None or service.state_root != state_root:
            from harness.gateway_operations import GatewayOperations
            from harness.gateway_operation_process import GatewayAgentProcessFactory
            service = GatewayOperations(state_root, clock=self.clock)
            type(self).operation_service = service
            type(self).operation_process_factory = GatewayAgentProcessFactory(
                repo_root=Path(self.root), run_root=Path(self.run_root))
        return service, type(self).operation_process_factory

    def _session_tokens(self):
        """Lazily build (and rebuild on flywheel_home change) the one
        in-memory SessionTokenStore this process holds. Mints and revokes
        must land in the same store a later request reads, so it cannot be
        recreated per-call the way the (stateless, disk-backed)
        CredentialHandleStore is; mirrors _operation_components so a test
        that repoints flywheel_home doesn't inherit a stale store."""
        state_root = self.flywheel_home / "state"
        cls = type(self)
        if cls.session_token_store is None or cls._session_token_state_root != state_root:
            from harness.credential_handles import CredentialHandleStore
            from harness.keychain import keychain_get
            from harness.session_token import SessionTokenStore
            cls.session_token_store = SessionTokenStore(
                CredentialHandleStore(state_root, keychain_get=keychain_get))
            cls._session_token_state_root = state_root
        return cls.session_token_store

    def _operation_response(self, response):
        if response.stream is None: return self._json(response.body, response.status)
        self.send_response(response.status)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self._cors(); self.end_headers()
        try:
            for chunk in response.stream:
                self.wfile.write(chunk); self.wfile.flush()
        except (BrokenPipeError, ConnectionError, OSError):
            pass

    def _route_operation(self, method):
        path = self.path.split("?", 1)[0]
        is_operation = (path == "/api/agent"
                        or path.startswith("/api/operations/"))
        if not is_operation: return False
        from harness.gateway_operation_route import route_gateway_operation
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        raw, content = b"", ""
        if method == "POST":
            length = self._content_length()
            raw = self.rfile.read(length) if length is not None else b""
            content = (self.headers.get("Content-Type", "") or "").split(
                ";", 1)[0].strip()
        service, factory = self._operation_components()
        response = route_gateway_operation(
            method, path, query=query, content_type=content,
            owner_ref=self.owner_ref, raw=raw, service=service,
            process_factory=factory)
        self._operation_response(response)
        return True

    def _sse_chat(self, req: dict):
        """Stream a completed, receipted answer as OpenAI-compatible SSE."""
        import time
        from harness.scaffold import scaffold_answer, scaffold_turn
        # hash and freeze what the model was ACTUALLY sent (the flattened
        # prompt), not a naive join of raw content that reprs content-parts
        _sys, _prompt = _flatten_messages(req.get("messages", []))
        env = scaffold_turn("\n".join(x for x in (_sys, _prompt) if x))
        bindings = getattr(self, "_gateway_bindings", None)
        body, code, receipt, text, model_ref = (
            openai_chat(req, self.serve_url) if bindings is None else
            openai_chat(req, self.serve_url, bindings))
        if code != 200:
            return self._json(body, code)          # errors are plain JSON, not a stream
        # the answer is produced whole before streaming, so the turn
        # receipt exists before the first chunk leaves (built at emit time
        # below with provenance)
        cid = "chatcmpl-" + receipt["receipt_id"]
        created = int(time.time())
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors()
        self.end_headers()

        def emit(choice, extra=None):
            obj = {"id": cid, "object": "chat.completion.chunk", "created": created,
                   "model": model_ref, "choices": [choice]}
            if extra: obj.update(extra)
            self.wfile.write(("data: " + json.dumps(obj) + "\n\n").encode())
            self.wfile.flush()

        try:
            emit({"index": 0, "delta": {"role": "assistant"}, "finish_reason": None})
            import re
            for piece in (re.findall(r"\S+\s*", str(text)) or [str(text)]):
                emit({"index": 0, "delta": {"content": piece}, "finish_reason": None})
            scaffold_doc = scaffold_answer(
                str(text or ""), env,
                provenance={"endpoint": "v1", "model_ref": str(model_ref)})
            emit({"index": 0, "delta": {}, "finish_reason": "stop"},
                 {"x_receipt": receipt, "x_scaffold": scaffold_doc})
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except Exception:
            pass                                   # client hung up mid-stream; nothing to do

    def _proxy(self, target: str):
        length = self._content_length()
        if length is None:
            return self._json({"error": "invalid or oversized Content-Length"}, 400)
        data = self.rfile.read(length) if length else None
        req = urllib.request.Request(target, data=data, method=self.command,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                body = r.read()
                code = r.status
        except Exception as exc:
            return self._json({"error": f"upstream unreachable: {exc}"}, 502)
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path: str):
        rel = path.lstrip("/") or "site/index.html"
        target = (self.root / rel).resolve()
        # path-traversal guard: must stay inside root
        if self.root.resolve() not in target.parents and target != self.root.resolve(): return self._json({"error": "forbidden"}, 403)
        if target.is_dir(): target = target / "index.html"
        if not target.is_file(): return self._json({"error": "not found"}, 404)
        ctype = {"html": "text/html", "js": "text/javascript", "css": "text/css",
                 "json": "application/json", "svg": "image/svg+xml"}.get(
                     target.suffix.lstrip("."), "application/octet-stream")
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def _safe_500(self, e):
        """Return one non-echoing response for an uncaught handler error."""
        try:
            self._json({"error": {"message": f"internal error: {type(e).__name__}",
                                  "type": "api_error"}}, 500)
        except Exception:
            pass                                   # headers already partly sent; nothing safe to do
    def _req_json(self):
        """Return one admitted or bounded decoded request body."""
        admitted = getattr(self, "_gateway_operation", None)
        if admitted is not None:
            del self._gateway_operation
            return admitted, None
        length = self._content_length()
        if length is None:
            return None, self._json(
                {"error": "invalid or oversized Content-Length"}, 400)
        try:
            return (json.loads(self.rfile.read(length) or b"{}")
                    if length else {}), None
        except Exception:
            return {}, None
    def _authorized(self) -> bool:
        """Refuse before dispatch; public auth-off compatibility stays available,
        while private custody always requires a configured bearer token."""
        path = self.path.split("?", 1)[0]
        private = (path.startswith(("/api/journeys/", "/api/grants/", "/api/plan/",
                                    "/api/gateway-grants/",
                                    "/api/pm/",
                                    "/api/credential-handles",
                                    "/api/session-tokens",
                                    "/api/operations/"))
                   or path in {"/v1/chat/completions", "/api/agent",
                               "/api/workflow", "/api/plugins/probe",
                               "/api/plugins/call", "/api/plugins/register",
                               "/api/plugins/toggle", "/api/plugins/remove",
                               "/api/marketplace/install",
                               "/api/marketplace/add",
                               "/api/marketplace/remove"})
        if not self.auth_token and not private: return True
        if private:
            owner, reason = ((None, "no_token") if not self.auth_token else _auth_owner(
                self.headers, self.command, self.auth_token, self.flywheel_home, allowed_hosts=self.allowed_hosts))
            ok = owner is not None
            if ok: self.owner_ref = owner
        else:
            ok, reason = _auth_check(self.headers, self.command, self.auth_token, allowed_hosts=self.allowed_hosts)
        if ok: return True
        refusal = ({"schema": "flywheel.evidence-transport-error/v1", "error": {
            "code": "AUTH_REQUIRED", "message": "gateway authentication is required"}}
            if private else {"error": "unauthorized", "reason": reason})
        body = json.dumps(refusal).encode()
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return False
    def _gateway_method(self, method, fallback=None):
        if not self._authorized(): return
        try:
            if not self._route_operation(method): (fallback or (lambda: self.send_error(501)))()
        except Exception as e:
            self._safe_500(e)
    def do_GET(self): self._gateway_method("GET", self._get)
    def do_POST(self): self._gateway_method("POST", self._post)
    def do_PUT(self): self._gateway_method("PUT")
    def do_DELETE(self): self._gateway_method("DELETE")
    def do_HEAD(self): self._gateway_method("HEAD")
    def _get(self):
        p = self.path.split("?", 1)[0]
        qs = self.path.split("?", 1)[1] if "?" in self.path else ""
        if p.startswith("/api/hooks"):
            from harness.hooks_route import handle_hooks_get
            body, code = handle_hooks_get(p, run_root=Path(self.run_root))
            return self._json(body, code)
        if p.startswith("/api/subagents"):
            from harness.subagents_route import handle_subagents_get
            body, code = handle_subagents_get(p, qs, run_root=self.run_root)
            return self._json(body, code)
        if p == "/api/skills":
            from harness.skill_route import handle_skills_get
            body, code = handle_skills_get(p, run_root=self.run_root)
            return self._json(body, code)
        if p == "/api/pm/roadmap":
            from harness.pm_roadmap_route import handle_pm_get
            body, code = handle_pm_get(p, run_root=self.run_root,
                clock=self.clock,
                journeys_state_root=self.flywheel_home / "state",
                owner_ref=self.owner_ref)
            return self._json(body, code)
        if p.startswith("/api/packs"):
            from harness.pack_admission_route import handle_pack_get
            body, code = handle_pack_get(p, run_root=self.run_root)
            return self._json(body, code)
        if p == "/api/endpoints/health":
            return self._json(endpoint_roster(self.serve_url, self.ollama_url))
        if p == "/api/endpoints":
            return self._json(_unified_roster())     # full universal-router roster
        if p == "/api/models":                       # one endpoint's model roster
            name = _qs_value(qs, "endpoint")
            if not name:
                return self._json({"error": "provide ?endpoint=NAME"}, 400)
            from harness.model_roster import list_models
            return self._json(list_models(name))
        if p == "/api/world":
            return self._json(_projected_world(self.root))
        if p == "/api/lanes":                        # the lane roster (umbrella layer)
            from harness.lanes import lane_roster
            probe = "probe=true" in qs or "probe=1" in qs
            return self._json(lane_roster(probe=probe))
        if p == "/api/desktop/status":               # read-only connection facts
            from harness.desktop_status import desktop_status
            from harness.lanes import lane_roster
            return self._json(desktop_status(lane_roster()))
        if p == "/api/forum/status":                  # forum lane status (via MCP)
            return self._json(_forum_mcp_call("forum.status", {}))
        if p == "/api/forum/ledger":                  # forum ledger summary
            return self._json(_forum_mcp_call("forum.ledger.summary", {}))
        if p == "/api/forum/gates":                   # pending approval gates
            return self._json(_forum_mcp_call("gate_list", {}))
        if p == "/api/forum/run-room":                # the current run room snapshot
            return self._json(_forum_mcp_call("forum.run.room", {}))
        if p in ("/api/relay/status", "/api/relay/result"):  # a relay run, via the exec lane
            from urllib.parse import parse_qs
            rid = parse_qs(qs).get("run_id", [""])[0]
            tool = "local_agent_status" if p.endswith("status") else "local_agent_result"
            return self._json(_relay_mcp_call(tool, {"run_id": rid}))
        if p == "/api/relay/runs":                     # recent relay runs (survive a restart)
            return self._json(_relay_mcp_call("local_agent_runs", {}))
        if p == "/api/relay/sessions":                 # saved relay sessions (follow you)
            return self._json(_relay_mcp_call("local_agent_sessions", {}))
        if p == "/api/lessons":                       # the organizational learning loop
            from harness.lesson_store import LessonStore
            store = LessonStore.load(Path(self.run_root) / "lessons.jsonl")
            return self._json({
                "n": len(store),
                "improvement_feed": store.improvement_feed(),
                "verify": store.verify(),
            })
        if p == "/api/lessons/patterns":              # recurring patterns for human admission
            from harness.lesson_store import LessonStore
            store = LessonStore.load(Path(self.run_root) / "lessons.jsonl")
            return self._json({"patterns": [p.to_dict() for p in store.patterns()]})
        if p == "/api/governance/tiers":               # TADR tier definitions
            from harness.governance.tadr_tier import TADR_TIERS, TADR_MODIFIERS
            return self._json({
                "tiers": TADR_TIERS,
                "modifiers": sorted(TADR_MODIFIERS),
            })
        if p == "/api/governance/compliance":          # control baseline compliance check
            from harness.governance.control_baseline import check_compliance
            tier = "T1"
            report = check_compliance(tier)
            return self._json(report.to_dict())
        if p == "/api/governance/classify":            # classify a system (GET with query params)
            from harness.governance.tadr_tier import classify
            from urllib.parse import parse_qs
            params = parse_qs(qs) if qs else {}
            overrides = params.get("override", [])
            result = classify(overrides)
            return self._json(result.to_dict())
        if p == "/api/lanes/callable":                # list lanes + their tier requirements
            from harness.lane_caller import list_available_lanes
            return self._json({"lanes": list_available_lanes()})
        if p == "/api/training/status":
            return self._json(_training_status(self.run_root))
        if p == "/api/train/duel":                    # verified-inference duel summary (read-only)
            from harness.train_surface import duel_summary
            return self._json(duel_summary())
        if p == "/api/train/loop":                    # the loop-closure self-audit (on demand)
            from harness.train_surface import loop_status
            try:
                return self._json(loop_status())
            except Exception as e:
                return self._json({"error": f"{type(e).__name__}: {e}"}, 502)
        if p == "/api/loops":                        # which candidate loops close? measured, not drawn
            from harness.loops import measure_all_loops
            return self._json(measure_all_loops())
        if p == "/api/tension":                      # measurement disagreements, kept re-checkable
            from harness.tension_ledger import tension_ledger
            return self._json(tension_ledger())
        if p == "/api/instruments":                  # the evaluation-engineering register
            from harness.eval_engineering import instrument_register
            return self._json(instrument_register())
        if p == "/api/typeface/gallery":             # the marketplace of published faces (metadata)
            from urllib.parse import unquote_plus
            limit = 60
            for part in qs.split("&"):
                if part.startswith("limit="):
                    try:
                        limit = int(unquote_plus(part[6:]))
                    except ValueError:
                        pass
            from harness.typeface_gallery import gallery
            return self._json(gallery(limit=limit))
        if p == "/api/typeface/face":                # one published face, bytes included
            from urllib.parse import unquote_plus
            eid = ""
            for part in qs.split("&"):
                if part.startswith("eid="):
                    eid = unquote_plus(part[4:])
            from harness.typeface_gallery import fetch_face
            out = fetch_face(eid)
            return self._json(out, 404 if "error" in out else 200)
        if p == "/api/academy":                      # the curriculum, derived from the live code
            from harness.academy_pipeline import academy_curriculum
            return self._json(academy_curriculum())
        if p == "/api/frontier":                     # the RAM/compute frontier, measured here
            from harness.frontier import frontier_table
            from harness.store import get_entity, query_entities
            probes = []
            seen = set()
            for meta in query_entities(kind="capability"):
                e = get_entity(meta["eid"])
                if e and isinstance(e.get("data"), dict):
                    ep = e["data"].get("endpoint", "")
                    if ep and ep not in seen:      # newest probe per endpoint
                        seen.add(ep)
                        probes.append(e["data"])
            return self._json(frontier_table(self.root, probes=probes))
        if p == "/api/retention":                    # what is still held, not what was once shown
            from harness.retention import retention_due
            days = 3.0
            for part in qs.split("&"):
                if part.startswith("days="):
                    try:
                        days = max(0.0, float(part[5:]))
                    except ValueError:
                        days = 3.0
            return self._json(retention_due(days=days))
        if p == "/api/comprehension":                # ownership from checked evidence, not blame
            from urllib.parse import unquote_plus
            from harness.comprehension_ledger import comprehension_ledger
            project = None
            for part in qs.split("&"):
                if part.startswith("project="):
                    project = unquote_plus(part[8:]) or None
            return self._json(comprehension_ledger(project=project))
        if p == "/api/readiness":                    # release readiness, measured not felt
            from harness.release_readiness import readiness_report
            return self._json(readiness_report())
        if p == "/api/credo":                        # the belief, content-addressed and retrievable
            from harness.credo import credo_doc
            return self._json(credo_doc())
        if p == "/api/feeds":                        # cross-domain live feeds through gather
            from urllib.parse import unquote_plus
            from harness.live_feeds import live_feeds
            domain = None
            for part in qs.split("&"):
                if part.startswith("domain="):
                    domain = unquote_plus(part[7:]) or None
            return self._json(live_feeds(domain=domain))
        if p == "/api/uplift":                       # bare-vs-wrapped uplift bench (read-only roster)
            from harness.uplift_bench import bench_summary
            return self._json(bench_summary(self.root))
        if p == "/api/graph":                        # cross-surface knowledge graph + context plan
            from urllib.parse import unquote_plus
            from harness.knowledge_graph import gateway_graph
            budget = None
            with_index = False
            query = None
            for part in qs.split("&"):
                if part.startswith("budget="):
                    try:
                        budget = int(part[7:])
                    except ValueError:
                        budget = None
                if part == "index=true":
                    with_index = True
                if part.startswith("q="):
                    query = unquote_plus(part[2:])
            return self._json(gateway_graph(self.root, self.run_root,
                                            with_index=with_index,
                                            budget=budget, query=query))
        if p == "/api/usage":                        # signed usage-metering session summary
            from harness.usage_route import handle_usage_summary
            body, code = handle_usage_summary(qs, self.run_root)
            return self._json(body, code)
        if p == "/api/receipts":                     # the receipts ledger (catalog + envelopes)
            return self._json(receipts_ledger(self.root, self.run_root))
        if p == "/api/receipts/proof":               # prove one receipt is in the log
            from harness.receipt_proof import route_payload
            led = receipts_ledger(self.root, self.run_root)
            leaves = [e["sha256"] for e in led["envelopes"]]
            body, code = route_payload(_qs_value(qs, "leaf").strip(), leaves)
            return self._json(body, code)
        if p == "/api/profiles":                     # profile manifests over the one substrate
            from harness.profiles import profile_roster
            return self._json(profile_roster())
        if p == "/api/workflows":                    # workflow definitions + recent runs
            from harness.workflows import workflow_roster
            return self._json(workflow_roster(self.run_root))
        if p == "/api/workflow/run":                 # one run's stored trace, chain-reverified
            from harness.workflows import workflow_run_detail
            return self._json(workflow_run_detail(
                self.run_root, _qs_value(qs, "chain")))
        if p == "/api/science/runs":                 # eval history, chain-reverified
            from harness.eval_store import science_runs
            return self._json(science_runs(
                self.run_root, limit=_qs_int(qs, "limit", 20)))
        if p == "/api/science/run":                  # one stored science run
            from harness.eval_store import science_run_detail
            return self._json(science_run_detail(
                self.run_root, _qs_value(qs, "chain")))
        if p == "/api/agent/runs":                   # agent-run history, content-addressed
            from harness.eval_store import agent_runs
            return self._json(agent_runs(
                self.run_root, limit=_qs_int(qs, "limit", 20)))
        if p == "/api/agent/run":                    # one stored agent run
            from harness.eval_store import agent_run_detail
            return self._json(agent_run_detail(
                self.run_root, _qs_value(qs, "id")))
        if p == "/api/memory":                       # durable memory stats (fold index)
            from harness.memory_api import memory_stats
            return self._json(memory_stats(self.run_root))
        if p == "/api/memory/list":                  # browse stored spans, verbatim
            from harness.memory_api import memory_list
            limit = 20
            for part in qs.split("&"):
                if part.startswith("limit="):
                    try:
                        limit = int(part[6:])
                    except ValueError:
                        limit = 20
            return self._json(memory_list(self.run_root, limit=limit))
        if p == "/api/plugins":                      # every mounted capability, one manifest shape
            from harness.plugins import plugin_roster
            return self._json(plugin_roster())
        if p == "/api/parity":                       # the capability matrix, witnessed not asserted
            from harness.parity import parity_matrix
            return self._json(parity_matrix())
        if p == "/api/projects":                     # the registered project/directory roster
            from harness.projects import project_roster
            return self._json(project_roster())
        if p == "/api/store":                        # verifiable substrate stats
            from harness.store import stats
            return self._json(stats())
        if p == "/api/store/verify":                 # walk the chain AND re-check the records
            from harness.store import verify_chain, verify_records
            chain = verify_chain()
            records = verify_records()
            return self._json({"schema": "flywheel.store-verify/v1",
                               "ok": bool(chain.get("ok"))
                               and bool(records.get("ok")),
                               "chain": chain, "records": records,
                               "note": "ok requires BOTH the ledger chain "
                                       "and the records it attests; a "
                                       "tampered entity fails records even "
                                       "when the chain still verifies"})
        if p == "/api/store/audit":                  # the hash-chained audit tail
            from harness.store import audit_tail
            n = 50
            for part in qs.split("&"):
                if part.startswith("n="):
                    try:
                        n = int(part[2:])
                    except ValueError:
                        n = 50
            return self._json({"schema": "flywheel.store-audit/v1",
                               "entries": audit_tail(n)})
        if p == "/api/marketplace":                  # curated catalog over the plugin registry
            from harness.marketplace import marketplace_catalog
            return self._json(marketplace_catalog())
        if p == "/api/auth":                         # subscription sign-in roster
            from harness import oauth_service
            return self._json(oauth_service.auth_rows())
        if p == "/api/keychain":                     # credential names + presence, never values
            from harness.keychain import credential_source, keychain_available
            try:
                from harness.endpoints import PROVIDERS
            except Exception:
                PROVIDERS = {}
            names = sorted({s.get("key", "") for s in PROVIDERS.values()
                            if s.get("key")})
            return self._json({
                "schema": "flywheel.keychain/v1",
                "available": keychain_available(),
                "entries": [{"name": n, "source": credential_source(n)}
                            for n in names],
                "note": "presence and source only; values never leave "
                        "resolution inside a routed call"})
        if p == "/api/credential-handles":
            from harness.credential_handle_route import credential_handle_get
            body, code = credential_handle_get(
                p, owner_ref=self.owner_ref,
                state_root=self.flywheel_home / "state")
            return self._json(body, code)
        if p == "/api/session-tokens":
            from harness.session_token_route import session_token_get
            body, code = session_token_get(
                owner_ref=self.owner_ref, token_store=self._session_tokens())
            return self._json(body, code)
        if p == "/api/plugins/probe":                # spawn a plugin's server, report its real tools
            return self._json({"schema": "flywheel.evidence-transport-error/v1",
                "error": {"code": "INVALID_REQUEST",
                          "message": "plugin probe requires POST approval"}}, 405)
        if p == "/api/router/stats":                 # observed per-provider success/cost
            return self._json(get_router_stats().snapshot())
        if p == "/v1/models":                        # OpenAI-compatible model list (the roster)
            return self._json(openai_models())
        if p.startswith("/v1/") or p == "/generate" or p == "/health":
            return self._proxy(self.serve_url.rstrip("/") + p)
        return self._static(p)

    def _plan_request(self, path):
        length = self._content_length()
        if length is None:
            return self._json({"schema": "flywheel.evidence-transport-error/v1",
                "error": {"code": "INVALID_REQUEST",
                          "message": "gateway operation is invalid"}}, 422)
        from harness.plan_run_route import plan_post
        body, code = plan_post(path, self.rfile.read(length), owner_ref=self.owner_ref,
            state_root=self.flywheel_home / "state", default_root=self.root,
            run_root=self.run_root, clock=self.clock,
            resolve_root=_resolve_workspace_root, countersign=_countersign_workflow)
        return self._json(body, code)

    def _post(self):
        p = self.path.split("?", 1)[0]
        if p.startswith("/api/plan/"): return self._plan_request(p)
        if p.startswith("/api/session-tokens/"):
            length = self._content_length()
            if length is None:
                return self._json({"schema": "flywheel.evidence-transport-error/v1",
                    "error": {"code": "INVALID_LENGTH", "message": "request length is invalid"}}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}")
            except Exception:
                req = {}
            action = p.rsplit("/", 1)[-1]
            from harness.session_token_route import session_token_post
            body, code = session_token_post(
                action, req, owner_ref=self.owner_ref,
                token_store=self._session_tokens())
            return self._json(body, code)
        if p.startswith(("/api/evidence/", "/api/journeys/", "/api/grants/",
                         "/api/gateway-grants/", "/api/credential-handles/")):
            length = self._content_length()
            if length is None:
                return self._json({"schema": "flywheel.evidence-transport-error/v1",
                    "error": {"code": "INVALID_LENGTH", "message": "request length is invalid"}}, 400)
            raw = self.rfile.read(length)
            if p.startswith("/api/evidence/"):
                from harness.evidence_route import evidence_post
                body, code = evidence_post(p, raw, root=self.root)
            elif p.startswith("/api/journeys/extensions/"):
                # Contextual extensions: fail-closed. The server-side
                # contract registry is empty, so the sheet has zero rows
                # and every extension denies until contracts are accepted.
                from harness.evidence_extension_route import (
                    handle_capabilities as _caps,
                    handle_domain_pack_project,
                    handle_frontier_axis,
                    handle_frontier_project,
                    handle_incident_propose,
                )
                from harness.evidence_public import parse_json
                from harness.evidence_extension_contracts import (
                    capability_document as _empty_doc)
                length = self._content_length()
                if length is None:
                    return self._json({"schema": "flywheel.evidence-transport-error/v1",
                        "error": {"code": "INVALID_LENGTH", "message": "request length is invalid"}}, 400)
                action = p.rsplit("/", 1)[-1]
                if action == "capabilities":
                    body, code = _caps(_empty_doc(
                        journey={"schema": "flywheel.evidence-journey-projection/v2",
                                 "event_head_sha256": "0" * 64},
                        incident_contract=None, frontier_contract=None,
                        pack_contracts=[], containment={"process": False}))
                else:
                    try:
                        req = parse_json(self.rfile.read(length))
                    except Exception:
                        req = {}
                    empty = _empty_doc(
                        journey={"schema": "flywheel.evidence-journey-projection/v2",
                                 "event_head_sha256": "0" * 64},
                        incident_contract=None, frontier_contract=None,
                        pack_contracts=[], containment={"process": False})
                    if action == "incident-propose":
                        body, code = handle_incident_propose(req, empty)
                    elif action == "frontier-project":
                        body, code = handle_frontier_project(req, empty)
                    elif action == "frontier-axis":
                        body, code = handle_frontier_axis(
                            req, empty, self.clock)
                    elif action == "domain-pack-project":
                        body, code = handle_domain_pack_project(req, empty)
                    else:
                        body, code = {"schema": "flywheel.evidence-transport-error/v1",
                            "error": {"code": "NOT_FOUND",
                                      "message": "unknown extension"}}, 404
                return self._json(body, code)
            elif p.startswith("/api/journeys/"):
                from harness.journey_route import journey_post
                body, code = journey_post(p, raw, owner_ref=self.owner_ref, state_root=self.flywheel_home / "state",
                    evidence_root=self.flywheel_home / "state" / "artifacts", clock=self.clock)
            elif p.startswith("/api/grants/"):
                from harness.grant_route import grant_post
                body, code = grant_post(p, raw, owner_ref=self.owner_ref, state_root=self.flywheel_home / "state",
                    evidence_root=self.flywheel_home / "state" / "artifacts", clock=self.clock)
            elif p.startswith("/api/gateway-grants/"):
                from harness.gateway_grant_route import gateway_grant_post
                body, code = gateway_grant_post(
                    p, raw, owner_ref=self.owner_ref,
                    state_root=self.flywheel_home / "state", clock=self.clock)
            else:
                from harness.credential_handle_route import credential_handle_post
                body, code = credential_handle_post(
                    p, raw, owner_ref=self.owner_ref,
                    state_root=self.flywheel_home / "state")
            return self._json(body, code)
        from harness.gateway_operation import action_for_path, materialize_agent_attachment, thaw_operation
        if p.startswith("/api/hooks/"):
            from harness.evidence_public import parse_json
            from harness.hooks_route import handle_hooks_post
            length = self._content_length()
            if length is None:
                return self._json({"schema": "flywheel.evidence-transport-error/v1",
                    "error": {"code": "INVALID_LENGTH", "message": "request length is invalid"}}, 400)
            try:
                req = parse_json(self.rfile.read(length))
            except Exception:
                req = {}
            body, code = handle_hooks_post(
                p, req, run_root=self.run_root,
                owner_ref=self.owner_ref, clock=self.clock)
            return self._json(body, code)
        if p.startswith("/api/subagents/"):
            from harness.evidence_public import parse_json
            from harness.subagents_route import handle_subagents_post
            length = self._content_length()
            if length is None:
                return self._json({"schema": "flywheel.evidence-transport-error/v1",
                    "error": {"code": "INVALID_LENGTH", "message": "request length is invalid"}}, 400)
            try:
                req = parse_json(self.rfile.read(length))
            except Exception:
                req = {}
            body, code = handle_subagents_post(
                p, req, run_root=self.run_root, clock=self.clock)
            return self._json(body, code)
        if p.startswith("/api/skills/"):
            from harness.evidence_public import parse_json
            from harness.skill_route import handle_skills_post
            length = self._content_length()
            if length is None:
                return self._json({"schema": "flywheel.evidence-transport-error/v1",
                    "error": {"code": "INVALID_LENGTH", "message": "request length is invalid"}}, 400)
            try:
                req = parse_json(self.rfile.read(length))
            except Exception:
                req = {}
            body, code = handle_skills_post(
                p, req, run_root=self.run_root, clock=self.clock)
            return self._json(body, code)
        action = action_for_path(p)
        if action is not None:
            length = self._content_length()
            if length is None:
                return self._json({"schema": "flywheel.evidence-transport-error/v1",
                    "error": {"code": "INVALID_REQUEST",
                              "message": "gateway operation is invalid"}}, 422)
            from harness.gateway_grant_route import (
                authorize_gateway_operation, gateway_error_response)
            try:
                authorized = authorize_gateway_operation(
                    action, self.rfile.read(length), owner_ref=self.owner_ref,
                    state_root=self.flywheel_home / "state", clock=self.clock)
                from harness.gateway_provider_adapter import resolve_credentials
                authorized = resolve_credentials(
                    authorized, self.flywheel_home / "state")
                self._gateway_guarded = True
            except Exception as exc:
                body, code = gateway_error_response(exc)
                return self._json(body, code)
            from harness.gateway_actions import dispatch_builtin
            try:
                dispatched = dispatch_builtin(authorized)
            except Exception as exc:
                body, code = gateway_error_response(exc)
                return self._json(body, code)
            if dispatched is not None:
                return self._json(*dispatched)
            self._gateway_operation = materialize_agent_attachment(thaw_operation(authorized.operation))
            self._gateway_bindings = authorized.credential_bindings
        if p == "/v1/chat/completions":              # OpenAI-compatible, routes to ANY provider
            req, bad = self._req_json()
            if bad: return bad
            if req.get("stream"):
                return self._sse_chat(req)
            from harness.scaffold import scaffold_answer, scaffold_turn
            # hash and freeze the flattened prompt the model was actually
            # sent, so the turn receipt is reproducible by a stranger
            _sys, _prompt = _flatten_messages(req.get("messages", []))
            env = scaffold_turn("\n".join(x for x in (_sys, _prompt) if x))
            bindings = getattr(self, "_gateway_bindings", None)
            body, code, _r, _t, _m = (
                openai_chat(req, self.serve_url) if bindings is None else
                openai_chat(req, self.serve_url, bindings))
            if code == 200 and isinstance(body, dict):
                try:
                    content = body["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError):
                    content = ""
                # extension field: OpenAI clients ignore unknown keys
                body["flywheel_scaffold"] = scaffold_answer(
                    str(content or ""), env,
                    provenance={"endpoint": "v1",
                                "model_ref": str(body.get("model") or "")})
            return self._json(body, code)
        if p == "/api/bench/run":                    # private verified benchmark
            from harness.endpoints import build_endpoints
            from harness.verified_bench_route import handle_bench_run
            req, bad = self._req_json()
            if bad:
                return bad
            body, code = handle_bench_run(
                req, run_root=Path(self.run_root),
                build_endpoints=build_endpoints)
            return self._json(body, code)
        if p == "/api/packs/admit":                  # admit a domain pack
            from harness.pack_admission_route import handle_pack_post
            req, bad = self._req_json()
            if bad:
                return bad
            body, code = handle_pack_post(p, req, run_root=self.run_root,
                                          clock=self.clock)
            return self._json(body, code)
        if p == "/v1/embeddings":                    # OpenAI-compatible, routed to a provider
            length = self._content_length()
            if length is None:
                return self._json({"error": {"message": "invalid or oversized Content-Length",
                                             "type": "invalid_request_error"}}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            body, code = openai_embeddings(req)
            return self._json(body, code)
        if p.startswith("/v1/") or p == "/generate":
            return self._proxy(self.serve_url.rstrip("/") + p)
        if p == "/api/relay/start":                  # start a witnessed relay run via the exec lane
            req, bad = self._req_json()
            if bad:
                return bad
            return self._json(_relay_mcp_call("local_agent_start", req))
        if p == "/api/forge":                        # goal -> verified PRP (the studio)
            req, bad = self._req_json()
            if bad:
                return bad
            goal = (req.get("goal") or "").strip()
            if not goal:
                return self._json({"error": "provide a non-empty 'goal'"}, 400)
            doc = _forge(
                goal, examples=req.get("examples"),
                documentation=req.get("documentation"),
                context=req.get("context", ""),
                intent_source=str(req.get("intent_source", "")),
                architecture_source=str(req.get("architecture_source", "")))
            if "error" not in doc:
                # seal the Y-chain server-side so the later drift recheck
                # never trusts the checked party for the sealed half
                doc["prp_id"] = persist_forge_seal(
                    self.run_root, goal,
                    intent_sha256=str(doc.get("intent_sha256", "")),
                    architecture_sha256=str(doc.get("architecture_sha256", "")))
            return self._json(doc)
        if p == "/api/academy/complete":             # bind a passed receipt to a lesson
            req, bad = self._req_json()
            if bad:
                return bad
            lesson_id = str(req.get("lesson_id", "")).strip()
            eid = str(req.get("comprehension_eid", "")).strip()
            if not lesson_id or not eid:
                return self._json({"error": "provide 'lesson_id' and "
                                            "'comprehension_eid'"}, 400)
            from harness.academy_pipeline import academy_complete
            doc = academy_complete(lesson_id, eid)
            return self._json(doc, 200 if doc.get("bound") else 400)
        if p == "/api/forge/recheck":                # did an arm drift since the forge?
            req, bad = self._req_json()
            if bad:
                return bad
            if req.get("intent_sha256") or req.get("architecture_sha256"):
                return self._json(
                    {"error": "caller-supplied sealed hashes are refused: "
                              "the checked party must not author its own "
                              "criterion. Provide 'prp_id' from the forge "
                              "response; the seal is read server-side"}, 400)
            out = forge_recheck(self.run_root, req.get("prp_id", ""), req)
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/science":                       # evidence -> spec -> witnessed judgment, one chain
            req, bad = self._req_json()
            if bad:
                return bad
            question = (req.get("question") or "").strip()
            if not question:
                return self._json({"error": "provide a non-empty 'question'"}, 400)
            from harness.science_bench import science_run
            try:
                max_sources = max(1, min(int(req.get("max_sources", 4)), 10))
            except (TypeError, ValueError):
                max_sources = 4
            claims = req.get("claims") if isinstance(req.get("claims"), list) else None
            measurements = (req.get("measurements")
                            if isinstance(req.get("measurements"), list) else None)
            from pathlib import Path as _P
            doc = science_run(
                question, claims=claims, measurements=measurements,
                max_sources=max_sources,
                workdir=_P(self.run_root) / "science")
            # history is best-effort: a full disk never blocks the answer,
            # but an unpersisted run says so instead of pretending
            try:
                from harness.eval_store import save_science_run
                doc["receipt_path"] = save_science_run(
                    self.run_root, doc)["receipt_path"]
            except Exception as e:
                doc["receipt_note"] = (
                    f"run not persisted: {type(e).__name__}: {e}")
            return self._json(doc)
        if p == "/api/retrieve":                      # retrieval that cites its evidence
            req, bad = self._req_json()
            if bad:
                return bad
            query = (req.get("query") or "").strip()
            if not query:
                return self._json({"error": "provide a non-empty 'query'"}, 400)
            root, err = _resolve_workspace_root(req.get("root"), self.root)
            if err:
                return self._json({"error": err}, 400)
            try:
                k = max(1, min(int(req.get("k", 8)), 50))
            except (TypeError, ValueError):
                k = 8
            from harness.bm25_retrieval import build_index, search
            index = build_index(root)
            return self._json({"schema": "flywheel.retrieval/v1",
                               "query": query,
                               "hits": search(index, query, k=k),
                               "indexed_files": index["files"],
                               "skipped": index["skipped"]})
        if p == "/api/snapshot":                      # the citation, frozen: bytes as the receipt
            req, bad = self._req_json()
            if bad:
                return bad
            url = (req.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                return self._json({"error": "provide an http(s) 'url'"}, 400)
            from pathlib import Path as _P
            from harness.web_snapshot import snapshot_url
            doc = snapshot_url(url, _P(self.run_root) / "snapshots")
            if "error" not in doc:
                try:
                    from harness.store import put_entity
                    doc["stored"] = put_entity("web-snapshot", doc).get("eid", "")
                except Exception as e:
                    doc["stored"] = f"store unavailable: {type(e).__name__}"
            return self._json(doc)
        if p == "/api/import":                        # arrive with your whole setup, keep the proof
            req, bad = self._req_json()
            if bad:
                return bad
            root, err = _resolve_workspace_root(req.get("root"), self.root)
            if err:
                return self._json({"error": err}, 400)
            from harness.import_adapters import import_config
            doc = import_config(root)
            try:
                from harness.store import put_entity
                doc["stored"] = put_entity("import-manifest", doc).get("eid", "")
            except Exception as e:
                doc["stored"] = f"store unavailable: {type(e).__name__}"
            return self._json(doc)
        if p == "/api/lean":                          # the apex oracle: the kernel decides
            req, bad = self._req_json()
            if bad:
                return bad
            code = req.get("code") or ""
            if not code.strip():
                return self._json({"error": "provide non-empty 'code'"}, 400)
            from harness.lean_oracle import lean_check
            doc = lean_check(code)
            try:
                from harness.store import put_entity
                doc["stored"] = put_entity("lean", doc).get("eid", "")
            except Exception as e:
                doc["stored"] = f"store unavailable: {type(e).__name__}"
            return self._json(doc)
        if p == "/api/invent":                        # generation under witness: propose, judge, keep
            req, bad = self._req_json()
            if bad:
                return bad
            k = req.get("k", 12)
            if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= 50:
                return self._json({"error": "provide integer 'k' in 1..50"}, 400)
            offset = req.get("offset", 0)
            if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
                return self._json({"error": "'offset' must be a non-negative integer"}, 400)
            from harness.conjecture_forge import forge_round
            return self._json(forge_round(k, offset=offset))
        if p == "/api/scaffold":                      # the full turn guarantee for external wrappers
            req, bad = self._req_json()
            if bad:
                return bad
            prompt = str(req.get("prompt") or "")
            answer = str(req.get("answer") or "")
            if not prompt and not answer:
                return self._json({"error": "provide 'prompt' and/or 'answer'"}, 400)
            from harness.scaffold import scaffold_answer, scaffold_turn
            env = scaffold_turn(prompt)
            cites = req.get("citations")
            doc = scaffold_answer(answer, env,
                                  citations=cites if isinstance(cites, list)
                                  else None)
            return self._json(doc)
        if p == "/api/suite":                         # can this acceptance suite refuse wrong code?
            req, bad = self._req_json()
            if bad:
                return bad
            path = (req.get("path") or "").strip()
            if not path:
                return self._json({"error": "provide a project 'path'"}, 400)
            mm = req.get("max_mutants", 5)
            if not isinstance(mm, int) or isinstance(mm, bool) or not 1 <= mm <= 20:
                return self._json({"error": "'max_mutants' must be an integer in 1..20"}, 400)
            from harness.suite_audit import audit_suite
            doc = audit_suite(path, oracle_cmd=str(
                req.get("oracle_cmd", "python -m pytest tests/ -q")),
                max_mutants=mm)
            return self._json(doc, 400 if "error" in doc else 200)
        if p == "/api/tension":                       # bank a measurement pair with frozen sources
            req, bad = self._req_json()
            if bad:
                return bad
            if not isinstance(req.get("a"), dict) or not isinstance(req.get("b"), dict):
                return self._json({"error": "provide measurement objects 'a' and 'b'"}, 400)
            from harness.tension_ledger import bank_tension
            doc = bank_tension(req["a"], req["b"])
            return self._json(doc, 400 if "error" in doc else 200)
        if p == "/api/capability":                    # probe a model on THIS machine
            req, bad = self._req_json()
            if bad:
                return bad
            endpoint = (req.get("endpoint") or "").strip()
            if not endpoint:
                return self._json({"error": "provide a non-empty 'endpoint'"}, 400)
            from harness.frontier import capability_probe
            doc = capability_probe(endpoint)
            if "error" not in doc:
                if isinstance(req.get("disk_gb"), (int, float)):
                    doc["disk_gb"] = float(req["disk_gb"])
                    doc["disk_gb_source"] = "declared by caller"
                try:
                    from harness.store import put_entity
                    doc["stored"] = put_entity("capability", doc).get("eid", "")
                except Exception as e:
                    doc["stored"] = f"store unavailable: {type(e).__name__}"
            return self._json(doc)
        if p == "/api/retention":                     # bank an unaided retest outcome, linked
            req, bad = self._req_json()
            if bad:
                return bad
            original = (req.get("original") or "").strip()
            if not original or not isinstance(req.get("passed"), bool):
                return self._json({"error": "provide 'original' (entity id) "
                                            "and boolean 'passed'"}, 400)
            from harness.retention import retention_record
            return self._json(retention_record(
                original, req["passed"], note=str(req.get("note", ""))))
        if p == "/api/explain":                       # the teach-back as a receipt (engagement, mechanical)
            req, bad = self._req_json()
            if bad:
                return bad
            diff = req.get("diff") or ""
            explanation = req.get("explanation") or ""
            if not diff.strip() or not explanation.strip():
                return self._json({"error": "provide 'diff' and 'explanation'"}, 400)
            from harness.explanation_gate import explanation_receipt
            try:
                threshold = min(1.0, max(0.1, float(req.get("threshold", 0.6))))
            except (TypeError, ValueError):
                threshold = 0.6
            doc = explanation_receipt(diff, explanation, threshold=threshold,
                                      reviewer=str(req.get("reviewer", "")))
            try:
                from harness.store import put_entity
                doc["stored"] = put_entity("comprehension", doc).get("eid", "")
            except Exception as e:
                doc["stored"] = f"store unavailable: {type(e).__name__}"
            return self._json(doc)
        if p == "/api/attest":                        # ownership made checkable: sign-off bound to the walk
            req, bad = self._req_json()
            if bad:
                return bad
            run_eid = (req.get("run_eid") or "").strip()
            review = req.get("review") if isinstance(req.get("review"), dict) else None
            files = req.get("reviewed_files")
            if not run_eid or review is None or not isinstance(files, list):
                return self._json({"error": "provide 'run_eid' (a banked "
                                            "agent-run entity), 'review' (the "
                                            "run's review doc, verified "
                                            "against the banked hash), and "
                                            "'reviewed_files' (a list); an "
                                            "inline run doc is not accepted "
                                            "because an attestation binds to "
                                            "a run that actually happened"}, 400)
            from harness.attestation import attest_banked
            doc = attest_banked(run_eid, review, files,
                                note=str(req.get("note", "")),
                                reviewer=str(req.get("reviewer", "")))
            if "error" in doc:
                return self._json(doc, 409)
            try:
                from harness.store import put_entity
                stored = put_entity("attestation", doc,
                                    project=str(req.get("project", "")))
                doc["stored"] = stored.get("eid", "")
                doc["store_chain_hash"] = stored.get("chain_hash", "")
            except Exception as e:                    # storing must not void the attestation
                doc["stored"] = f"store unavailable: {type(e).__name__}"
            return self._json(doc)
        if p == "/api/route":                         # universal router: send to ANY provider, with a receipt
            req, bad = self._req_json()
            if bad:
                return bad
            prompt = (req.get("prompt") or "").strip()
            endpoint = (req.get("endpoint") or "").strip()
            if not prompt or not endpoint:
                return self._json({"error": "provide non-empty 'prompt' and 'endpoint'"}, 400)
            model = req.get("model") or ""
            if not isinstance(model, str) or len(model.strip()) > 200:
                return self._json({"error": "'model' must be a string of "
                                            "at most 200 characters"}, 400)
            # the organs fire on every message: pre-pass freezes named
            # sources, post-pass chains the turn receipt (scaffold.py)
            from harness.scaffold import scaffold_answer, scaffold_turn
            env = scaffold_turn(prompt)
            body, code = route_request(prompt, endpoint, model=model.strip())
            if code == 200 and isinstance(body, dict):
                body["scaffold"] = scaffold_answer(
                    str(body.get("text", "")), env,
                    provenance={"endpoint": endpoint,
                                "model_ref": str(body.get("model_ref")
                                                 or endpoint)})
                # meter the spend: a signed usage receipt chained onto the route
                # receipt, from the provider's reported tokens (else a labeled
                # estimate). Never raises -- metering cannot break the answer.
                from harness.usage_route import emit_route_usage
                body["usage_receipt_file"] = emit_route_usage(
                    body, getattr(self, "run_root", None), prompt)
            return self._json(body, code)
        if p == "/api/companion":                     # the seat: answer local, escalate the hard slice
            req, bad = self._req_json()
            if bad:
                return bad
            prompt = (req.get("prompt") or "").strip()
            if not prompt:
                return self._json({"error": "provide a non-empty 'prompt'"}, 400)
            seat = get_companion_seat(self.serve_url)
            if seat is None:
                return self._json({"error": "companion seat unavailable"}, 503)
            from harness.scaffold import scaffold_answer, scaffold_turn
            env = scaffold_turn(prompt)
            body = companion_answer(seat, prompt, req.get("solution_sig", ""))
            body["scaffold"] = scaffold_answer(
                str(body.get("text", "")), env,
                provenance={"endpoint": "companion",
                            "model_ref": str(body.get("model_ref")
                                             or body.get("source") or "")})
            return self._json(body)
        if p == "/api/agent":                          # the agentic tool loop over ANY provider
            req, bad = self._req_json()
            if bad:
                return bad
            goal = (req.get("goal") or "").strip()
            endpoint = (req.get("endpoint") or "").strip()
            if not goal or not endpoint:
                return self._json({"error": "provide non-empty 'goal' and 'endpoint'"}, 400)
            if req.get("stream"):
                return self._sse_agent(req, goal, endpoint)
            effort = None
            if req.get("effort"):
                from harness.effort import resolve_effort
                effort = resolve_effort(str(req["effort"]))
            try:
                max_steps = max(1, min(int(req.get("max_steps",
                                            (effort or {}).get("max_steps", 6))), 12))
            except (TypeError, ValueError):
                max_steps = 6
            root, err = _resolve_workspace_root(req.get("root"), self.root)
            if err:
                return self._json({"error": err}, 400)
            # freeze the goal's named sources BEFORE the agent runs, so the
            # pre-pass is a pre-pass (not an after-the-fact re-freeze)
            from harness.scaffold import scaffold_answer as _sa, \
                scaffold_turn as _st
            env = _st(goal)
            from harness.router_agent import run_router_agent
            events: list = []
            try:
                result = run_router_agent(
                    goal, endpoint, root=str(root),
                    allow_write=bool(req.get("allow_write", False)),
                    allow_exec=bool(req.get("allow_exec", False)),
                    max_steps=max_steps, test_cmd=(req.get("test_cmd") or None),
                    model=(req.get("model") or None),
                    compact_budget=int(req.get("compact_budget", 0) or 0),
                    credential_bindings=getattr(
                        self, "_gateway_bindings", None),
                    on_event=events.append)
            except Exception:
                # failed runs land in history too, with their partial trace
                try:
                    from harness.eval_store import save_agent_run, trim_events
                    save_agent_run(
                        self.run_root,
                        {"goal_excerpt": goal[:200], "endpoint": endpoint,
                         "status": "ERROR",
                         "error": "authorized external action failed",
                         "events": trim_events(events)})
                except Exception:
                    pass  # the 502 already carries the primary error
                return self._json({"error": "authorized external action failed"}, 502)
            if effort is not None:
                # stamp what was ENFORCED, not the nominal dial: a caller
                # max_steps override past the dial, and this route not fanning
                # out n_candidates, must show in the receipt
                from harness.effort import stamp_applied
                result["effort"] = stamp_applied(effort, max_steps_applied=max_steps,
                                                 n_candidates_applied=False)
            result["scaffold"] = _sa(
                str(result.get("final") or ""), env,
                provenance={"endpoint": endpoint,
                            "model_ref": str(req.get("model") or endpoint)})
            result["run_receipt"] = _countersign_run(result)
            try:
                from harness.eval_store import save_agent_run, trim_events
                result["run_id"] = save_agent_run(
                    self.run_root,
                    dict(result, goal_excerpt=goal[:200],
                         events=trim_events(events)))["run_id"]
            except Exception:
                result["receipt_note"] = "authorized external action failed"
            return self._json(result)
        if p == "/api/workflow":                       # staged run with a chained receipt, any endpoint
            req, bad = self._req_json()
            if bad:
                return bad
            goal = (req.get("goal") or "").strip()
            workflow = (req.get("workflow") or "").strip()
            if not goal or not workflow:
                return self._json({"error": "provide 'workflow' and a non-empty 'goal'"}, 400)
            from harness.profiles import get_profile
            from harness.workflows import run_workflow
            profile = get_profile((req.get("profile") or "").strip()) or {}
            root, err = _resolve_workspace_root(req.get("root"), self.root)
            if err:
                return self._json({"error": err}, 400)
            try:
                doc = run_workflow(
                    workflow, goal, (req.get("endpoint") or "serve").strip(),
                    root=str(root),
                    allow_write=bool(req.get("allow_write", False)),
                    allow_exec=bool(req.get("allow_exec", False)),
                    allow_mcp=bool(req.get("allow_mcp", False)),
                    test_cmd=(req.get("test_cmd") or None),
                    system=profile.get("system", ""),
                    run_root=self.run_root,
                    credential_bindings=getattr(
                        self, "_gateway_bindings", None), authorized=True)
            except Exception as e:
                return self._json({"error": f"workflow failed: {type(e).__name__}: {e}"}, 502)
            doc["run_countersign"] = _countersign_workflow(doc)
            return self._json(doc)
        if p == "/api/memory/recall":                  # verbatim recall from the fold index
            req, bad = self._req_json()
            if bad:
                return bad
            query = (req.get("query") or "").strip()
            if not query:
                return self._json({"error": "provide a non-empty 'query'"}, 400)
            from harness.memory_api import memory_recall
            return self._json(memory_recall(self.run_root, query,
                                            req.get("top_k", 5)))
        if p in ("/api/auth/login", "/api/auth/token", "/api/auth/logout"):
            # Subscription sign-in. A browser flow runs in the background and
            # the surface polls /api/auth; a guided flow returns its steps and
            # the surface posts the paste back to /api/auth/token. No token
            # value is logged, echoed, or returned.
            req, bad = self._req_json()
            if bad:
                return bad
            from harness import oauth_service
            provider = (req.get("provider") or "").strip()
            if p == "/api/auth/login":
                # A remote client (a paired phone) sends the engine address it
                # reached as callback_base, so the browser flow can return a
                # callback the phone can deliver to. A local client omits it
                # and the flow stays on loopback.
                out = oauth_service.begin(
                    provider, callback_base=(req.get("callback_base") or None))
            elif p == "/api/auth/token":
                out = oauth_service.submit(provider, req.get("token") or "")
            else:
                out = oauth_service.sign_out(provider)
            return self._json(out, 200 if out.get("ok") else 400)
        if p == "/api/keychain/set":                   # store a secret in the OS keychain
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.keychain import keychain_set
            out = keychain_set((req.get("name") or "").strip(),
                               req.get("value") or "")
            # The secret is now only in the OS store; nothing here logs or
            # echoes it, and `req` goes out of scope with this request.
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/keychain/delete":                # remove a stored secret
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.keychain import keychain_delete
            out = keychain_delete((req.get("name") or "").strip())
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/store/entity":                   # store a content-addressed entity
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.store import put_entity
            out = put_entity((req.get("kind") or "").strip(),
                             req.get("data") or {},
                             project=(req.get("project") or "").strip())
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/store/query":                    # query entities by kind/project
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.store import query_entities
            rows = query_entities(kind=(req.get("kind") or None),
                                  project=(req.get("project") or None),
                                  limit=int(req.get("limit", 200) or 200))
            return self._json({"schema": "flywheel.store-query/v1",
                               "entities": rows, "n": len(rows)})
        if p == "/api/projects/add":                   # register a project directory
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.projects import add_project
            out = add_project((req.get("root") or "").strip(),
                              (req.get("name") or "").strip())
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/projects/remove":                # unregister a project directory
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.projects import remove_project
            out = remove_project((req.get("root") or "").strip())
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/lint":                           # native receipt-carrying linter over a project
            req, bad = self._req_json()
            if bad:
                return bad
            root, err = _resolve_workspace_root(req.get("root"), self.root)
            if err:
                return self._json({"error": err}, 400)
            from harness.linter import lint_project
            paths = req.get("paths") if isinstance(req.get("paths"), list) else None
            out = lint_project(str(root), paths)
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/index":                          # drive the index engine over a project root
            req, bad = self._req_json()
            if bad:
                return bad
            root, err = _resolve_workspace_root(req.get("root"), self.root)
            if err:
                return self._json({"error": err}, 400)
            view = (req.get("view") or "summary").strip()
            if view == "summary":
                from harness.index_bridge import index_summary
                return self._json(index_summary(str(root)))
            from harness.index_bridge import index_view
            out = index_view(str(root), view)
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/discourse":                      # drive the chorus satellite over a gathered corpus
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.chorus_bridge import discourse_digest
            out = discourse_digest((req.get("corpus") or "").strip())
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/discourse/corpora":              # discover gather corpora as discourse sources
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.chorus_bridge import list_corpora
            out = list_corpora((req.get("root") or "").strip())
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/learn/animate":                  # a lesson -> a runnable manim scene (academy)
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.manim_lesson import lesson_to_manim, scene_name, manimgl_available
            lesson = req.get("lesson") if isinstance(req.get("lesson"), dict) else {}
            return self._json({"schema": "flywheel.learn-animation/v1",
                               "scene": scene_name(lesson),
                               "source": lesson_to_manim(lesson),
                               "renderable": manimgl_available()})
        if p == "/api/discourse/digests":              # what the chorus daemon has synthesized
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.chorus_bridge import recent_digests
            limit = req.get("limit")
            out = recent_digests((req.get("store") or "").strip(),
                                 limit=int(limit) if isinstance(limit, int) else 20)
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/robustness/inject":              # measure the gated tool loop's injection containment
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.injection_probe import probe
            return self._json(probe(allow_write=bool(req.get("allow_write")),
                                    allow_exec=bool(req.get("allow_exec"))))
        if p in ("/api/typeface", "/api/typeface/publish",
                 "/api/typeface/family", "/api/typeface/variable"):
            # mint / publish / family / variable, one module (typeface_route.py)
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.typeface_route import typeface_post
            body, code = typeface_post(p, req)
            return self._json(body, code)
        if p == "/api/studio/poster":                  # plate + minted face + copy, one receipt
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.design_studio import compose
            try:
                seed = int(req.get("seed", 58))
            except (TypeError, ValueError):
                seed = 58
            try:
                density = float(req.get("density", 1.0))
            except (TypeError, ValueError):
                density = 1.0
            out = compose(
                str(req.get("title", "")),
                subtitle=str(req.get("subtitle", "")),
                fmt=str(req.get("format", "poster")),
                seed=seed,
                ground=str(req.get("ground", "dark")),
                accent=bool(req.get("accent", True)),
                face_params=req.get("face_params")
                if isinstance(req.get("face_params"), dict) else None,
                orb=str(req.get("orb", "auto")),
                density=density,
                want_svg=bool(req.get("svg")),
                want_pdf=bool(req.get("pdf")))
            return self._json(out, 400 if out.get("refused") else 200)
        if p == "/api/lanes/install":                  # one lane, installed on request
            req, bad = self._req_json()
            if bad:
                return bad
            name = str(req.get("name", "")).strip()
            if not name:
                return self._json({"error": "provide a lane 'name'"}, 400)
            profile = str(req.get("profile", "package")).strip() or "package"
            from harness.lanes import install_lane
            return self._json(install_lane(name, profile=profile))
        if p == "/api/telos/kernel":                   # run a bridged telos creative kernel
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.telos_kernels import run_kernel
            out = run_kernel(str(req.get("kernel", "")).strip(),
                             req.get("args")
                             if isinstance(req.get("args"), dict) else {})
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/studio/graph":                   # branching creative DAG, Merkle receipt
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.creative_graph import run_graph
            out = run_graph(req.get("nodes")
                            if isinstance(req.get("nodes"), list) else [],
                            req.get("edges")
                            if isinstance(req.get("edges"), list) else [])
            return self._json(out, 400 if out.get("refused") else 200)
        if p == "/api/studio/pipeline":                # ordered stages, one chained receipt
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.creative_pipeline import run_pipeline
            out = run_pipeline(req.get("stages")
                               if isinstance(req.get("stages"), list) else [])
            return self._json(out, 400 if out.get("refused") else 200)
        if p == "/api/telos/raster":                   # dither / pixel-sort over a plate or PNG
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.raster_fx import apply_fx
            out = apply_fx(str(req.get("kernel", "")).strip(),
                           req.get("source")
                           if isinstance(req.get("source"), dict) else None,
                           req.get("args")
                           if isinstance(req.get("args"), dict) else None)
            return self._json(out, 400 if out.get("refused") else 200)
        if p == "/api/studio/brandkit":                # one seed + a name -> a whole identity
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.brand_kit import mint_kit
            try:
                seed = int(req.get("seed", 58))
            except (TypeError, ValueError):
                seed = 58
            out = mint_kit(str(req.get("name", "")), seed=seed,
                           tagline=str(req.get("tagline", "")),
                           face_params=req.get("face_params")
                           if isinstance(req.get("face_params"), dict) else None)
            return self._json(out, 400 if out.get("refused") else 200)
        if p == "/api/studio/sound":                   # the seeded chime study, score = receipt
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.sound_studio import compose_sound
            def _num(key, default):
                try:
                    return float(req.get(key, default))
                except (TypeError, ValueError):
                    return default
            out = compose_sound(seed=int(_num("seed", 58)),
                                duration=_num("duration", 24.0),
                                root=_num("root", 220.0))
            return self._json(out, 400 if out.get("refused") else 200)
        if p == "/api/lsp":                            # editor intelligence over any LSP server
            req, bad = self._req_json()
            if bad:
                return bad
            root, err = _resolve_workspace_root(req.get("root"), self.root)
            if err:
                return self._json({"error": err}, 400)
            method = (req.get("method") or "definition").strip()
            if method == "diagnostics":
                from harness.lsp_diagnostics import lsp_diagnostics
                out = lsp_diagnostics(
                    req.get("command", []), str(root),
                    (req.get("file") or "").strip(), req.get("text") or "",
                    (req.get("language_id") or "plaintext").strip())
            else:
                from harness.lsp_bridge import lsp_query
                out = lsp_query(
                    req.get("command", []), str(root),
                    (req.get("file") or "").strip(), req.get("text") or "",
                    (req.get("language_id") or "plaintext").strip(),
                    method,
                    int(req.get("line", 0) or 0),
                    int(req.get("character", 0) or 0))
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/memory/note":                    # durable content-addressed note
            req, bad = self._req_json()
            if bad:
                return bad
            content = (req.get("content") or "").strip()
            if not content:
                return self._json({"error": "provide non-empty 'content'"}, 400)
            from harness.memory_api import memory_note
            return self._json(memory_note(self.run_root, content,
                                          (req.get("role") or "note").strip() or "note"))
        if p == "/api/lessons/admit":                # transition a lesson to admitted
            req, bad = self._req_json()
            if bad:
                return bad
            lesson_id = str(req.get("lesson_id", "")).strip()
            if not lesson_id:
                return self._json({"error": "provide 'lesson_id'"}, 400)
            from harness.lesson_store import LessonStore
            from pathlib import Path
            store = LessonStore.load(Path(self.run_root) / "lessons.jsonl")
            try:
                row = store.transition(lesson_id, "admitted")
                store.save(Path(self.run_root) / "lessons.jsonl")
                return self._json(row)
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
        if p == "/api/lessons/retire":               # transition a lesson to retired
            req, bad = self._req_json()
            if bad:
                return bad
            lesson_id = str(req.get("lesson_id", "")).strip()
            if not lesson_id:
                return self._json({"error": "provide 'lesson_id'"}, 400)
            from harness.lesson_store import LessonStore
            from pathlib import Path
            store = LessonStore.load(Path(self.run_root) / "lessons.jsonl")
            try:
                row = store.transition(lesson_id, "retired")
                store.save(Path(self.run_root) / "lessons.jsonl")
                return self._json(row)
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
        if p == "/api/eval/run":                       # a real eval -> a sealed, offline-verifiable receipt
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.eval_run_route import handle_eval_run
            body, code = handle_eval_run(req, self.run_root)
            return self._json(body, code)
        if p == "/api/eval/verify":                     # re-check a receipt offline; the verdict is the answer
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.eval_run_route import handle_eval_verify
            body, code = handle_eval_verify(req)
            return self._json(body, code)
        if p == "/api/audit/run":                        # a post-work review -> a receipt chained onto the work receipt
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.audit_run_route import handle_audit_run
            body, code = handle_audit_run(req, self.run_root)
            return self._json(body, code)
        if p == "/api/audit/verify":                     # re-check an audit receipt (and its chain) offline
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.audit_run_route import handle_audit_verify
            body, code = handle_audit_verify(req)
            return self._json(body, code)
        if p == "/api/usage/verify":                     # re-check a usage receipt offline; the verdict is the answer
            req, bad = self._req_json()
            if bad:
                return bad
            from harness.usage_route import handle_usage_verify
            body, code = handle_usage_verify(req)
            return self._json(body, code)
        if p.startswith("/api/lane/"):                   # generic lane caller
            parts = p.split("/")
            if len(parts) < 5:
                return self._json({"error": "use /api/lane/<name>/<tool>"}, 400)
            lane_name = parts[3]
            tool_name = parts[4]
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            args = req.get("args", {}) if isinstance(req, dict) else {}
            gov_tier = str(req.get("governance_tier", "")) if isinstance(req, dict) else ""
            timeout = int(req.get("timeout", 20)) if isinstance(req, dict) else 20
            from harness.lane_caller import call_lane_tool
            result = call_lane_tool(lane_name, tool_name, args,
                                    timeout=timeout, governance_tier=gov_tier)
            code = 403 if result.get("governance_denied") else (
                400 if "error" in result else 200)
            return self._json(result, code)
        return self._json({"error": "not found"}, 404)
def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="flywheel superapp gateway (one origin)")
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--serve-url", default="http://127.0.0.1:8765")
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    ap.add_argument("--run-root", default=run_root_default())
    ap.add_argument("--cors", action="store_true",
                    help="allow cross-origin browser clients (off by default; the gateway is local)")
    ap.add_argument("--host", action="append", default=None, dest="host", metavar="ADDR",
                    help="bind address, repeatable (default 127.0.0.1, loopback only). Repeat to "
                         "bind several interfaces at once, e.g. --host 127.0.0.1 --host 100.x.y.z "
                         "serves the local app on loopback AND a Tailscale phone, without exposing "
                         "every LAN the way 0.0.0.0 does. 0.0.0.0 accepts all IPv4 and subsumes the "
                         "rest. The bearer token and the Host allowlist still gate every request, "
                         "and a TLS tunnel should front a routable bind.")
    ap.add_argument("--allow-host", action="append", default=[], dest="allow_host",
                    help="add a Host header value to the DNS-rebinding allowlist (repeatable). "
                         "Give the public tunnel hostname here so a phone can reach this gateway.")
    return ap


def _resolve_hosts(requested):
    """Turn the raw --host list into the bind order. Default stays loopback only.
    Duplicates collapse while keeping first-seen order. 0.0.0.0 accepts every
    IPv4, so it cannot share a port with a specific IPv4 bind; when present it
    wins and the rest are dropped."""
    hosts, seen = [], set()
    for h in (requested or ["127.0.0.1"]):
        if h not in seen:
            seen.add(h)
            hosts.append(h)
    if "0.0.0.0" in hosts:
        return ["0.0.0.0"]
    return hosts


def _bind_hosts(hosts, port):
    """Bind one ThreadingHTTPServer per host, all sharing the one _Handler class.
    A host whose address this machine does not hold (e.g. the Tailscale interface
    is down) is reported and skipped, so a working interface still serves instead
    of the whole gateway refusing to start. Returns the bound servers in order;
    empty when none bound."""
    servers = []
    for h in hosts:
        try:
            servers.append(ThreadingHTTPServer((h, port), _Handler))
        except OSError as e:
            print(f"  SKIP      cannot bind {h}:{port}: {e}")
    return servers


def _serve_all(servers):
    """Serve every bound socket. All but the last run in daemon threads; the last
    blocks the main thread so Ctrl-C still stops the process. On shutdown the
    operation service is stopped once and every socket is closed."""
    import threading
    for s in servers[:-1]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        servers[-1].serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _Handler.operation_service.shutdown()
        for s in servers:
            s.server_close()


def main(argv=None) -> int:
    a = _build_parser().parse_args(argv)
    _Handler.root = Path(a.root).resolve()
    _Handler.serve_url = a.serve_url
    _Handler.ollama_url = a.ollama_url
    _Handler.run_root = a.run_root
    _Handler.cors = a.cors
    # Default is unchanged: nothing goes remote unless the operator opts in with
    # --host and names the public hostname with --allow-host. The token and the
    # Host allowlist remain the guard on every request.
    _Handler.allowed_hosts = DEFAULT_HOSTS | frozenset(a.allow_host)
    flywheel_home = Path(os.environ.get("FLYWHEEL_HOME", str(Path.home() / ".flywheel")))
    _Handler.flywheel_home = flywheel_home
    _Handler.auth_token = load_or_create_token(flywheel_home)
    hosts = _resolve_hosts(a.host)
    servers = _bind_hosts(hosts, a.port)
    if not servers:
        print(f"no interface bound on port {a.port}; nothing to serve")
        return 1
    bound = [s.server_address[0] for s in servers]
    remote = [h for h in bound if h not in ("127.0.0.1", "localhost", "::1")]
    if remote:
        print(f"  REMOTE    binding {', '.join(remote)}: reachable off-box. Front a routable "
              f"bind with a TLS tunnel; allowlisted hosts = {sorted(_Handler.allowed_hosts)}")
    state_root = flywheel_home / "state"
    from harness.gateway_operations import GatewayOperations
    from harness.gateway_operation_process import GatewayAgentProcessFactory
    from harness.gateway_operation_recovery import recover_gateway_operations
    from harness.journey_recovery import recover_store
    _Handler.operation_service = GatewayOperations(state_root, clock=_Handler.clock)
    _Handler.operation_process_factory = GatewayAgentProcessFactory(
        repo_root=_Handler.root, run_root=Path(_Handler.run_root))
    from harness.credential_handles import CredentialHandleStore
    from harness.keychain import keychain_get
    from harness.session_token import SessionTokenStore
    _Handler.session_token_store = SessionTokenStore(
        CredentialHandleStore(state_root, keychain_get=keychain_get))
    _Handler._session_token_state_root = state_root
    recover_store(state_root, now=_Handler.clock())
    recover_gateway_operations(state_root, now=_Handler.clock())
    print(f"flywheel gateway: http://127.0.0.1:{a.port}  root={_Handler.root}")
    print(f"  bound     {', '.join(f'{h}:{a.port}' for h in bound)}")
    print(f"  token     {flywheel_home / 'gateway.token'}  (send as: Authorization: Bearer <token>)")
    print(f"  surface   Flywheel Desktop (the native client) talks to this gateway")
    print(f"  dev shell http://127.0.0.1:{a.port}/site/index.html  (dev/CI fallback only)")
    print(f"  world     http://127.0.0.1:{a.port}/api/world")
    print(f"  health    http://127.0.0.1:{a.port}/api/endpoints/health")
    print(f"  router    http://127.0.0.1:{a.port}/api/endpoints    (all providers)")
    print(f"  studio    POST /api/forge {{'goal': ...}}            (goal -> verified PRP)")
    print(f"  route     POST /api/route {{'prompt':...,'endpoint':...}} (any provider + a receipt)")
    print(f"  companion POST /api/companion {{'prompt': ...}}      (answer local, escalate hard)")
    print(f"  agent     POST /api/agent {{'goal':...,'endpoint':...}} (gated tool loop over ANY provider, witnessed)")
    print(f"  eval      POST /api/eval/run {{'endpoint':...}} (real eval -> a sealed, offline-verifiable receipt)")
    print(f"  audit     POST /api/audit/run {{'work_receipt':...}} (post-work review -> a receipt chained onto the work)")
    print(f"  training  http://127.0.0.1:{a.port}/api/training/status  (read-only supervisor status)")
    print(f"  stats     http://127.0.0.1:{a.port}/api/router/stats  (adaptive-routing scoreboard)")
    print(f"  openai    POST /v1/chat/completions  +  GET /v1/models  (drop-in, model=any provider, stream ok)")
    _serve_all(servers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
