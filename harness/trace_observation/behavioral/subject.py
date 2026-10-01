"""subject.py -- the model under a behavioral test, as a plain callable.

A subject takes a prompt and a seed and returns text. The behavioral suite
needs nothing else, so the same design runs on a closed model's documented API
(through a caller-supplied function holding the caller's own key), on a local
model, or on recorded responses. FixtureSubject replays recorded responses and
refuses an unrecorded prompt, so a test cannot pass by silently generating.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request


def prompt_key(prompt: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}\n{prompt}".encode("utf-8")).hexdigest()


class FixtureSubject:
    def __init__(self, table: dict, name: str = "fixture") -> None:
        self.table, self.name = table, name

    def __call__(self, prompt: str, *, seed: int = 1) -> str:
        k = prompt_key(prompt, seed)
        if k not in self.table:
            raise KeyError(f"{self.name}: no recorded response for prompt key {k[:12]}")
        return self.table[k]


class RecordingSubject:
    """Wraps a live subject and keeps every response for a fixture file."""

    def __init__(self, inner) -> None:
        self.inner, self.table = inner, {}

    def __call__(self, prompt: str, *, seed: int = 1) -> str:
        out = self.inner(prompt, seed=seed)
        self.table[prompt_key(prompt, seed)] = out
        return out


class OllamaSubject:
    """A local model through Ollama's /api/generate with its own chat template."""

    def __init__(self, model: str, url: str = "http://localhost:11434/api/generate",
                 num_predict: int = 256, timeout: float = 120.0) -> None:
        self.model, self.url, self.num_predict, self.timeout = model, url, num_predict, timeout

    def __call__(self, prompt: str, *, seed: int = 1) -> str:
        if seed == 0:
            raise ValueError("seed 0 is unseeded on Ollama; use a nonzero seed")
        body = {"model": self.model, "prompt": prompt, "stream": False,
                "options": {"temperature": 0, "seed": seed, "num_predict": self.num_predict}}
        req = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 -- local server
            return json.loads(resp.read()).get("response", "")
