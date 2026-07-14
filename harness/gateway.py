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
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness.run_paths import run_root_default


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
    return {"schema": "flywheel.receipts/v1",
            "catalog": catalog,
            "catalog_present": sum(1 for r in catalog if r["present"]),
            "envelopes": envelopes,
            "envelope_count": len(envelopes),
            "pass_count": passes}


def _resolve_workspace_root(requested, default: Path) -> "tuple[Path, str | None]":
    """Resolve the workspace root an agent run operates in. The caller may
    name any EXISTING directory (the desktop IDE points at an open project);
    the ToolExecutor then sandboxes reads and gated writes to that root. A
    missing or non-directory path is refused, never silently substituted."""
    if not requested:
        return default, None
    try:
        p = Path(str(requested)).expanduser().resolve()
    except (OSError, ValueError) as e:
        return default, f"invalid root: {e}"
    if not p.is_dir():
        return default, f"root is not an existing directory: {requested}"
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
# chains into ONE tamper-evident record (the audit trail no other router keeps).
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
            "credential": credential}


def route_request(prompt: str, endpoint: str) -> tuple[dict, int]:
    """Validate + route a request to a named endpoint. Returns (body, http_code).
    Credential PRESENCE gate: an endpoint with no key present is refused honestly
    (never a silent local fallback), and no key value is ever read or returned."""
    roster = _unified_roster()
    entry = next((e for e in roster.get("endpoints", []) if e["name"] == endpoint), None)
    if entry is None:
        usable = roster.get("usable_names", [])
        return {"error": f"unknown endpoint {endpoint!r}", "usable": usable}, 404
    if entry.get("credential") == "absent":
        return {"error": f"endpoint {endpoint!r} has no credential present; set its API "
                f"key in the environment (presence only, never read here)",
                "credential": "absent"}, 400
    try:
        from harness.endpoint_registry import make_endpoint_proposer
    except Exception:
        from endpoint_registry import make_endpoint_proposer
    try:
        prop = make_endpoint_proposer(endpoint, ledger=_router_ledger())
    except Exception as e:
        return {"error": f"cannot build a proposer for {endpoint!r}: {e}"}, 502
    try:
        return route_answer(prompt, endpoint, prop, credential=entry.get("credential", "")), 200
    except Exception as e:
        return {"error": f"provider call failed: {e}"}, 502


# --- OpenAI-compatible surface: /v1/chat/completions + /v1/models ---------------
# Any OpenAI SDK or client can point its base_url at this gateway and route to ANY
# provider by naming it in `model` ("anthropic", "openai:gpt-4o", or a local name),
# getting back a standard ChatCompletion PLUS an `x_receipt` extension OpenAI clients
# ignore. This is the drop-in compatibility that makes Flywheel a better router: the
# same wire protocol every tool already speaks, plus the verify layer none of them have.

def _flatten_messages(messages) -> tuple[str, str]:
    """OpenAI messages -> (system, prompt). System turns concatenate. A single user
    turn passes through as the bare prompt (unchanged). A multi-turn conversation is
    rendered as a labelled transcript ending with an open `Assistant:` turn, so the
    model sees the history instead of only the last line. Content may be a string or
    the OpenAI content-parts array. (Structured passthrough to a provider's own chat
    template is a future refinement; the proposer seam is single-prompt today.)"""
    system, convo = "", []
    for m in messages or []:
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        content = content or ""
        if role == "system":
            system = (system + "\n" + content).strip() if system else content
        elif role in ("user", "assistant", "tool"):
            convo.append((role, content))
    if len(convo) <= 1:
        return system, (convo[0][1] if convo else "")
    label = {"user": "User", "assistant": "Assistant", "tool": "Tool"}
    lines = [f"{label.get(r, 'User')}: {c}" for r, c in convo]
    lines.append("Assistant:")
    return system, "\n\n".join(lines)


