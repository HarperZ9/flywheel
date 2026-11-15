"""gateway_embeddings.py -- POST /v1/embeddings, forwarded to a hosted provider and recorded.

The route forwards an OpenAI embeddings request to the provider the `model`
field names (`openai`, or `openai:text-embedding-3-small`), with the
provider's key from the environment. Flywheel computes no embeddings.

Until 2.0.0's fifth review round this route was outside the gateway ledger: a
hosted provider was contacted and billed, and nothing recorded it. It now
records through the same object as every other provider route
(`gateway_account.Call`):

  endpoint_call_started   before the provider is contacted: the endpoint,
                          `interface` `openai-embeddings`, the hash of the
                          forwarded request, `key` `owner` (the route takes
                          the gateway token only) and the call id
  endpoint_call           the hash of the response body, `model_ref`, and the
                          provider's `usage.prompt_tokens` when it sent one
  endpoint_call_failed    a provider error status (`upstream_status_N`), or a
                          provider that could not be reached (`upstream_error`)

With no ledger to write to, the call is refused with 503 and nothing is sent
(gateway_ledger_gate), as on the other provider routes. A request refused
before contact (an unknown provider, a missing credential, text that cannot be
hashed) leaves no entry.
"""
from __future__ import annotations

import hashlib
import json
import urllib.error

INTERFACE = "openai-embeddings"


def _refused(message: str, status: int = 400) -> tuple:
    return {"error": {"message": message, "type": "invalid_request_error"}}, status


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def openai_embeddings(req: dict, *, providers_registry, urllib_module, resolve_credential,
                      ledger_of) -> tuple:
    """Route POST /v1/embeddings to an embeddings-capable hosted provider. (body, status)."""
    from .gateway_account import Call
    from .gateway_ledger_gate import required, typed_refusal
    from .gateway_turn import UpstreamFailed
    model = str(req.get("model", ""))
    name = model.split(":", 1)[0] or "openai"
    spec = providers_registry.get(name)
    if spec is None or getattr(spec, "local", False):
        return _refused(f"no hosted embeddings provider '{name}'; name one from "
                        "GET /api/endpoints")
    key = resolve_credential(spec.api_key_env or "")
    if spec.api_key_env and not key:
        return _refused(f"missing credential for '{name}'")
    fwd = dict(req)
    fwd.pop("adaptive", None)
    if ":" in model:
        fwd["model"] = model.split(":", 1)[1]
    try:
        data = json.dumps(fwd).encode()
        asked = _sha(json.dumps(fwd, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    except (UnicodeError, TypeError, ValueError):
        return _refused("the request holds text that is not valid UTF-8, so the call cannot "
                        "be recorded; nothing was sent upstream")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib_module.request.Request(
        spec.base_url.rstrip("/") + "/embeddings", data=data, method="POST", headers=headers)
    try:
        call = Call(required(ledger_of), {"endpoint": name, "interface": INTERFACE,
                                          "prompt_sha": asked, "key": "owner"})
    except Exception as exc:    # noqa: BLE001 - no ledger: the typed 503, nothing sent
        refusal = typed_refusal(exc)
        if refusal is None:
            raise
        return refusal

    def send():
        try:
            with urllib_module.request.urlopen(request, timeout=60) as response:
                return response.status, response.read() or b"{}"
        except urllib.error.HTTPError as error:
            return error.code, error.read() or b"{}"
    try:
        status, raw = call.reach(send)
    except UpstreamFailed as failed:    # the started entry could not be written: not sent
        return {"error": {"message": str(failed), "type": "server_error",
                          "code": failed.reason}}, failed.status
    except Exception as exc:    # noqa: BLE001 - the provider could not be reached
        call.end("endpoint_call_failed", "upstream_error", {
            "reason": "upstream_error", "error": type(exc).__name__})
        return {"error": {"message": f"embeddings upstream unreachable: "
                          f"{type(exc).__name__}"}}, 502
    try:
        body = json.loads(raw)
    except ValueError:
        body = None
    if not 200 <= status < 300 or not isinstance(body, dict):
        reason = f"upstream_status_{status}" if not 200 <= status < 300 else "malformed_reply"
        call.end("endpoint_call_failed", reason, {"reason": reason})
        if isinstance(body, dict):
            return body, status
        return {"error": {"message": f"provider returned {status}"}}, status if (
            not 200 <= status < 300) else 502
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    counted = usage.get("prompt_tokens")
    sha = _sha(raw)
    call.end("endpoint_call", sha, {
        "model_ref": f"{name}:{fwd.get('model') or ''}", "response_sha": sha,
        "usage_reported": type(counted) is int,
        **({"input_tokens": counted} if type(counted) is int else {})})
    return body, status
