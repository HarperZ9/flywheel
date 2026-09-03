"""model_ollama.py: everything model_shim says to an ollama daemon.

Split out of model_shim.py (which holds the wire protocol and serving loop)
so each file stays under the repo's 300-line gate; the contract restated in
model_shim's docstring governs this module too. Two conversations live here:
the /api/generate completion POST and the /api/tags daemon-digest fetch a
model boundary receipt records.

UNTESTED-LIVE: as of this commit neither path has been exercised against a
running ollama instance (hardware gated). Both are stdlib urllib and are unit
tested with the network mocked at the urllib boundary, but no live call has
been made -- treat them as unverified until a hardware session confirms them
end-to-end.

Fail-closed everywhere: a connection failure, a non-2xx status, a malformed
body, or a response missing the expected field returns None (completion) or
{"status": "UNAVAILABLE"} (digest), never a fabricated value.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def ollama_request_body_bytes(model: str, prompt: str) -> bytes:
    """The exact JSON bytes `ollama_complete` POSTs to /api/generate. Pulled
    out as its own pure function so a model boundary receipt's
    `model.request_body_sha256` can be computed from the SAME construction
    the real POST uses (calling this twice with the same args is
    byte-identical, since json.dumps over a fixed-key-order dict literal is
    deterministic), rather than risking two code paths drifting apart."""
    return json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")


def ollama_complete(prompt: str, model: str, endpoint: str, timeout: float) -> str | None:
    """POST prompt to an ollama /api/generate endpoint. Returns the raw
    "response" field (not yet sanitized -- the caller sanitizes uniformly
    before writing to the socket), or None on any failure. UNTESTED-LIVE:
    see the module docstring. Never called during this repo's own test run.
    """
    url = endpoint.rstrip("/") + "/api/generate"
    body = ollama_request_body_bytes(model, prompt)
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        print(f"[model_shim] ollama request failed: {e!r}", file=sys.stderr)
        return None
    response = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(response, str):
        print(f"[model_shim] ollama response missing 'response' field: {payload!r}",
              file=sys.stderr)
        return None
    return response


def is_sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdefABCDEF" for c in value)


def fetch_ollama_daemon_digest(model: str, endpoint: str, timeout: float) -> dict:
    """GET <endpoint>/api/tags and extract the digest ollama declares for
    `model`, for the receipt's `model.daemon_digest` field.

    UNTESTED-LIVE (see the module docstring): the /api/tags response shape
    assumed here (`{"models": [{"name": ..., "digest": ...}, ...]}`, digest
    optionally prefixed `sha256:`) has not been confirmed against a running
    daemon; pin it during the hardware-gated live session the ollama path
    already needs. Fails closed to `{"status": "UNAVAILABLE"}` on ANY problem
    -- network failure, unexpected response shape, no matching model entry,
    or a digest that is not a well-formed 64-hex-char sha256 -- because a
    receipt claiming FETCHED must be right: "weights I could not identify" is
    honest where a guessed or malformed digest would not be. Even a FETCHED
    result only witnesses that the daemon reported this digest for this model
    name AT FETCH TIME; it is the daemon's own declaration about itself, not
    independently checked against the weights.
    """
    url = endpoint.rstrip("/") + "/api/tags"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            return {"status": "UNAVAILABLE"}
        for entry in models:
            if not isinstance(entry, dict) or entry.get("name") != model:
                continue
            digest = entry.get("digest")
            if not isinstance(digest, str):
                break
            if digest.startswith("sha256:"):
                digest = digest[len("sha256:"):]
            if is_sha256_hex(digest):
                return {"status": "FETCHED", "hex": digest.lower()}
            break
        return {"status": "UNAVAILABLE"}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError,
            AttributeError, TypeError) as e:
        print(f"[model_shim] daemon digest fetch failed: {e!r}", file=sys.stderr)
        return {"status": "UNAVAILABLE"}
