#!/usr/bin/env python3
"""determinism_baseline.py -- repeat-run digest baseline for a pinned rung.

`determinism_pins.py` pins what the server SAYS about how it will run a rung
(runtime, sampler, num_ctx, kv_cache_type). None of that proves the server
answers the same fixed prompt the same way twice under those pins. This
module asks that question directly: call `/api/generate` at the pinned
sampler tuple N times for a short fixed prompt, and record the sha256 of
each response text verbatim. Equal digests across N runs are recorded as
`"witnessed": true`; unequal digests are recorded as `"witnessed": false`
with every digest kept, never collapsed or hidden. A baseline that shows
nondeterminism is not a failed baseline, it is the honest result.

Split out of `determinism_pins.py` to keep both files under the file-length
gate; this module imports the one sampler tuple and the injectable-fetch
default from there instead of repeating either.

Stdlib only.
"""
from __future__ import annotations

import hashlib

from determinism_pins import SAMPLER_TUPLE, _default_fetch

BASELINE_PROMPT = "Compute 17 * 23 and reply with only the number."


def _digest_of_text(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _one_rung_baseline(fetch, model: str, n: int, prompt: str) -> dict:
    digests = []
    for _ in range(n):
        payload = {"model": model, "prompt": prompt, "stream": False,
                   "options": dict(SAMPLER_TUPLE)}
        result = fetch("/api/generate", payload) or {}
        digests.append(_digest_of_text(result.get("response")))
    return {"model": model, "n": n, "digests": digests,
            "witnessed": bool(digests) and len(set(digests)) == 1}


def baseline(base_url: str, models: list[str], n: int = 3,
            prompt: str = BASELINE_PROMPT, fetch=None) -> dict:
    """Per rung, n calls to /api/generate at the pinned sampler, digested.

    Returns a dict keyed by model name so the CLI can drop it straight under
    the pins document's "baselines" key without reshaping it.
    """
    if n < 1:
        raise ValueError("n must be >= 1")
    fetch = fetch or _default_fetch(base_url)
    return {model: _one_rung_baseline(fetch, model, n, prompt) for model in models}
