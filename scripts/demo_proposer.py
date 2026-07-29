"""demo_proposer.py -- OllamaProposer: the .generate() harness/pool.py wants.

The exact contract, read from harness/pool.py's `fill`, not assumed:

    try:
        res = proposer.generate(prompt, seed=seed, temperature=temp,
                                max_new_tokens=max_new)
        text = res.text if isinstance(res.text, str) else str(res.text)
    except Exception as e:
        slots.append({... "candidate_sha256": None, "error": ...})
        continue

Only a RAISED exception lands in that except block. A `.text` of None does
NOT: `str(None)` is the four-character string "None", which is not a string
instance check failure, so `fill` would happily digest and cache "None" as a
real candidate and never touch the error path at all. So this proposer raises
`OllamaGenerationError` on every failure -- network, timeout, non-200, or a
response body with no string "response" field -- rather than returning an
object whose `.text` is None, because that is the only path pool.fill's own
code actually treats as a harness-attributed failure.

stdlib only. The one HTTP call goes through an injectable `fetch(request,
timeout=...) -> response`, defaulting to urllib.request.urlopen, so tests
never touch the network (mirrors the `fetch(path, payload=None)` seam already
used in scripts/determinism_pins.py, adapted here to a single POST call).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULT_HOST = "127.0.0.1:11434"
GENERATE_PATH = "/api/generate"
# 600s: a cold 32B load outruns 30s and would read as a mechanical failure.
# scripts/determinism_pins.py already learned this the same way.
TIMEOUT_SECONDS = 600


class OllamaGenerationError(RuntimeError):
    """Ollama refused, errored, timed out, or returned no usable text."""


class GenerationResult:
    """Just enough to match what pool.fill reads: a `.text` attribute."""
    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


def default_base_url(host: str | None = None) -> str:
    """OLLAMA_HOST, defaulted, with a scheme. Never a literal drive path."""
    host = (host or os.environ.get("OLLAMA_HOST", "").strip() or DEFAULT_HOST)
    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")
    return f"http://{host}".rstrip("/")


class OllamaProposer:
    """Talks to one live Ollama server's /api/generate for one model."""

    def __init__(self, model: str, host: str | None = None, fetch=None) -> None:
        self.model = model
        self.base_url = default_base_url(host)
        # fetch(request, timeout=...) -> a urlopen()-shaped response (`.status`,
        # `.read()`, usable as a context manager). Tests inject a fake here.
        self._fetch = fetch or urllib.request.urlopen

    def generate(self, prompt: str, *, seed: int, temperature: float,
                 max_new_tokens: int) -> GenerationResult:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "seed": seed,
                "temperature": temperature,
                "num_predict": max_new_tokens,
            },
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + GENERATE_PATH, data=body, method="POST",
            headers={"Content-Type": "application/json"})

        try:
            with self._fetch(request, timeout=TIMEOUT_SECONDS) as response:
                raw = response.read()
                status = getattr(response, "status", 200)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            raise OllamaGenerationError(
                f"ollama {GENERATE_PATH} returned HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise OllamaGenerationError(
                f"could not reach ollama at {self.base_url}: {e.reason}") from e
        except TimeoutError as e:
            raise OllamaGenerationError(
                f"ollama {GENERATE_PATH} timed out after "
                f"{TIMEOUT_SECONDS}s") from e

        if status != 200:
            raise OllamaGenerationError(
                f"ollama {GENERATE_PATH} returned HTTP {status}")

        try:
            doc = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise OllamaGenerationError(
                f"ollama {GENERATE_PATH} returned a non-JSON body: {e}") from e

        if doc.get("error"):
            raise OllamaGenerationError(
                f"ollama {GENERATE_PATH} reported an error: {doc['error']}")

        text = doc.get("response")
        if not isinstance(text, str):
            raise OllamaGenerationError(
                "ollama {} response had no string 'response' field: {!r}"
                .format(GENERATE_PATH, doc)[:500])
        return GenerationResult(text)
