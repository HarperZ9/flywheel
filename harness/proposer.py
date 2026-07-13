"""proposer.py — model-agnostic proposer adapter (HARNESS.md "the model is cheap
and replaceable").

The loop never calls a model directly; it calls a Proposer. M0's serve.py is one
implementation. A stub lets the loop run with zero GPU. An enterprise adapter
targets the opaque inference boundary. The accept path (oracle + witness) is
identical regardless of which proposer produced the candidate — that is the
local-vs-enterprise observation point.
"""
from __future__ import annotations
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Protocol
import urllib.request
import urllib.error


@dataclass
class ProposerOutput:
    text: str
    model_ref: str
    seed: int
    prompt_hash: str
    cache: str


class Proposer(Protocol):
    model_ref: str

    def generate(self, prompt: str, *, seed: int, temperature: float,
                 max_new_tokens: int, system: str = "") -> ProposerOutput: ...


def prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class StubProposer:
    def __init__(self, canned: str, model_ref: str = "stub"):
        self._canned = canned
        self.model_ref = model_ref

    def generate(self, prompt: str, *, seed: int, temperature: float,
                 max_new_tokens: int, system: str = "") -> ProposerOutput:
        return ProposerOutput(
            text=self._canned, model_ref=self.model_ref,
            seed=seed, prompt_hash=prompt_hash(prompt), cache="stub")


class ServeProposer:
    def __init__(self, base_url: str = "http://127.0.0.1:8765",
                 model_ref: str = "serve"):
        self.base_url = base_url.rstrip("/")
        self.model_ref = model_ref

    def generate(self, prompt: str, *, seed: int, temperature: float,
                 max_new_tokens: int, system: str = "") -> ProposerOutput:
        body = json.dumps({
            "prompt": prompt, "seed": seed, "temperature": temperature,
            "max_new_tokens": max_new_tokens, "system": system,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/generate", data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            obj = json.loads(r.read())
        from .extract import extract_code
        return ProposerOutput(
            text=extract_code(obj["text"]),   # strip fences/prose -> runnable candidate
            model_ref=obj.get("model_ref", self.model_ref),
            seed=obj.get("seed", seed), prompt_hash=obj.get("prompt_hash", prompt_hash(prompt)),
            cache=obj.get("cache", "miss"))


class EnterpriseProposer:
    def __init__(self, base_url: str | None = None, model: str | None = None,
                 api_key_env: str = "OPENAI_API_KEY", model_ref: str = "enterprise"):
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL",
                          "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.api_key_env = api_key_env
        self.model_ref = f"{model_ref}:{self.model}"

    def generate(self, prompt: str, *, seed: int, temperature: float,
                 max_new_tokens: int, system: str = "") -> ProposerOutput:
        try:
            from .keychain import resolve_credential
            key = resolve_credential(self.api_key_env)
        except Exception:
            key = os.environ.get(self.api_key_env, "")
        msgs = ([{"role": "system", "content": system}] if system else []) \
            + [{"role": "user", "content": prompt}]
        body = json.dumps({
            "model": self.model, "messages": msgs,
            "temperature": temperature, "max_tokens": max_new_tokens,
            "seed": seed,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=300) as r:
            obj = json.loads(r.read())
        from .extract import extract_code
        text = extract_code(obj["choices"][0]["message"]["content"])  # enterprise models fence too
        return ProposerOutput(
            text=text, model_ref=self.model_ref,
            seed=seed, prompt_hash=prompt_hash(prompt), cache="miss")
