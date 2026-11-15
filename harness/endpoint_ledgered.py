"""endpoint_ledgered.py -- a proposer whose every provider call is in a ledger.

`LedgeredProposer` wraps any `Proposer` and records each `generate` in one
ledger, through the same accounting object the gateway's model interfaces use
(`gateway_account.Call`). The chat routes (/v1/chat/completions, /api/route)
and the gateway's agent runs reach providers through it.

One call leaves two entries, or none:

  endpoint_call_started   appended before the inner proposer runs: the endpoint,
                          the hash of the prompt and the call id. When it cannot
                          be appended, the inner proposer is not called.
  endpoint_call           the reply's hash, `model_ref` and `seed`, or
  endpoint_call_failed    when the inner proposer raised (`upstream_error`, with
                          the error's type) or returned text that cannot be
                          hashed (`malformed_reply`).

Before 2.0.0's fifth review round a provider error here left no entry at all,
although the provider had been contacted.

The started entry is written when `generate` hands the call to the inner
proposer, which is the last point this wrapper can see. An inner proposer that
fails before it opens a connection (a missing credential, for one) therefore
leaves a started entry and a failed entry for a call that reached no
provider. The record errs toward a call that was not made, never toward a
missing one.

A prompt that cannot be hashed is refused first, with no entry and no call.
The ledger holds commitments only: no prompt text, no reply text, no secret.
"""
from __future__ import annotations

from .proposer import Proposer, ProposerOutput, prompt_hash

FAILED = "endpoint_call_failed"


class LedgeredProposer:
    """Append tamper-evident endpoint-call commitments to one ledger."""

    def __init__(self, inner: Proposer, ledger, *, endpoint: str | None = None):
        self.inner = inner
        self.ledger = ledger
        self.model_ref = getattr(inner, "model_ref", endpoint or "endpoint")
        self.endpoint = endpoint or self.model_ref

    def generate(self, prompt: str, *, seed: int, temperature: float,
                 max_new_tokens: int, system: str = "") -> ProposerOutput:
        from .gateway_account import Call, encodable
        try:                    # before the provider is contacted: an unhashable prompt is not sent
            asked = prompt_hash(prompt)
        except UnicodeError as exc:
            raise ValueError("the prompt is not valid UTF-8 (a lone surrogate), so the call "
                             "cannot be recorded; nothing was sent upstream") from exc
        from .gateway_reach import route
        base = {"endpoint": self.endpoint, "prompt_sha": asked}
        if route():                     # the gateway route this call is made for
            base["route"] = route()
        call = Call(self.ledger, base)
        try:
            out = call.reach(lambda: self.inner.generate(
                prompt, seed=seed, temperature=temperature, max_new_tokens=max_new_tokens,
                system=system))
        except Exception as exc:
            if call.state == "contacted":       # the start is recorded: so is this end
                call.end(FAILED, "upstream_error", {"reason": "upstream_error",
                                                    "error": type(exc).__name__})
            raise
        text = out.text if isinstance(out.text, str) else str(out.text)
        if not encodable([text, out.model_ref, out.seed]):
            call.end(FAILED, "malformed_reply", {"reason": "malformed_reply"})
            raise UnicodeError("the reply holds text that is not valid UTF-8 (a lone "
                               "surrogate); it was recorded as a failed call and not served")
        resp_sha = prompt_hash(text)
        call.end("endpoint_call", resp_sha, {
            "model_ref": out.model_ref,        # provider provenance, not a secret
            "seed": out.seed, "response_sha": resp_sha})
        return out


def recorded(endpoint: str, request: bytes, send):
    """Run `send`, one model request made of the bytes `request`, as a ledger call when
    this process is a gateway; anywhere else just run it. Returns what `send` returns.

    For a model request that is not made through a proposer or a backend (the optional
    judge model of the pre-action monitor, for one). The entries carry the endpoint
    name, the hash of the request bytes and the hash of the reply bytes."""
    import hashlib

    from . import gateway_reach
    from .gateway_account import Call, contacting
    if not gateway_reach.enforced() or contacting() is not None:
        return send()
    base = {"endpoint": endpoint, "prompt_sha": hashlib.sha256(request).hexdigest()[:16]}
    if gateway_reach.route():
        base["route"] = gateway_reach.route()
    call = Call(gateway_reach.ledger(), base)
    try:
        out = call.reach(send)
    except Exception as exc:
        if call.state == "contacted":
            call.end(FAILED, "upstream_error", {"reason": "upstream_error",
                                                "error": type(exc).__name__})
        raise
    sha = hashlib.sha256(out if isinstance(out, bytes) else str(out).encode("utf-8",
                         "replace")).hexdigest()[:16]
    call.end("endpoint_call", sha, {"response_sha": sha})
    return out