def _resolve_proposer(model: str, serve_url: str):
    """Pick the proposer for an OpenAI `model` string. Returns
    (proposer, error, code). Empty / a local alias -> the local serve model; a
    roster endpoint name or `name:model` -> that provider (credential-gated,
    honest error if absent); anything else -> 404."""
    m = (model or "").strip()
    if m in ("", "flywheel", "flywheel-serve", "serve", "default", "local", "auto"):
        try:
            from harness.proposer import ServeProposer
        except Exception:
            from proposer import ServeProposer
        return ServeProposer(base_url=serve_url), None, 200
    name = m.split(":", 1)[0]
    sub = m.split(":", 1)[1] if ":" in m else None
    roster = _unified_roster()
    entry = next((e for e in roster.get("endpoints", []) if e["name"] == name), None)
    if entry is None:
        return None, f"unknown model {m!r}; see GET /v1/models", 404
    if entry.get("credential") == "absent":
        return None, f"model {name!r} has no credential present; set its API key in the environment", 400
    try:
        from harness.endpoint_registry import make_endpoint_proposer
    except Exception:
        from endpoint_registry import make_endpoint_proposer
    try:
        return make_endpoint_proposer(name, model=sub, ledger=_router_ledger()), None, 200
    except Exception as e:
        return None, f"cannot build proposer for {name!r}: {e}", 502


def _chat_receipt(prompt, system, max_tokens, temperature, seed, out):
    from harness.messages_api import make_receipt
    gen = {"text": out.text, "seed": getattr(out, "seed", seed),
           "prompt_hash": getattr(out, "prompt_hash", "")}
    return make_receipt({"prompt": prompt, "system": system, "max_new_tokens": max_tokens,
                         "temperature": temperature, "seed": seed}, gen, out.model_ref)


def openai_embeddings(req: dict):
    """POST /v1/embeddings, routed to an embeddings-capable provider named by the
    `model` field ("openai" or "openai:text-embedding-3-small"). Flywheel forwards
    the request with the provider's key (present-only, from the env, never stored or
    logged), so any OpenAI embeddings client works through the same surface. Flywheel
    is zero-dep and computes no embeddings itself; it routes. Returns (body, code)."""
    import urllib.error

    from harness import providers
    model = str(req.get("model", ""))
    name = model.split(":", 1)[0] or "openai"
    spec = providers.REGISTRY.get(name)
    if spec is None or getattr(spec, "local", False):
        return {"error": {"message": f"no hosted embeddings provider '{name}'; "
                          "name one from GET /api/endpoints", "type": "invalid_request_error"}}, 400
    key = _resolve_credential(spec.api_key_env or "")
    if spec.api_key_env and not key:
        return {"error": {"message": f"missing credential for '{name}'",
                          "type": "invalid_request_error"}}, 400
    fwd = dict(req)
    fwd.pop("adaptive", None)
    if ":" in model:
        fwd["model"] = model.split(":", 1)[1]
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(spec.base_url.rstrip("/") + "/embeddings",
                                     data=json.dumps(fwd).encode(), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as r:
            return json.loads(r.read() or b"{}"), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read() or b"{}"), e.code
        except Exception:
            return {"error": {"message": f"provider returned {e.code}"}}, e.code
    except Exception as e:
        return {"error": {"message": f"embeddings upstream unreachable: {type(e).__name__}"}}, 502


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


def openai_chat(req: dict, serve_url: str):
    """Core of POST /v1/chat/completions (non-stream). Returns (body, code, receipt,
    text, model_ref). On error, receipt/text/model_ref are None.

    Failover: a comma-separated `model` ("openai,anthropic,serve") is a fallback
    chain, tried in order until one succeeds. The winning provider and any skipped
    ones are recorded on the receipt (routed_via / failover_from), so the record
    stays honest about which model actually answered. The reliability layer other
    routers charge for, in the open."""
    import time
    system, prompt = _flatten_messages(req.get("messages", []))
    if not prompt:
        return {"error": {"message": "messages must include a user turn", "type": "invalid_request_error"}}, 400, None, None, None
    temperature = float(req.get("temperature", 0.0))
    max_tokens = int(req.get("max_tokens", 512))
    seed = int(req.get("seed", 0))
    candidates = [m.strip() for m in str(req.get("model", "")).split(",") if m.strip()] or [""]
    # Opt-in adaptive routing: reorder the failover chain best-first by observed
    # success/cost and record each outcome. Off by default, so an explicit order is
    # honored. Routing only -- the oracle still decides what is accepted.
    adaptive = bool(req.get("adaptive"))
    if adaptive:
        candidates = get_router_stats().order(candidates)
    tried, last_err, last_code = [], "no provider resolved", 502
    for cand in candidates:
        t0 = time.time()
        proposer, err, code = _resolve_proposer(cand, serve_url)
        if err is not None:
            last_err, last_code = err, code
            tried.append((cand or "flywheel") + ": unavailable")
            if adaptive:
                get_router_stats().record(cand or "flywheel", False, time.time() - t0)
            continue
        try:
            out = proposer.generate(prompt, seed=seed, temperature=temperature,
                                    max_new_tokens=max_tokens, system=system)
        except Exception as e:
            last_err, last_code = f"provider call failed: {e}", 502
            tried.append((cand or "flywheel") + ": error")
            if adaptive:
                get_router_stats().record(cand or "flywheel", False, time.time() - t0)
            continue
        if adaptive:
            get_router_stats().record(cand or "flywheel", True, time.time() - t0)
        receipt = _chat_receipt(prompt, system, max_tokens, temperature, seed, out)
        receipt["routed_via"] = cand or "flywheel"
        if tried:
            receipt["failover_from"] = tried       # honest: which providers were skipped, and why
        body = {"id": "chatcmpl-" + receipt["receipt_id"], "object": "chat.completion",
                "created": int(time.time()), "model": out.model_ref,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": out.text},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": len(prompt.split()),
                          "completion_tokens": len(str(out.text).split()),
                          "total_tokens": len(prompt.split()) + len(str(out.text).split())},
                "x_receipt": receipt}
        return body, 200, receipt, out.text, out.model_ref
    detail = "; ".join(tried) if tried else last_err
    return {"error": {"message": f"all providers failed ({detail})", "type": "api_error"},
            "failover_from": tried}, last_code, None, None, None


