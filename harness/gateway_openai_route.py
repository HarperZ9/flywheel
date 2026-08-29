"""Provider and OpenAI-compatible route implementations for the gateway.

`harness.gateway` keeps the public wrapper functions so existing tests and
callers can still monkeypatch names on that module. This file carries the
implementation that does not need direct access to the HTTP handler.
"""
from __future__ import annotations

import json
import time
import urllib.error


def route_request(
        prompt: str, endpoint: str, model: str = "", *, unified_roster,
        router_ledger, route_answer) -> tuple[dict, int]:
    """Validate and route one named endpoint request."""
    roster = unified_roster()
    entry = next((e for e in roster.get("endpoints", [])
                  if e["name"] == endpoint), None)
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
        kw = {"model": model} if model else {}
        prop = make_endpoint_proposer(endpoint, ledger=router_ledger(), **kw)
    except Exception as e:
        return {"error": f"cannot build a proposer for {endpoint!r}: {e}"}, 502
    try:
        return route_answer(
            prompt, endpoint, prop, credential=entry.get("credential", "")), 200
    except Exception as e:
        return {"error": f"provider call failed: {e}"}, 502


def flatten_messages(messages) -> tuple[str, str]:
    """OpenAI messages -> (system, prompt)."""
    system, convo = "", []
    for m in messages or []:
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, list):
            content = "".join(
                p.get("text", "") for p in content if isinstance(p, dict))
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


def resolve_proposer(
        model: str, serve_url: str, credential_bindings=None, *,
        unified_roster, router_ledger):
    """Resolve one local or explicitly credential-bound proposer."""
    m = (model or "").strip()
    if m in ("", "flywheel", "flywheel-serve", "serve", "default", "local", "auto"):
        try:
            from harness.proposer import ServeProposer
        except Exception:
            from proposer import ServeProposer
        return ServeProposer(base_url=serve_url), None, 200
    name = m.split(":", 1)[0]
    sub = m.split(":", 1)[1] if ":" in m else None
    if credential_bindings is None:
        roster = unified_roster()
        entry = next((e for e in roster.get("endpoints", [])
                      if e["name"] == name), None)
        if entry is None:
            return None, f"unknown model {m!r}; see GET /v1/models", 404
        if entry.get("credential") == "absent":
            return None, f"model {name!r} has no credential present", 400
    try:
        from harness.endpoint_registry import (
            make_authorized_endpoint_proposer, make_endpoint_proposer)
    except Exception:
        from endpoint_registry import (
            make_authorized_endpoint_proposer, make_endpoint_proposer)
    try:
        factory = (make_endpoint_proposer if credential_bindings is None else
                   make_authorized_endpoint_proposer)
        kwargs = {"model": sub, "ledger": router_ledger()}
        if credential_bindings is not None:
            kwargs["credential_bindings"] = credential_bindings
        return factory(name, **kwargs), None, 200
    except Exception as e:
        return None, f"cannot build proposer for {name!r}: {e}", 502


def chat_receipt(prompt, system, max_tokens, temperature, seed, out):
    from harness.messages_api import make_receipt
    gen = {"text": out.text, "seed": getattr(out, "seed", seed),
           "prompt_hash": getattr(out, "prompt_hash", ""),
           "served_model": getattr(out, "served_model", "")}
    return make_receipt({"prompt": prompt, "system": system,
                         "max_new_tokens": max_tokens,
                         "temperature": temperature, "seed": seed},
                        gen, out.model_ref)


def openai_embeddings(
        req: dict, *, providers_registry, urllib_module, resolve_credential):
    """Route POST /v1/embeddings to an embeddings-capable hosted provider."""
    model = str(req.get("model", ""))
    name = model.split(":", 1)[0] or "openai"
    spec = providers_registry.get(name)
    if spec is None or getattr(spec, "local", False):
        return {"error": {"message": f"no hosted embeddings provider '{name}'; "
                          "name one from GET /api/endpoints",
                          "type": "invalid_request_error"}}, 400
    key = resolve_credential(spec.api_key_env or "")
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
    request = urllib_module.request.Request(
        spec.base_url.rstrip("/") + "/embeddings",
        data=json.dumps(fwd).encode(), method="POST", headers=headers)
    try:
        with urllib_module.request.urlopen(request, timeout=60) as r:
            return json.loads(r.read() or b"{}"), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read() or b"{}"), e.code
        except Exception:
            return {"error": {"message": f"provider returned {e.code}"}}, e.code
    except Exception as e:
        return {"error": {"message": f"embeddings upstream unreachable: "
                          f"{type(e).__name__}"}}, 502


