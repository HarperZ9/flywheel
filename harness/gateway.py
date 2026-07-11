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
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Ensure `from harness.X import ...` resolves even when run as `python
# harness/gateway.py` (script mode puts harness/ on the path, not the repo root),
# so the on-demand endpoint_registry / context_forge imports work in both modes.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Receipt catalog: in-repo, re-checkable artifacts that define the world state.
# Relative to the served root. Missing files are reported honestly as absent.
RECEIPT_CATALOG = (
    "artifacts/flywheel-local-coder-14b-benchmark-ci.json",
    "artifacts/flywheel-local-coder-14b-benchmark-m7-hard-scorecard.json",
    "artifacts/exe/model_release_readiness.local.json",
    "tasks/curated/hard_v2.jsonl",
    "demos/index.json",
)

# The flagship spine (peers composing through protocols, not a hierarchy).
SPINE = ("local-model", "telos", "index", "forum", "gather", "crucible",
         "mneme", "relay", "plexus")


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
            "credential_present": bool(key_env and os.environ.get(key_env)),
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
    return unified_roster()


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
    return training_status(run_root)


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
    return forge_prp(goal, **kw).to_dict()


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


class _Handler(BaseHTTPRequestHandler):
    root = REPO
    serve_url = "http://127.0.0.1:8765"
    ollama_url = "http://127.0.0.1:11434"
    run_root = "E:/local-model-run"

    def log_message(self, *a):  # quiet
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self, target: str):
        length = int(self.headers.get("Content-Length", 0))
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

    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/api/endpoints/health":
            return self._json(endpoint_roster(self.serve_url, self.ollama_url))
        if p == "/api/endpoints":
            return self._json(_unified_roster())     # full universal-router roster
        if p == "/api/world":
            return self._json(_projected_world(self.root))
        if p == "/api/training/status":
            return self._json(_training_status(self.run_root))
        if p.startswith("/v1/") or p == "/generate" or p == "/health":
            return self._proxy(self.serve_url.rstrip("/") + p)
        return self._static(p)

    def do_POST(self):
        p = self.path.split("?", 1)[0]
        if p.startswith("/v1/") or p == "/generate":
            return self._proxy(self.serve_url.rstrip("/") + p)
        if p == "/api/forge":                        # goal -> verified PRP (the studio)
            length = int(self.headers.get("Content-Length", 0))
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
        if p == "/api/companion":                     # the seat: answer local, escalate the hard slice
            length = int(self.headers.get("Content-Length", 0))
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
        return self._json({"error": "not found"}, 404)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="flywheel superapp gateway (one origin)")
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--serve-url", default="http://127.0.0.1:8765")
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    ap.add_argument("--run-root", default="E:/local-model-run")
    a = ap.parse_args(argv)
    _Handler.root = Path(a.root).resolve()
    _Handler.serve_url = a.serve_url
    _Handler.ollama_url = a.ollama_url
    _Handler.run_root = a.run_root
    httpd = ThreadingHTTPServer(("127.0.0.1", a.port), _Handler)
    print(f"flywheel gateway: http://127.0.0.1:{a.port}  root={_Handler.root}")
    print(f"  shell     http://127.0.0.1:{a.port}/site/index.html")
    print(f"  world     http://127.0.0.1:{a.port}/api/world")
    print(f"  health    http://127.0.0.1:{a.port}/api/endpoints/health")
    print(f"  router    http://127.0.0.1:{a.port}/api/endpoints    (all providers)")
    print(f"  studio    POST /api/forge {{'goal': ...}}            (goal -> verified PRP)")
    print(f"  companion POST /api/companion {{'prompt': ...}}      (answer local, escalate hard)")
    print(f"  training  http://127.0.0.1:{a.port}/api/training/status  (read-only supervisor status)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
