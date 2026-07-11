"""endpoint_registry.py -- one roster of EVERY provider, one bridge to the
verified accept path. The superapp's universal-router foundation (increment 3).

Two provider abstractions existed side by side: `providers.REGISTRY` (OpenAI-
shaped endpoints -> `make_proposer` -> the verified accept path) and `endpoints.py`'s
rich NATIVE backends (Anthropic, Gemini, subscription-CLI tiers, OpenCode) that the
local agent used but that never reached the harness's oracle+witness+receipt path.
This unifies them: `BackendProposer` bridges ANY `.chat` backend into a Proposer,
so every provider -- local serve/ollama, OpenAI-compat, native Anthropic/Gemini,
subscription CLI -- feeds the SAME verified loop, and `unified_roster()` enumerates
them all with credential-PRESENCE booleans (env presence only, never a value).

The differentiator over every other router (OpenRouter, LiteLLM, ...): they route;
this routes AND verifies. Provider provenance rides `model_ref` into every receipt,
and the accept authority stays the oracle -- the provider only proposes.
"""
from __future__ import annotations

import os

from . import providers
from .proposer import Proposer, ProposerOutput, prompt_hash


class BackendProposer:
    """Adapt an endpoints.py backend (`.chat(messages, *, system, max_tokens,
    temperature, seed) -> {text, model_ref, seed}`) to the Proposer protocol, so a
    native Anthropic/Gemini/CLI/OpenCode backend feeds the same accept path the
    OpenAI-shaped proposers reach. `extract` strips code fences for the code loop
    (default); set False for general routing where prose must survive."""

    def __init__(self, backend, *, model_ref: str | None = None, extract: bool = True):
        self.backend = backend
        self.model_ref = model_ref or getattr(backend, "name", "backend")
        self._extract = extract

    def generate(self, prompt: str, *, seed: int, temperature: float,
                 max_new_tokens: int, system: str = "") -> ProposerOutput:
        out = self.backend.chat([{"role": "user", "content": prompt}], system=system,
                                max_tokens=max_new_tokens, temperature=temperature, seed=seed)
        text = out.get("text", "") if isinstance(out, dict) else str(out)
        if self._extract:
            from .extract import extract_code
            text = extract_code(text)
        return ProposerOutput(
            text=text, model_ref=(out.get("model_ref", self.model_ref) if isinstance(out, dict) else self.model_ref),
            seed=(out.get("seed", seed) if isinstance(out, dict) else seed),
            prompt_hash=prompt_hash(prompt), cache="miss")


# Native (non-OpenAI-shaped) endpoints endpoints.py serves directly.
# (name, kind, key_env, host, default_model). CLI tiers use their own login.
_NATIVE = [
    ("anthropic", "anthropic", "ANTHROPIC_API_KEY", "api.anthropic.com", "claude-sonnet-5"),
    ("gemini", "gemini", "GEMINI_API_KEY", "generativelanguage.googleapis.com", "gemini-2.5-flash"),
    ("claude-cli", "cli", "", "local-cli", "claude"),
    ("codex-cli", "cli", "", "local-cli", "codex"),
    ("opencode", "opencode", "OPENCODE_PASSWORD", "local", "opencode"),
]


def _credential(key_env: str, *, local: bool, kind: str = "") -> str:
    """PRESENCE only -- never the value. local -> 'local-none'; cli -> 'cli-auth'
    (its own login); else present/absent by whether the env var is set."""
    if local:
        return "local-none"
    if kind == "cli":
        return "cli-auth"
    return "present" if os.environ.get(key_env or "") else "absent"


def _host(url: str) -> str:
    if not url:
        return ""
    return url.split("://", 1)[-1].split("/", 1)[0]


def unified_roster() -> dict:
    """Every endpoint in one list, with credential-presence (never a value). Every
    entry is receipt_capable: it can be turned into a verified Proposer."""
    rows = []
    for name, spec in sorted(providers.REGISTRY.items()):
        rows.append({"name": name, "kind": "openai-compat", "local": bool(spec.local),
                     "credential": _credential(spec.api_key_env, local=bool(spec.local)),
                     "host": _host(spec.base_url), "default_model": spec.default_model,
                     "receipt_capable": True, "source": "providers"})
    rows.append({"name": "serve", "kind": "serve", "local": True, "credential": "local-none",
                 "host": "127.0.0.1:8765", "default_model": "14b-cpt",
                 "receipt_capable": True, "source": "builtin"})
    for name, kind, key_env, host, dm in _NATIVE:
        rows.append({"name": name, "kind": kind, "local": kind in ("cli", "opencode"),
                     "credential": _credential(key_env, local=False, kind=kind),
                     "host": host, "default_model": dm,
                     "receipt_capable": True, "source": "endpoints"})
    usable = [r for r in rows if r["credential"] in ("present", "cli-auth", "local-none")]
    return {"schema": "flywheel.endpoint-roster/v1", "n_endpoints": len(rows),
            "n_usable": len(usable), "usable_names": sorted(r["name"] for r in usable),
            "endpoints": rows,
            "note": "credential is PRESENCE only, never a value; every endpoint feeds the "
                    "SAME verified accept path -- the oracle disposes, the provider proposes"}


def make_endpoint_proposer(name: str, *, model: str | None = None,
                           base_url: str | None = None, extract: bool = True) -> Proposer:
    """A verified Proposer for ANY endpoint. OpenAI-shaped + serve/stub go through
    providers.make_proposer; native Anthropic/Gemini are constructed and bridged;
    CLI/OpenCode come from the endpoints ladder (their own construction)."""
    if name in providers.REGISTRY or name in ("serve", "stub"):
        return providers.make_proposer(name, model=model, base_url=base_url)
    from . import endpoints
    if name == "anthropic":
        b = endpoints.AnthropicBackend(name="anthropic",
                                       base_url=base_url or "https://api.anthropic.com",
                                       model=model or "claude-sonnet-5")
        return BackendProposer(b, extract=extract)
    if name == "gemini":
        b = endpoints.GeminiBackend(name="gemini",
                                    base_url=base_url or "https://generativelanguage.googleapis.com/v1beta",
                                    model=model or "gemini-2.5-flash")
        return BackendProposer(b, extract=extract)
    # cli / opencode: pull the configured backend from the endpoints ladder
    for b in endpoints.build_endpoints(only_configured=False):
        if getattr(b, "name", None) == name:
            return BackendProposer(b, extract=extract)
    raise ValueError(f"unknown endpoint {name!r}; see unified_roster()['usable_names']")
