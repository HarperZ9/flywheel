"""Extracted state, world, countersign, companion, and SSE helpers for harness/gateway.py."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace


def resolve_credential(key_env: str) -> str:
    """Env first, OS keychain second; '' when neither."""
    try:
        from harness.keychain import resolve_credential as _rc
        return _rc(key_env)
    except Exception:
        return os.environ.get(key_env or "", "")


def endpoint_roster(
    serve_url: str,
    ollama_url: str,
    *,
    probe_fn,
    resolve_credential_fn,
) -> dict:
    """Local tiers get a live probe; enterprise providers report credential presence only."""
    ok, info = probe_fn(serve_url.rstrip("/") + "/health")
    local = [{"name": "flywheel-serve", "tier": "local", "kind": "serve",
              "healthy": ok, "model_ref": info.get("model_ref", "")}]
    ok, info = probe_fn(ollama_url.rstrip("/") + "/api/version")
    local.append({"name": "flywheel-ollama", "tier": "local", "kind": "ollama",
                  "healthy": ok, "version": info.get("version", "")})
    try:
        from harness.endpoints import PROVIDERS
    except Exception:
        try:
            from endpoints import PROVIDERS  # standalone run
        except Exception:
            PROVIDERS = {}
    enterprise = [
        {"name": name, "tier": "enterprise", "model": spec.get("model", ""),
         "credential_present": bool(spec.get("key", "") and resolve_credential_fn(spec.get("key", ""))),
         "key_env": spec.get("key", "")}
        for name, spec in PROVIDERS.items()
    ]
    return {
        "schema": "flywheel.endpoint-roster/v1",
        "local": local, "enterprise": enterprise,
        "local_healthy": sum(1 for e in local if e["healthy"]),
        "local_total": len(local),
        "enterprise_configured": sum(1 for e in enterprise if e["credential_present"]),
    }


def world_state(root: Path, catalog, spine) -> dict:
    """Projected world v0: spine roster + receipt catalog with a root hash."""
    receipts, lines = [], []
    for rel in catalog:
        p = root / rel
        if p.is_file():
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            receipts.append({"path": rel, "sha256": h, "size": p.stat().st_size, "present": True})
        else:
            h = "MISSING"
            receipts.append({"path": rel, "sha256": h, "present": False})
        lines.append(f"{rel}:{h}")
    root_hash = hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()
    return {
        "schema": "flywheel.world/v0", "spine": list(spine), "receipts": receipts,
        "receipt_count": len(receipts),
        "present_count": sum(1 for r in receipts if r["present"]),
        "root_hash": root_hash,
    }


def receipts_ledger(root: Path, run_root: Path | str, *, world_state_fn) -> dict:
    """In-repo receipt catalog plus accepted proof envelopes under the run root."""
    catalog = world_state_fn(root)["receipts"]
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
                entry["verdict"], entry["task_id"] = "UNREADABLE", ""
            envelopes.append(entry)
    from harness.transparency_log import merkle_root
    leaves = [e["sha256"] for e in envelopes]
    return {
        "schema": "flywheel.receipts/v1", "catalog": catalog,
        "catalog_present": sum(1 for r in catalog if r["present"]),
        "envelopes": envelopes, "envelope_count": len(envelopes),
        "pass_count": sum(1 for e in envelopes if e["verdict"] == "PASS"),
        "merkle_root": merkle_root(leaves) if leaves else "",
        "merkle_note": "root over the ordered envelope hashes; GET "
                       "/api/receipts/proof?leaf=<sha256> returns an "
                       "inclusion proof re-checkable offline",
    }


def workspace_root_allowlist() -> list[str]:
    """Permitted workspace-root prefixes read from FLYWHEEL_WORKSPACE_ROOTS."""
    roots = []
    for part in os.environ.get("FLYWHEEL_WORKSPACE_ROOTS", "").split(os.pathsep):
        part = part.strip()
        if not part:
            continue
        try:
            roots.append(str(Path(part).expanduser().resolve()))
        except (OSError, ValueError):
            continue
    return roots


def resolve_workspace_root(requested, default: Path, *, allowlist_fn) -> tuple[Path, str | None]:
    """Resolve and allowlist-check a workspace root directory."""
    if not requested:
        return default, None
    try:
        p = Path(str(requested)).expanduser().resolve()
    except (OSError, ValueError) as e:
        return default, f"invalid root: {e}"
    if not p.is_dir():
        return default, f"root is not an existing directory: {requested}"
    allow = allowlist_fn()
    if allow:
        rp = str(p)
        if not any(rp == a or rp.startswith(a + os.sep) for a in allow):
            return default, f"root is not under an allowlisted workspace prefix: {requested}"
    return p, None


def unified_roster() -> dict:
    """Full universal-router roster, credential-presence only."""
    try:
        from harness.endpoint_registry import unified_roster as _ur
    except Exception:
        try:
            from endpoint_registry import unified_roster as _ur  # standalone run
        except Exception as e:
            return {"error": f"endpoint_registry unavailable: {e}"}
    try:
        return _ur()
    except Exception as e:
        return {"error": f"unified_roster failed: {e}"}


def relay_remote_state(relay_call_fn) -> dict:
    """Forward relay's phone-reachability report without reading relay config directly."""
    doctor = relay_call_fn("relay.doctor", {})
    if "error" in doctor:
        return {"reported": False, "reason": doctor["error"]}
    remote = doctor.get("remote")
    if not isinstance(remote, dict):
        return {"reported": False, "reason": "this relay build does not report the remote surface"}
    return {"reported": True, **remote}


