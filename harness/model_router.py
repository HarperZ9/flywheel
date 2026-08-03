"""model_router.py -- one engine reaches every model, with failover.

The piece OpenRouter is for, built into the loop: a request resolves to a chain
of candidate models across providers, and the router tries them in order, failing
over when a provider is rate-limited or quota-exhausted (429), unreachable, or
its key is not configured. The winning candidate's output feeds the same accept
path as any other proposer.

Reuses everything: providers.REGISTRY + make_proposer for the 27 OpenAI-wire
providers, AnthropicProposer for the /v1/messages wire, keychain for auth by env
var name. Adds the routing chain, the failover policy, and a routing receipt that
records provider, model, and auth SOURCE (env / keychain / absent), never a key.

Roles let a request ask for a capability instead of a name; the role's chain is
the fallback order. Model ids are high-confidence or registry defaults, never
invented.
"""
from __future__ import annotations

import hashlib
import urllib.error
from dataclasses import dataclass

from .keychain import credential_source
from .providers import REGISTRY, make_proposer
from .proposer import AnthropicProposer, ProposerOutput, prompt_hash
from .receipt_fields import canonical

# Roles let a request ask for a capability instead of a model name.
FLAGSHIP = "flagship"
WORKHORSE = "workhorse"
CHEAP = "cheap"
REASONING = "reasoning"
VISION = "vision"
LOCAL = "local"

# Anthropic /v1/messages endpoints: (base_url, api_key_env, version, default_model).
# The AnthropicProposer appends "/v1/messages" to base_url. Every entry below is a
# confirmed Anthropic-compatible endpoint (provider-catalog 2026-08-03): a client
# built for Anthropic reaches all of them with no translation adapter, so they form
# one drop-in failover lane. Default model ids are best-known; verify per catalog.
ANTHROPIC_ENDPOINTS = {
    "anthropic": ("https://api.anthropic.com", "ANTHROPIC_API_KEY",
                  "2023-06-01", "claude-fable-5"),
    "qwen-anthropic": ("https://dashscope-intl.aliyuncs.com/apps/anthropic",
                       "DASHSCOPE_API_KEY", "2023-06-01", "qwen-max"),
    "deepseek-anthropic": ("https://api.deepseek.com/anthropic",
                           "DEEPSEEK_API_KEY", "2023-06-01", "deepseek-v4-flash"),
    "fireworks-anthropic": ("https://api.fireworks.ai/inference",
                            "FIREWORKS_API_KEY", "2023-06-01",
                            "accounts/fireworks/models/llama-v3p3-70b-instruct"),
    "openrouter-anthropic": ("https://openrouter.ai/api", "OPENROUTER_API_KEY",
                             "2023-06-01", "anthropic/claude-opus-4.6"),
}

# Retryable HTTP statuses: fail over to the next candidate rather than error out.
RETRYABLE = frozenset({429, 500, 502, 503, 504})


def retryable_status(code: int) -> bool:
    return code in RETRYABLE


@dataclass(frozen=True)
class Candidate:
    provider: str
    model: str
    wire: str            # "anthropic" | "openai"
    api_key_env: str
    base_url: str = ""


def candidate(provider: str, model: str | None = None) -> Candidate:
    """Resolve a provider (+ optional model) into a Candidate, pulling the base
    url and auth env var name from the registries."""
    if provider in ANTHROPIC_ENDPOINTS:
        base, env, _ver, default_model = ANTHROPIC_ENDPOINTS[provider]
        return Candidate(provider, model or default_model, "anthropic", env, base)
    spec = REGISTRY.get(provider)
    if spec is None:
        raise ValueError(f"unknown provider {provider!r}")
    return Candidate(provider, model or spec.default_model, "openai",
                     spec.api_key_env, spec.base_url)


def build_candidate(cand: Candidate):
    """Build the proposer for a candidate: the Anthropic wire for anthropic
    endpoints, make_proposer (OpenAI wire) for everything else."""
    if cand.wire == "anthropic":
        _base, _env, version, _dm = ANTHROPIC_ENDPOINTS.get(
            cand.provider, (cand.base_url, cand.api_key_env, "2023-06-01", cand.model))
        return AnthropicProposer(base_url=cand.base_url, model=cand.model,
                                 api_key_env=cand.api_key_env, version=version,
                                 model_ref=cand.provider)
    return make_proposer(cand.provider, model=cand.model)


