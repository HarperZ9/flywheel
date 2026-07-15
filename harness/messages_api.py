"""messages_api.py — Anthropic Messages-API facade with a receipt per turn.

The category-capture feature (dive F1): point ANY agent CLI that speaks the
Anthropic Messages API at the local harness. Ollama gives local compatibility;
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


def make_receipt(req_params: dict, gen: dict, served_ref: str,
                 weights_sha256: str = "") -> dict:
    """A per-turn receipt binding request ⊕ prompt ⊕ model ⊕ response (⊕ weights).
    The receipt_id is content-addressed, so identical turns share an id
    (idempotent), and any change to request or response changes it.

    When a weights fingerprint is supplied it is folded into the receipt_id
    PREIMAGE (not merely stored alongside), so tampering with it breaks the
    recompute and two weight files that share a coarse model_ref but differ in
    artifact hash yield DISTINCT receipt_ids -- the provenance field is genuinely
    re-checkable, never a write-only claim. Omitted (default) -> byte-identical to
    the prior no-fingerprint receipt."""
    request_hash = _h(json.dumps(
        {k: req_params.get(k) for k in ("prompt", "system", "max_new_tokens",
                                        "temperature", "seed")}, sort_keys=True))[:16]
    response_hash = _h(gen.get("text", ""))[:16]
    prompt_hash = gen.get("prompt_hash", _h(req_params.get("prompt", ""))[:16])
    parts = [request_hash, prompt_hash, served_ref, response_hash]
    if weights_sha256:
        parts.append(weights_sha256)
    receipt_id = _h("|".join(parts))[:20]
    receipt = {"receipt_id": receipt_id, "request_hash": request_hash,
               "response_hash": response_hash, "prompt_hash": prompt_hash,
               "model_ref": served_ref, "seed": gen.get("seed", req_params.get("seed", 0))}
    if weights_sha256:
        receipt["weights_sha256"] = weights_sha256
    # the model the provider SAYS it served: if present and it is not the
    # requested model (embedded in served_ref), the receipt names the swap
    # rather than trusting the requested identity
    served_model = str(gen.get("served_model", ""))
    if served_model:
        requested_model = served_ref.split(":", 1)[-1]
        if served_model != served_ref and served_model != requested_model:
            receipt["model_mismatch"] = {"requested": served_ref,
                                         "served": served_model}
    return receipt


def translate_response(gen: dict, req_params: dict, served_ref: str) -> dict:
    """Our /generate output -> Anthropic Messages response, with the receipt.
    Response model echoes the REQUESTED name (client contract) but the receipt
    records the true served_ref (provenance)."""
    receipt = make_receipt(req_params, gen, served_ref)
    text = gen.get("text", "")
    return {
        "id": f"msg_{receipt['receipt_id']}",
        "type": "message",
        "role": "assistant",
        "model": req_params.get("requested_model") or served_ref,
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": len(req_params.get("prompt", "").split()),
                  "output_tokens": len(text.split())},
        "x_receipt": receipt,          # surfaced as the X-Receipt-Id header by serve.py
    }


def error_response(message: str, *, etype: str = "invalid_request_error") -> dict:
    """A TYPED error — never a 200-with-nothing (the serve failure the dive named)."""
    return {"type": "error", "error": {"type": etype, "message": message}}