def projected_world(root: Path, *, world_state_fn) -> dict:
    """Full projected world with fallback to inline v0 receipt catalog."""
    try:
        from harness.world import project_world
        return project_world(repo_root=root)
    except Exception:
        return world_state_fn(root)


def training_status(run_root: str) -> dict:
    """Read-only 32B supervisor status."""
    try:
        from harness.training_lane import training_status as _ts
    except Exception:
        try:
            from training_lane import training_status as _ts  # standalone run
        except Exception as e:
            return {"error": f"training_lane unavailable: {e}"}
    try:
        return _ts(run_root)
    except Exception as e:
        return {"error": f"training_status failed: {e}"}


def countersign_run(result: dict) -> dict:
    """Gateway-side countersign of an agent run into the verifiable store."""
    summary = {
        "checkpoint": str(result.get("checkpoint", "")),
        "verified": bool(result.get("verified")),
        "integrity_clean": bool((result.get("integrity") or {}).get("clean")),
        "review_sha256": hashlib.sha256(json.dumps(result.get("review") or {}, sort_keys=True).encode()).hexdigest(),
        "manifest_sha256": hashlib.sha256(json.dumps(result.get("context_manifest") or {}, sort_keys=True).encode()).hexdigest(),
        "high_risk_edits": len((result.get("risk_review") or {}).get("demands") or []),
    }
    try:
        from harness.store import put_entity
        stored = put_entity("agent-run", summary)
        return {**summary, "stored": stored.get("eid", ""), "chain_hash": stored.get("chain_hash", "")}
    except Exception as e:
        return {**summary, "stored": f"store unavailable: {type(e).__name__}"}


def countersign_workflow(doc: dict) -> dict:
    """Gateway-side countersign of a workflow run into the verifiable store."""
    summary = {
        "kind": "workflow-run", "workflow": str(doc.get("workflow", "")),
        "endpoint": str(doc.get("endpoint", "")), "status": str(doc.get("status", "")),
        "chain_hash": str(doc.get("chain_hash", "")), "n_steps": len(doc.get("steps") or []),
    }
    try:
        from harness.store import put_entity
        stored = put_entity("workflow-run", summary)
        return {**summary, "stored": stored.get("eid", ""), "store_chain_hash": stored.get("chain_hash", "")}
    except Exception as e:
        return {**summary, "stored": f"store unavailable: {type(e).__name__}"}