def openai_chat(
        req: dict, serve_url: str, credential_bindings=None, *,
        flatten_messages, resolve_proposer, get_router_stats, chat_receipt):
    """Return one routed completion plus its receipt and provenance."""
    system, prompt = flatten_messages(req.get("messages", []))
    if not prompt:
        return {"error": {"message": "messages must include a user turn",
                          "type": "invalid_request_error"}}, 400, None, None, None
    temperature = float(req.get("temperature", 0.0))
    max_tokens = int(req.get("max_tokens", 512))
    seed = int(req.get("seed", 0))
    candidates = [m.strip() for m in str(req.get("model", "")).split(",")
                  if m.strip()] or [""]
    adaptive = bool(req.get("adaptive"))
    routing = None
    if adaptive:
        rs = get_router_stats()
        requested = [c or "flywheel" for c in candidates]
        routing = {"adaptive": True, "requested": requested,
                   "scores": {c: round(rs.score(c), 4) for c in requested},
                   "circuit_open": [c for c in requested
                                    if rs.is_circuit_open(c)]}
        candidates = rs.order(candidates)
        routing["order"] = [c or "flywheel" for c in candidates]
    tried, last_err, last_code = [], "no provider resolved", 502
    resolution_failures = []
    for cand in candidates:
        t0 = time.time()
        proposer, err, code = (
            resolve_proposer(cand, serve_url) if credential_bindings is None
            else resolve_proposer(cand, serve_url, credential_bindings))
        if err is not None:
            last_err, last_code = err, code
            tried.append((cand or "flywheel") + ": unavailable")
            resolution_failures.append(
                {"provider": cand or "flywheel", "reason": err})
            continue
        try:
            out = proposer.generate(prompt, seed=seed, temperature=temperature,
                                    max_new_tokens=max_tokens, system=system)
        except Exception as e:
            last_err, last_code = f"provider call failed: {e}", 502
            tried.append((cand or "flywheel") + ": error")
            if adaptive:
                get_router_stats().record(
                    cand or "flywheel", False, time.time() - t0)
            continue
        if adaptive:
            get_router_stats().record(
                cand or "flywheel", True, time.time() - t0)
        receipt = chat_receipt(prompt, system, max_tokens, temperature, seed, out)
        receipt["routed_via"] = cand or "flywheel"
        if routing is not None:
            receipt["routing"] = routing
        if resolution_failures:
            receipt["resolution_failures"] = resolution_failures
        if tried:
            receipt["failover_from"] = tried
        body = {"id": "chatcmpl-" + receipt["receipt_id"],
                "object": "chat.completion", "created": int(time.time()),
                "model": out.model_ref,
                "choices": [{"index": 0,
                             "message": {"role": "assistant",
                                         "content": out.text},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": len(prompt.split()),
                          "completion_tokens": len(str(out.text).split()),
                          "total_tokens": len(prompt.split())
                          + len(str(out.text).split())},
                "x_receipt": receipt}
        return body, 200, receipt, out.text, out.model_ref
    detail = "; ".join(tried) if tried else last_err
    return {"error": {"message": f"all providers failed ({detail})",
                      "type": "api_error"},
            "failover_from": tried}, last_code, None, None, None


def openai_models(*, unified_roster) -> dict:
    """GET /v1/models as OpenAI model objects."""
    roster = unified_roster()
    data = [{"id": "flywheel", "object": "model", "created": 0,
             "owned_by": "flywheel"}]
    for e in roster.get("endpoints", []):
        data.append({"id": e["name"], "object": "model", "created": 0,
                     "owned_by": e.get("source", "flywheel")})
    return {"object": "list", "data": data}