# Role -> fallback chain. Anthropic role tiers and ids follow the provider-catalog
# (2026-08-03): fable-5 flagship, opus-5 reasoning, sonnet-5 workhorse, haiku cheap.
# Other providers use their registry default model rather than an unconfirmed id
# (the catalog could not confirm qwen3.8-max on any official page, so dashscope
# falls back to its high-confidence "qwen-max" default).
ROLES: dict[str, list[tuple[str, str | None]]] = {
    FLAGSHIP: [("anthropic", "claude-fable-5"), ("dashscope", None),
               ("openrouter", None)],
    REASONING: [("anthropic", "claude-opus-5"), ("openai", None),
                ("dashscope", None)],
    WORKHORSE: [("anthropic", "claude-sonnet-5"), ("dashscope", None),
                ("deepseek", None)],
    CHEAP: [("anthropic", "claude-haiku-4-5-20251001"), ("deepseek", None),
            ("groq", None)],
    LOCAL: [("ollama", None), ("vllm", None)],
}


def chain_for_role(role: str) -> list[Candidate]:
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}; known: {', '.join(sorted(ROLES))}")
    return [candidate(p, m) for p, m in ROLES[role]]


@dataclass
class Attempt:
    provider: str
    model: str
    outcome: str         # ok | failover | error | unreachable | auth_absent
    status: int | None
    auth_source: str     # env | keychain | absent | none

    def to_dict(self) -> dict:
        return {"provider": self.provider, "model": self.model,
                "outcome": self.outcome, "status": self.status,
                "auth_source": self.auth_source}


@dataclass
class RoutingResult:
    winner: Candidate | None
    served_model: str
    attempts: list[Attempt]

    def failover_count(self) -> int:
        return sum(1 for a in self.attempts if a.outcome != "ok")

    def to_receipt(self) -> dict:
        body = {
            "winner": (f"{self.winner.provider}:{self.winner.model}"
                       if self.winner else None),
            "served_model": self.served_model,
            "failover_count": self.failover_count(),
            "attempts": [a.to_dict() for a in self.attempts],
        }
        digest = hashlib.sha256(canonical(body).encode()).hexdigest()[:16]
        return {"schema": "flywheel.routing-receipt/v1", "digest": digest, **body}


class RoutingExhausted(Exception):
    """Every candidate in the chain failed. Carries the attempts (no secrets)."""

    def __init__(self, attempts: list[Attempt]):
        self.attempts = attempts
        super().__init__(f"all {len(attempts)} routing candidates failed")


class RoutingProposer:
    """A Proposer that routes across a candidate chain with failover. Plugs into
    run_loop unchanged; the winning provider:model rides model_ref into every
    receipt, and last_route.to_receipt() carries the failover trace."""

    def __init__(self, chain: list[Candidate], *, builder=None,
                 model_ref: str = "route", skip_absent_auth: bool = True):
        if not chain:
            raise ValueError("a routing chain needs at least one candidate")
        self.chain = chain
        self._builder = builder or build_candidate
        self.model_ref = model_ref
        self.skip_absent_auth = skip_absent_auth
        self.last_route: RoutingResult | None = None

    def generate(self, prompt: str, *, seed: int, temperature: float,
                 max_new_tokens: int, system: str = "") -> ProposerOutput:
        attempts: list[Attempt] = []
        for cand in self.chain:
            src = credential_source(cand.api_key_env) if cand.api_key_env else "none"
            if self.skip_absent_auth and cand.api_key_env and src == "absent":
                attempts.append(Attempt(cand.provider, cand.model, "auth_absent",
                                        None, src))
                continue
            prop = self._builder(cand)
            try:
                out = prop.generate(prompt, seed=seed, temperature=temperature,
                                    max_new_tokens=max_new_tokens, system=system)
            except urllib.error.HTTPError as e:
                outcome = "failover" if retryable_status(e.code) else "error"
                attempts.append(Attempt(cand.provider, cand.model, outcome,
                                        e.code, src))
                continue
            except urllib.error.URLError:
                attempts.append(Attempt(cand.provider, cand.model, "unreachable",
                                        None, src))
                continue
            attempts.append(Attempt(cand.provider, cand.model, "ok", 200, src))
            self.last_route = RoutingResult(cand, out.served_model, attempts)
            return ProposerOutput(
                text=out.text, model_ref=f"{cand.provider}:{cand.model}",
                seed=seed, prompt_hash=prompt_hash(prompt), cache="route",
                served_model=out.served_model)
        self.last_route = RoutingResult(None, "", attempts)
        raise RoutingExhausted(attempts)


def route_role(role: str, **kwargs) -> RoutingProposer:
    """The one-call constructor: a routing proposer for a capability role."""
    return RoutingProposer(chain_for_role(role), model_ref=f"route:{role}", **kwargs)