def forge(goal: str, **kw) -> dict:
    """Goal -> verified PRP via context_forge."""
    try:
        from harness.context_forge import forge_prp
    except Exception:
        try:
            from context_forge import forge_prp
        except Exception as e:
            return {"error": f"context_forge unavailable: {e}"}
    try:
        return forge_prp(goal, **kw).to_dict()
    except Exception as e:
        return {"error": f"forge failed: {e}"}


def companion_task(prompt: str, solution_sig: str = ""):
    tid = hashlib.sha256(f"{prompt}|{solution_sig}".encode()).hexdigest()[:16]
    return SimpleNamespace(task_id=tid, prompt=prompt, max_new_tokens=512, system="")


def companion_answer(seat, prompt: str, solution_sig: str = "", effort: str | None = None) -> dict:
    res = seat.answer(companion_task(prompt, solution_sig), solution_sig=solution_sig, effort=effort)
    out = res.to_dict()
    out["text"], out["best_effort_text"], out["ledger_len"] = res.text, res.best_effort_text, len(seat.ledger)
    return out


def route_answer(prompt: str, endpoint: str, proposer, *, credential: str = "local-none") -> dict:
    from harness.messages_api import make_receipt
    out = proposer.generate(prompt, seed=0, temperature=0.0, max_new_tokens=512, system="")
    gen = {"text": out.text, "seed": getattr(out, "seed", 0), "prompt_hash": getattr(out, "prompt_hash", "")}
    receipt = make_receipt(
        {"prompt": prompt, "system": "", "max_new_tokens": 512, "temperature": 0.0, "seed": 0},
        gen, out.model_ref)
    return {"schema": "flywheel.route-result/v1", "endpoint": endpoint, "model_ref": out.model_ref,
            "text": out.text, "receipt": receipt, "credential": credential, "usage": getattr(out, "usage", None)}


def stream_sse_chat(handler, req: dict, *, flatten_fn, openai_chat_fn):
    """Stream a completed, receipted answer as OpenAI-compatible SSE."""
    from harness.scaffold import scaffold_answer, scaffold_turn
    _sys, _prompt = flatten_fn(req.get("messages", []))
    env = scaffold_turn("\n".join(x for x in (_sys, _prompt) if x))
    bindings = getattr(handler, "_gateway_bindings", None)
    body, code, receipt, text, model_ref = (
        openai_chat_fn(req, handler.serve_url) if bindings is None else
        openai_chat_fn(req, handler.serve_url, bindings))
    if code != 200:
        return handler._json(body, code)
    cid, created = "chatcmpl-" + receipt["receipt_id"], int(time.time())
    handler.send_response(200)
    for k, v in (("Content-Type", "text/event-stream"), ("Cache-Control", "no-cache"), ("Connection", "keep-alive")):
        handler.send_header(k, v)
    handler._cors()
    handler.end_headers()

    def emit(choice, extra=None):
        obj = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model_ref, "choices": [choice]}
        if extra:
            obj.update(extra)
        handler.wfile.write(("data: " + json.dumps(obj) + "\n\n").encode())
        handler.wfile.flush()

    try:
        emit({"index": 0, "delta": {"role": "assistant"}, "finish_reason": None})
        for piece in (re.findall(r"\S+\s*", str(text)) or [str(text)]):
            emit({"index": 0, "delta": {"content": piece}, "finish_reason": None})
        scaffold_doc = scaffold_answer(str(text or ""), env, provenance={"endpoint": "v1", "model_ref": str(model_ref)})
        emit({"index": 0, "delta": {}, "finish_reason": "stop"}, {"x_receipt": receipt, "x_scaffold": scaffold_doc})
        handler.wfile.write(b"data: [DONE]\n\n")
        handler.wfile.flush()
    except Exception:
        pass