def openai_models() -> dict:
    """GET /v1/models: the roster as OpenAI model objects, so a client's model
    picker lists every provider it can route to. `flywheel` is the verified local seat."""
    roster = _unified_roster()
    data = [{"id": "flywheel", "object": "model", "created": 0, "owned_by": "flywheel"}]
    for e in roster.get("endpoints", []):
        data.append({"id": e["name"], "object": "model", "created": 0,
                     "owned_by": e.get("source", "flywheel")})
    return {"object": "list", "data": data}


class _Handler(BaseHTTPRequestHandler):
    root = REPO
    serve_url = "http://127.0.0.1:8765"
    ollama_url = "http://127.0.0.1:11434"
    run_root = run_root_default()

    MAX_BODY = 32 * 1024 * 1024               # 32 MiB ceiling on any request body
    cors = False                              # opt-in (--cors) so browser OpenAI clients can call in

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
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _sse_chat(self, req: dict):
        """Stream a chat completion as OpenAI Server-Sent Events. The verified or
        routed answer is produced whole (a receipt is a hash over the FULL response,
        so we stand behind what we stream), then delivered as chat.completion.chunk
        deltas ending with [DONE]. Any OpenAI streaming client consumes it as-is."""
        import time
        body, code, receipt, text, model_ref = openai_chat(req, self.serve_url)
        if code != 200:
            return self._json(body, code)          # errors are plain JSON, not a stream
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
            if extra:
                obj.update(extra)
            self.wfile.write(("data: " + json.dumps(obj) + "\n\n").encode())
            self.wfile.flush()

        try:
            emit({"index": 0, "delta": {"role": "assistant"}, "finish_reason": None})
            import re
            for piece in (re.findall(r"\S+\s*", str(text)) or [str(text)]):
                emit({"index": 0, "delta": {"content": piece}, "finish_reason": None})
            emit({"index": 0, "delta": {}, "finish_reason": "stop"}, {"x_receipt": receipt})
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except Exception:
            pass                                   # client hung up mid-stream; nothing to do

    def _sse_agent(self, req: dict, goal: str, endpoint: str):
        """Stream the agentic tool loop as Server-Sent Events: each assistant turn,
        tool call, and tool result is emitted as it happens, then a final `done`
        event carries the witnessed result (verdict + integrity)."""
        try:
            max_steps = max(1, min(int(req.get("max_steps", 6)), 12))
        except (TypeError, ValueError):
            max_steps = 6
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors()
        self.end_headers()

        def emit(evt):
            try:
                self.wfile.write(("data: " + json.dumps(evt) + "\n\n").encode())
                self.wfile.flush()
            except Exception:
                pass

        from harness.router_agent import run_router_agent
        root, root_err = _resolve_workspace_root(req.get("root"), self.root)
        if root_err:
            emit({"type": "error", "error": root_err})
            try:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except Exception:
                pass
            return
        try:
            result = run_router_agent(
                goal, endpoint, root=str(root),
                allow_write=bool(req.get("allow_write", False)),
                allow_exec=bool(req.get("allow_exec", False)),
                max_steps=max_steps, test_cmd=(req.get("test_cmd") or None),
                model=(req.get("model") or None),
                compact_budget=int(req.get("compact_budget", 0) or 0), on_event=emit)
            emit({"type": "done", "final": result.get("final"), "steps": result.get("steps"),
                  "verified": result.get("verified"), "integrity": result.get("integrity"),
                  # the reviewability projection + checkpoint ride the done
                  # event so the surface can offer a sign-this-run attestation
                  "review": result.get("review"),
                  "checkpoint": result.get("checkpoint"),
                  # the window manifest: what the model actually saw
                  "context_manifest": result.get("context_manifest"),
                  "risk_review": result.get("risk_review"),
                  "provenance": result.get("provenance"),
                  "duration_s": result.get("duration_s"),
                  "ttva_s": result.get("ttva_s"),
                  "run_receipt": _countersign_run(result)})
        except Exception as e:
            emit({"type": "error", "error": f"{type(e).__name__}: {e}"})
        try:
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except Exception:
            pass

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
        if self.root.resolve() not in target.parents and target != self.root.resolve():
            return self._json({"error": "forbidden"}, 403)
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            return self._json({"error": "not found"}, 404)
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
        """Any uncaught handler error becomes a clean 500, never a dropped
        connection or a stderr traceback. Only the exception TYPE is surfaced, so a
        stack path never leaks to the client."""
        try:
            self._json({"error": {"message": f"internal error: {type(e).__name__}",
                                  "type": "api_error"}}, 500)
        except Exception:
            pass                                   # headers already partly sent; nothing safe to do

    def do_GET(self):
        try:
            self._get()
        except Exception as e:
            self._safe_500(e)

    def do_POST(self):
        try:
            self._post()
        except Exception as e:
            self._safe_500(e)

    def _get(self):
        p = self.path.split("?", 1)[0]
        qs = self.path.split("?", 1)[1] if "?" in self.path else ""
        if p == "/api/endpoints/health":
            return self._json(endpoint_roster(self.serve_url, self.ollama_url))
        if p == "/api/endpoints":
            return self._json(_unified_roster())     # full universal-router roster
        if p == "/api/world":
            return self._json(_projected_world(self.root))
        if p == "/api/lanes":                        # the lane roster (umbrella layer)
            from harness.lanes import lane_roster
            probe = "probe=true" in qs or "probe=1" in qs
            return self._json(lane_roster(probe=probe))
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
        if p == "/api/receipts":                     # the receipts ledger (catalog + envelopes)
            return self._json(receipts_ledger(self.root, self.run_root))
        if p == "/api/profiles":                     # profile manifests over the one substrate
            from harness.profiles import profile_roster
            return self._json(profile_roster())
        if p == "/api/workflows":                    # workflow definitions + recent runs
            from harness.workflows import workflow_roster
            return self._json(workflow_roster(self.run_root))
        if p == "/api/memory":                       # durable memory stats (fold index)
            from harness.memory_api import memory_stats
            return self._json(memory_stats(self.run_root))
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
        if p == "/api/store/verify":                 # walk + re-check the audit chain
            from harness.store import verify_chain
            return self._json(verify_chain())
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
        if p == "/api/plugins/probe":                # spawn a plugin's server, report its real tools
            from harness.plugins import probe_plugin
            name = ""
            for part in qs.split("&"):
                if part.startswith("name="):
                    name = urllib.parse.unquote(part[5:])
            if not name:
                return self._json({"error": "provide ?name="}, 400)
            return self._json(probe_plugin(name))
        if p == "/api/router/stats":                 # observed per-provider success/cost
            return self._json(get_router_stats().snapshot())
        if p == "/v1/models":                        # OpenAI-compatible model list (the roster)
            return self._json(openai_models())
        if p.startswith("/v1/") or p == "/generate" or p == "/health":
            return self._proxy(self.serve_url.rstrip("/") + p)
        return self._static(p)

    def _post(self):
        p = self.path.split("?", 1)[0]
        if p == "/v1/chat/completions":              # OpenAI-compatible, routes to ANY provider
            length = self._content_length()
            if length is None:
                return self._json({"error": {"message": "invalid or oversized Content-Length",
                                             "type": "invalid_request_error"}}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            if req.get("stream"):
                return self._sse_chat(req)
            body, code, _r, _t, _m = openai_chat(req, self.serve_url)
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
        if p == "/api/forge":                        # goal -> verified PRP (the studio)
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            goal = (req.get("goal") or "").strip()
            if not goal:
                return self._json({"error": "provide a non-empty 'goal'"}, 400)
            return self._json(_forge(goal, examples=req.get("examples"),
                                     documentation=req.get("documentation"),
                                     context=req.get("context", "")))
        if p == "/api/science":                       # evidence -> spec -> witnessed judgment, one chain
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
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
            return self._json(science_run(
                question, claims=claims, measurements=measurements,
                max_sources=max_sources,
                workdir=_P(self.run_root) / "science"))
        if p == "/api/retrieve":                      # retrieval that cites its evidence
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
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
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
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
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
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
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
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
        if p == "/api/capability":                    # probe a model on THIS machine
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
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
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            original = (req.get("original") or "").strip()
            if not original or not isinstance(req.get("passed"), bool):
                return self._json({"error": "provide 'original' (entity id) "
                                            "and boolean 'passed'"}, 400)
            from harness.retention import retention_record
            return self._json(retention_record(
                original, req["passed"], note=str(req.get("note", ""))))
        if p == "/api/explain":                       # the teach-back as a receipt (engagement, mechanical)
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
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
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            run = req.get("run") if isinstance(req.get("run"), dict) else None
            files = req.get("reviewed_files")
            if run is None or not isinstance(files, list):
                return self._json({"error": "provide 'run' (an agent run doc) "
                                            "and 'reviewed_files' (a list)"}, 400)
            from harness.attestation import attest
            doc = attest(run, files, note=str(req.get("note", "")),
                         reviewer=str(req.get("reviewer", "")))
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
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            prompt = (req.get("prompt") or "").strip()
            endpoint = (req.get("endpoint") or "").strip()
            if not prompt or not endpoint:
                return self._json({"error": "provide non-empty 'prompt' and 'endpoint'"}, 400)
            body, code = route_request(prompt, endpoint)
            return self._json(body, code)
        if p == "/api/companion":                     # the seat: answer local, escalate the hard slice
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            prompt = (req.get("prompt") or "").strip()
            if not prompt:
                return self._json({"error": "provide a non-empty 'prompt'"}, 400)
            seat = get_companion_seat(self.serve_url)
            if seat is None:
                return self._json({"error": "companion seat unavailable"}, 503)
            return self._json(companion_answer(seat, prompt, req.get("solution_sig", "")))
        if p == "/api/agent":                          # the agentic tool loop over ANY provider
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
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
            from harness.router_agent import run_router_agent
            try:
                result = run_router_agent(
                    goal, endpoint, root=str(root),
                    allow_write=bool(req.get("allow_write", False)),
                    allow_exec=bool(req.get("allow_exec", False)),
                    max_steps=max_steps, test_cmd=(req.get("test_cmd") or None),
                    model=(req.get("model") or None),
                    compact_budget=int(req.get("compact_budget", 0) or 0))
            except Exception as e:
                return self._json({"error": f"{type(e).__name__}: {e}"}, 502)
            if effort is not None:
                result["effort"] = effort   # the dial position, receipted
            result["run_receipt"] = _countersign_run(result)
            return self._json(result)
        if p == "/api/workflow":                       # staged run with a chained receipt, any endpoint
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
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
                    run_root=self.run_root)
            except Exception as e:
                return self._json({"error": f"workflow failed: {type(e).__name__}: {e}"}, 502)
            return self._json(doc)
        if p == "/api/memory/recall":                  # verbatim recall from the fold index
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            query = (req.get("query") or "").strip()
            if not query:
                return self._json({"error": "provide a non-empty 'query'"}, 400)
            from harness.memory_api import memory_recall
            return self._json(memory_recall(self.run_root, query,
                                            req.get("top_k", 5)))
        if p == "/api/plugins/register":               # register a custom MCP server by argv
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            from harness.plugins import register_mcp
            out = register_mcp(req.get("name", ""), req.get("command", []),
                               (req.get("detail") or "").strip())
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/keychain/set":                   # store a secret in the OS keychain
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            from harness.keychain import keychain_set
            out = keychain_set((req.get("name") or "").strip(),
                               req.get("value") or "")
            # The secret is now only in the OS store; nothing here logs or
            # echoes it, and `req` goes out of scope with this request.
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/keychain/delete":                # remove a stored secret
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            from harness.keychain import keychain_delete
            out = keychain_delete((req.get("name") or "").strip())
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/store/entity":                   # store a content-addressed entity
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            from harness.store import put_entity
            out = put_entity((req.get("kind") or "").strip(),
                             req.get("data") or {},
                             project=(req.get("project") or "").strip())
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/store/query":                    # query entities by kind/project
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            from harness.store import query_entities
            rows = query_entities(kind=(req.get("kind") or None),
                                  project=(req.get("project") or None),
                                  limit=int(req.get("limit", 200) or 200))
            return self._json({"schema": "flywheel.store-query/v1",
                               "entities": rows, "n": len(rows)})
        if p == "/api/projects/add":                   # register a project directory
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            from harness.projects import add_project
            out = add_project((req.get("root") or "").strip(),
                              (req.get("name") or "").strip())
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/projects/remove":                # unregister a project directory
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            from harness.projects import remove_project
            out = remove_project((req.get("root") or "").strip())
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/lint":                           # native receipt-carrying linter over a project
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            root, err = _resolve_workspace_root(req.get("root"), self.root)
            if err:
                return self._json({"error": err}, 400)
            from harness.linter import lint_project
            paths = req.get("paths") if isinstance(req.get("paths"), list) else None
            out = lint_project(str(root), paths)
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/index":                          # drive the index engine over a project root
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
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
        if p == "/api/marketplace/install":            # catalog entry -> plugin registry
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            from harness.marketplace import install_from_catalog
            out = install_from_catalog((req.get("name") or "").strip())
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/plugins/toggle":                 # enable/disable a custom plugin
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            from harness.plugins import toggle_mcp
            out = toggle_mcp(req.get("name", ""), bool(req.get("enabled", True)))
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/plugins/remove":                 # remove a custom plugin
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            from harness.plugins import remove_mcp
            out = remove_mcp(req.get("name", ""))
            return self._json(out, 400 if "error" in out else 200)
        if p == "/api/lsp":                            # editor intelligence over any LSP server
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
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
            length = self._content_length()
            if length is None:
                return self._json({"error": "invalid or oversized Content-Length"}, 400)
            try:
                req = json.loads(self.rfile.read(length) or b"{}") if length else {}
            except Exception:
                req = {}
            content = (req.get("content") or "").strip()
            if not content:
                return self._json({"error": "provide non-empty 'content'"}, 400)
            from harness.memory_api import memory_note
            return self._json(memory_note(self.run_root, content,
                                          (req.get("role") or "note").strip() or "note"))
        return self._json({"error": "not found"}, 404)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="flywheel superapp gateway (one origin)")
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--serve-url", default="http://127.0.0.1:8765")
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    ap.add_argument("--run-root", default=run_root_default())
    ap.add_argument("--cors", action="store_true",
                    help="allow cross-origin browser clients (off by default; the gateway is local)")
    a = ap.parse_args(argv)
    _Handler.root = Path(a.root).resolve()
    _Handler.serve_url = a.serve_url
    _Handler.ollama_url = a.ollama_url
    _Handler.run_root = a.run_root
    _Handler.cors = a.cors
    httpd = ThreadingHTTPServer(("127.0.0.1", a.port), _Handler)
    print(f"flywheel gateway: http://127.0.0.1:{a.port}  root={_Handler.root}")
    print(f"  shell     http://127.0.0.1:{a.port}/site/index.html")
    print(f"  world     http://127.0.0.1:{a.port}/api/world")
    print(f"  health    http://127.0.0.1:{a.port}/api/endpoints/health")
    print(f"  router    http://127.0.0.1:{a.port}/api/endpoints    (all providers)")
    print(f"  studio    POST /api/forge {{'goal': ...}}            (goal -> verified PRP)")
    print(f"  route     POST /api/route {{'prompt':...,'endpoint':...}} (any provider + a receipt)")
    print(f"  companion POST /api/companion {{'prompt': ...}}      (answer local, escalate hard)")
    print(f"  agent     POST /api/agent {{'goal':...,'endpoint':...}} (gated tool loop over ANY provider, witnessed)")
    print(f"  training  http://127.0.0.1:{a.port}/api/training/status  (read-only supervisor status)")
    print(f"  stats     http://127.0.0.1:{a.port}/api/router/stats  (adaptive-routing scoreboard)")
    print(f"  openai    POST /v1/chat/completions  +  GET /v1/models  (drop-in, model=any provider, stream ok)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
