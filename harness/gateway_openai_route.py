"""Provider and OpenAI-compatible route implementations for the gateway.

`harness.gateway` keeps the public wrappers, so callers monkeypatch names there."""
from __future__ import annotations

import json
import math
import time
import urllib.error
from .model_selection_required import model_selection_response


def _route_block(entry: dict, roster: dict, endpoint: str) -> tuple[dict, int] | None:
    if entry.get("credential") == "absent":
        return {"error": f"endpoint {endpoint!r} has no credential present; set its API "
                f"key in the environment (presence only, never read here)",
                "credential": "absent"}, 400
    if endpoint != "claude-cli":
        return None
    usable = roster.get("usable_names")
    not_usable = isinstance(usable, list) and endpoint not in usable
    if (entry.get("account_authenticated") is not True
            or entry.get("receipt_capable") is not True or not_usable):
        return {"error": "Claude Code account sign-in required before routing claude-cli",
                "credential": entry.get("credential", ""),
                "account_state": entry.get("account_state", "unknown")}, 403
    return None


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
    blocked = _route_block(entry, roster, endpoint)
    if blocked is not None:
        return blocked
    try:
        from harness.endpoint_registry import make_endpoint_proposer
    except Exception:
        from endpoint_registry import make_endpoint_proposer
    try:
        kw = {"model": model} if model else {}
        prop = make_endpoint_proposer(endpoint, ledger=router_ledger(), **kw)
    except Exception as e:
        if (typed := model_selection_response(e)) is not None:
            return typed
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
        blocked = _route_block(entry, roster, name)
        if blocked is not None:
            return None, blocked[0]["error"], blocked[1]
    try:
        from harness.endpoint_registry import make_authorized_endpoint_proposer, make_endpoint_proposer
    except Exception:
        from endpoint_registry import make_authorized_endpoint_proposer, make_endpoint_proposer
    try:
        factory = (make_endpoint_proposer if credential_bindings is None else
                   make_authorized_endpoint_proposer)
        kwargs = {"model": sub, "ledger": router_ledger()}
        if credential_bindings is not None:
            kwargs["credential_bindings"] = credential_bindings
        return factory(name, **kwargs), None, 200
    except Exception as e:
        if (typed := model_selection_response(e)) is not None:
            return None, typed[0], typed[1]
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


def _finite_temperature(raw):
    """Return a finite float temperature, or None for a malformed value."""
    if isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _adaptive_order(candidates, rs):
    """Order candidates by router score and describe the routing decision."""
    requested = [c or "flywheel" for c in candidates]
    routing = {"adaptive": True, "requested": requested,
               "scores": {c: round(rs.score(c), 4) for c in requested},
               "circuit_open": [c for c in requested if rs.is_circuit_open(c)]}
    ordered = rs.order(candidates)
    routing["order"] = [c or "flywheel" for c in ordered]
    return ordered, routing


def _completion_body(receipt, out, prompt):
    """Build the OpenAI-shaped chat completion body for one provider reply."""
    prompt_tokens = len(prompt.split())
    completion_tokens = len(str(out.text).split())
    return {"id": "chatcmpl-" + receipt["receipt_id"],
            "object": "chat.completion", "created": int(time.time()),
            "model": out.model_ref,
            "choices": [{"index": 0,
                         "message": {"role": "assistant", "content": out.text},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": prompt_tokens,
                      "completion_tokens": completion_tokens,
                      "total_tokens": prompt_tokens + completion_tokens},
            "x_receipt": receipt}


def _whole_number(raw):
    """Return int(raw), or None for a boolean, malformed or non-finite value."""
    if isinstance(raw, bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError, OverflowError):
        return None


def _chat_params(req, prompt):
    """Return (temperature, max_tokens, seed) and the first problem, if any."""
    params = (_finite_temperature(req.get("temperature", 0.0)),
              _whole_number(req.get("max_tokens", 512)),
              _whole_number(req.get("seed", 0)))
    if not prompt:
        return params, "messages must include a user turn"
    for name, value in zip(("temperature", "max_tokens", "seed"), params):
        if value is None:
            kind = "a finite number" if name == "temperature" else "an integer"
            return params, f"{name} must be {kind}"
    return params, None


def _all_failed(tried, last_err):
    """Build the error body returned when every candidate provider failed."""
    detail = "; ".join(tried) if tried else last_err
    return {"error": {"message": f"all providers failed ({detail})",
                      "type": "api_error"},
            "failover_from": tried}


def openai_chat(
        req: dict, serve_url: str, credential_bindings=None, *,
        flatten_messages, resolve_proposer, get_router_stats, chat_receipt):
    """Return one routed completion plus its receipt and provenance."""
    system, prompt = flatten_messages(req.get("messages", []))
    (temperature, max_tokens, seed), problem = _chat_params(req, prompt)
    if problem:
        return {"error": {"message": problem, "type": "invalid_request_error"}
                }, 400, None, None, None
    candidates = [m.strip() for m in str(req.get("model", "")).split(",")
                  if m.strip()] or [""]
    adaptive = bool(req.get("adaptive"))
    candidates, routing = (_adaptive_order(candidates, get_router_stats())
                           if adaptive else (candidates, None))
    tried, resolution_failures, last_err, last_code = [], [], "no provider resolved", 502
    for cand in candidates:
        t0 = time.time()
        proposer, err, code = (
            resolve_proposer(cand, serve_url) if credential_bindings is None
            else resolve_proposer(cand, serve_url, credential_bindings))
        if err is not None:
            if isinstance(err, dict):
                return err, code, None, None, None
            last_err, last_code = err, code
            tried.append((cand or "flywheel") + ": unavailable")
            resolution_failures.append(
                {"provider": cand or "flywheel", "reason": err})
            continue
        try:
            out = proposer.generate(prompt, seed=seed, temperature=temperature,
                                    max_new_tokens=max_tokens, system=system)
        except Exception as e:
            out, last_err, last_code = None, f"provider call failed: {e}", 502
            tried.append((cand or "flywheel") + ": error")
        if adaptive:
            get_router_stats().record(
                cand or "flywheel", out is not None, time.time() - t0)
        if out is None:
            continue
        receipt = chat_receipt(prompt, system, max_tokens, temperature, seed, out)
        receipt["routed_via"] = cand or "flywheel"
        for key, value in (("routing", routing),
                           ("resolution_failures", resolution_failures),
                           ("failover_from", tried)):
            if value:
                receipt[key] = value
        body = _completion_body(receipt, out, prompt)
        return body, 200, receipt, out.text, out.model_ref
    return _all_failed(tried, last_err), last_code, None, None, None


def openai_models(*, unified_roster) -> dict:
    """GET /v1/models as OpenAI model objects."""
    roster = unified_roster()
    data = [{"id": "flywheel", "object": "model", "created": 0,
             "owned_by": "flywheel"}]
    for e in roster.get("endpoints", []):
        data.append({"id": e["name"], "object": "model", "created": 0,
                     "owned_by": e.get("source", "flywheel")})
    return {"object": "list", "data": data}
