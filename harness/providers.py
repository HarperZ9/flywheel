"""providers.py — one line from any inference provider to a GATED proposer.

Capability-first agent harnesses (clawcodex and kin) ship long provider lists;
the protocol truth is that nearly all of them speak the OpenAI-compatible
chat/completions surface, which EnterpriseProposer already implements over
stdlib urllib. What was missing is the naming: a registry of known endpoints,
a factory, and the provider identity bound into `model_ref` — which already
flows into every ProofEnvelope and cache key, so every accepted result carries
WHICH provider proposed it as part of the receipt, for free.

The point is not the list. Any provider plugged in here proposes INTO the same
accept path: oracle-verify, witness re-check, grounding closure. A proposer
never gains authority by being famous; the criterion stays external (C2).

Fail closed: an unknown provider name raises with the known list — never a
silent default to somebody's cloud.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .proposer import EnterpriseProposer, Proposer, ServeProposer, StubProposer


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    base_url: str            # OpenAI-compatible /v1 root ("" -> env-supplied)
    api_key_env: str         # "" -> no key needed (local servers)
    default_model: str
    local: bool = False


# Known OpenAI-compatible endpoints. base_url/model are overridable per call;
# keys ALWAYS come from the environment (never hardcoded, never logged).
REGISTRY: dict[str, ProviderSpec] = {s.name: s for s in (
    ProviderSpec("codex", "https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-5.3-codex-spark"),
    ProviderSpec("openai", "https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-4o-mini"),
    ProviderSpec("deepseek", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY", "deepseek-chat"),
    ProviderSpec("groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", "llama-3.3-70b-versatile"),
    ProviderSpec("mistral", "https://api.mistral.ai/v1", "MISTRAL_API_KEY", "mistral-small-latest"),
    ProviderSpec("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "auto"),
    ProviderSpec("together", "https://api.together.xyz/v1", "TOGETHER_API_KEY", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    ProviderSpec("xai", "https://api.x.ai/v1", "XAI_API_KEY", "grok-3-mini"),
    ProviderSpec("ollama", "http://127.0.0.1:11434/v1", "", "qwen2.5-coder:14b", local=True),
    ProviderSpec("vllm", "http://127.0.0.1:8000/v1", "", "served-model", local=True),
    ProviderSpec("sglang", "http://127.0.0.1:30000/v1", "", "served-model", local=True),
    ProviderSpec("lmstudio", "http://127.0.0.1:1234/v1", "", "served-model", local=True),
    ProviderSpec("llamacpp", "http://127.0.0.1:8080/v1", "", "served-model", local=True),
    ProviderSpec("openai-compatible", "", "OPENAI_API_KEY", ""),  # bring-your-own base_url
)}

_BUILTIN = {"serve", "stub"}          # non-OpenAI-shaped proposers we also name


def provider_names() -> list[str]:
    return sorted(REGISTRY) + sorted(_BUILTIN)


def make_proposer(provider: str, *, model: str | None = None,
                  base_url: str | None = None, canned: str = "") -> Proposer:
    """One line from a provider name to a proposer the gated loop can consume.
    `model_ref` becomes 'provider:model', so the receipt of every accepted
    result names its proposer — provider provenance rides the envelope."""
    if provider == "stub":
        return StubProposer(canned or "pass\n")
    if provider == "serve":
        return ServeProposer(base_url or "http://127.0.0.1:8765")
    spec = REGISTRY.get(provider)
    if spec is None:
        raise ValueError(
            f"unknown provider {provider!r} — known: {', '.join(provider_names())}")
    url = base_url or spec.base_url or os.environ.get("OPENAI_BASE_URL", "")
    if not url:
        raise ValueError(
            f"provider {provider!r} needs --base-url (or OPENAI_BASE_URL)")
    return EnterpriseProposer(
        base_url=url,
        model=model or spec.default_model,
        api_key_env=spec.api_key_env or "OPENAI_API_KEY",
        model_ref=provider)
