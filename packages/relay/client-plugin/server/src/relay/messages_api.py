"""messages_api.py — Anthropic Messages-API facade with a receipt per turn.

The category-capture feature (dive F1): point ANY agent CLI that speaks the
Anthropic Messages API at the local relay. Ollama gives local compatibility;
nobody gives compatibility PLUS a re-checkable receipt per agent turn. Every
response carries an X-Receipt-Id binding (request ⊕ prompt ⊕ model ⊕ response),
so an agent's whole trajectory is witnessed, not just served.

This module is the pure, model-independent core: request translation (Messages
-> our /generate params), response translation (our output -> Messages shape),
per-turn receipt, tier-name aliasing (claude-* never 404s), and TYPED errors
(never a 200-with-nothing — the exact serve failure the dive flagged). The HTTP
endpoint in serve.py calls these; the logic is falsifiable here without a GPU.
"""
from __future__ import annotations

import hashlib
import json

# claude-* / gpt-* names an agent client may request -> the locally served model.
# Aliasing means a client asking for a frontier model name gets served, never 404.
_TIER_PREFIXES = ("claude-opus", "claude-sonnet", "claude-haiku", "claude-fable",
                  "claude-3", "claude-", "gpt-", "o1", "o3")


def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def resolve_model(requested: str, served_ref: str) -> str:
    """Any recognized frontier tier name maps to the served local model. An
    unrecognized name passes through (explicit, so a typo is visible)."""
    r = (requested or "").lower()
    if any(r.startswith(p) for p in _TIER_PREFIXES):
        return served_ref
    return requested or served_ref


def _content_to_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text")
    return str(content or "")


def translate_request(body: dict) -> dict:
    """Anthropic Messages request -> our /generate params. Flattens the
    conversation into a single prompt; system stays separate. Raises ValueError
    on a malformed request (caller returns a typed error, never 200-empty)."""
    msgs = body.get("messages")
    if not isinstance(msgs, list) or not msgs:
        raise ValueError("messages must be a non-empty list")
    parts = []
    for m in msgs:
        role = m.get("role", "user")
        parts.append(f"{role}: {_content_to_text(m.get('content'))}")
    system = _content_to_text(body.get("system", ""))
    return {
        "prompt": "\n".join(parts),
        "system": system,
        "max_new_tokens": int(body.get("max_tokens", 512)),
        "temperature": float(body.get("temperature", 0.0)),
        "seed": int(body.get("seed", 0)),
        "requested_model": body.get("model", ""),
    }


# finish signals every backend reports for a length-truncated turn -> "max_tokens".
_LENGTH_STOPS = {"length", "max_tokens", "max_output_tokens"}


def _receipt_terms(request_hash: str, prompt_hash: str, served_ref: str,
                   response_hash: str) -> str:
    return "|".join([request_hash, prompt_hash, served_ref, response_hash])


def recompute_receipt_id(receipt: dict) -> str:
    """Re-derive a receipt_id from its own recorded components, so a stranger
    holding only the stored receipt (credo tenet 3) can re-check it."""
    return _h(_receipt_terms(receipt["request_hash"], receipt["prompt_hash"],
                             receipt["model_ref"], receipt["response_hash"]))[:20]


def make_receipt(req_params: dict, gen: dict, served_ref: str) -> dict:
    """A per-turn receipt binding request ⊕ prompt ⊕ model ⊕ response. The
    receipt_id is content-addressed, so identical turns share an id (idempotent),
    and any change to request or response changes it."""
    request_hash = _h(json.dumps(
        {k: req_params.get(k) for k in ("prompt", "system", "max_new_tokens",
                                        "temperature", "seed", "requested_model")},
        sort_keys=True))[:16]
    response_hash = _h(gen.get("text", ""))[:16]
    # prompt_hash is ALWAYS computed locally over the prompt we actually sent, so a
    # receipt holder can re-derive it. A server-attested prompt_hash (serve.py
    # templates the prompt server-side) is an attestation by the audited component,
    # so it is recorded beside ours, never in its place.
    prompt_hash = _h(req_params.get("prompt", ""))[:16]
    receipt_id = _h(_receipt_terms(request_hash, prompt_hash, served_ref, response_hash))[:20]
    # seed is the APPLIED seed. A backend that pins one reports it; a tier that
    # cannot (hosted APIs, the CLI tier) reports seed=None -> the turn is recorded
    # as non-reproducible rather than as seed 0, which would falsely imply a pin.
    seed = gen["seed"] if "seed" in gen else req_params.get("seed", 0)
    receipt = {"receipt_id": receipt_id, "request_hash": request_hash,
               "response_hash": response_hash, "prompt_hash": prompt_hash,
               "model_ref": served_ref, "seed": seed}
    server_ph = gen.get("prompt_hash")
    if server_ph is not None:
        receipt["server_prompt_hash"] = server_ph
        receipt["prompt_hash_match"] = (server_ph == prompt_hash)
    return receipt


def translate_response(gen: dict, req_params: dict, served_ref: str) -> dict:
    """Our /generate output -> Anthropic Messages response, with the receipt.
    Response model echoes the REQUESTED name (client contract) but the receipt
    records the true served_ref (provenance)."""
    receipt = make_receipt(req_params, gen, served_ref)
    text = gen.get("text", "")
    # A length-truncated turn is reported as max_tokens, never laundered into a
    # natural end_turn — a client must be able to tell a cut-off answer from a
    # finished one. The finish signal is witnessed in the receipt too.
    raw_stop = (gen.get("stop_reason") or "").lower()
    stop_reason = "max_tokens" if raw_stop in _LENGTH_STOPS else "end_turn"
    receipt["stop_reason"] = stop_reason
    return {
        "id": f"msg_{receipt['receipt_id']}",
        "type": "message",
        "role": "assistant",
        "model": req_params.get("requested_model") or served_ref,
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": len(req_params.get("prompt", "").split()),
                  "output_tokens": len(text.split())},
        "x_receipt": receipt,          # surfaced as the X-Receipt-Id header by serve.py
    }


def error_response(message: str, *, etype: str = "invalid_request_error") -> dict:
    """A TYPED error — never a 200-with-nothing (the serve failure the dive named)."""
    return {"type": "error", "error": {"type": etype, "message": message}}
