"""Falsifiers for the PROVIDERS slot registry in the endpoint ladder.

Split from test_endpoints.py, which covers per-backend wire shape. This file
covers the registry contract instead: which slots exist, and the rule that
binds every one of them equally.

The rule is dormancy. A slot names a reachable endpoint, but naming is not
reachability: without a credential the slot must stay OFF the ladder, so an
unconfigured provider can never become a silent default. Each slot gets the
same three questions: is it absent without a key, does it join with one, and
does the operator's environment override its model and base URL.

Hermetic: transports are injected, so no network and no real provider is
touched.
"""
from harness.endpoints import OpenAICompatBackend, build_endpoints

_MSG = [{"role": "user", "content": "hi"}]


def _tx(status, obj, sink=None):
    def t(method, url, headers, body, timeout):
        if sink is not None:
            sink.update({"url": url, "headers": headers})
        return status, obj
    return t


# --- glm-flash: GLM-5.3-Flash on OpenRouter -------------------------------
# Replaces the retired `ox-alpha` slot. That slot carried the stealth
# pre-release of this same model under slug `stealth/ox-alpha`; the slug was
# withdrawn when the model shipped under its own name, which left a slot that
# could resolve a credential and still 404 at dispatch.

def test_glm_flash_dormant_without_key(monkeypatch):
    for v in ("OPENROUTER_API_KEY", "GLM_FLASH_BASE_URL", "GLM_FLASH_MODEL"):
        monkeypatch.delenv(v, raising=False)
    assert build_endpoints(providers=["glm-flash"],
                           modes=("api", "provider", "cloud")) == []


def test_glm_flash_joins_ladder_when_configured(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    lad = build_endpoints(providers=["glm-flash"], modes=("api",))
    assert [b.name for b in lad] == ["glm-flash"]
    sink = {}
    lad[0].transport = _tx(200, {"choices": [{"message": {"content": "hey"}}]},
                           sink)
    out = lad[0].chat(_MSG, system="", max_tokens=8, temperature=0, seed=0)
    assert out["text"] == "hey"
    assert out["model_ref"] == "glm-flash:z-ai/glm-5.3-flash"
    assert sink["url"].startswith(
        "https://openrouter.ai/api/v1/chat/completions")
    assert sink["headers"]["Authorization"] == "Bearer k"


def test_glm_flash_model_and_base_overridable(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("GLM_FLASH_MODEL", "z-ai/glm-5.3")
    monkeypatch.setenv("GLM_FLASH_BASE_URL", "https://gateway.example/v1")
    lad = build_endpoints(providers=["glm-flash"], modes=("api",))
    sink = {}
    lad[0].transport = _tx(200, {"choices": [{"message": {"content": "x"}}]},
                           sink)
    lad[0].chat(_MSG, system="", max_tokens=4, temperature=0, seed=0)
    assert sink["url"].startswith("https://gateway.example/v1/chat/completions")


def test_retired_ox_alpha_slot_is_gone():
    """The stealth slug is withdrawn upstream. A slot that resolves a
    credential and then 404s at dispatch is worse than no slot, so the name
    must not resolve at all."""
    from harness.endpoints import PROVIDERS
    assert "ox-alpha" not in PROVIDERS
    assert build_endpoints(providers=["ox-alpha"], modes=("api",)) == []


# --- abliteration: operator-supplied endpoint -----------------------------
# The served weights have had their refusal direction orthogonalized away, so
# this backend proposes with no provider-side refusal behaviour of its own.
# That changes nothing downstream: a proposer never gains authority by which
# slot it came from, and the accept path stays external. It gets the same
# dormancy contract as every other slot, and no privileged position.

def test_abliteration_dormant_without_key(monkeypatch):
    for v in ("ABLITERATION_API_KEY", "ABLITERATION_BASE_URL",
              "ABLITERATION_MODEL"):
        monkeypatch.delenv(v, raising=False)
    assert build_endpoints(providers=["abliteration"],
                           modes=("api", "provider", "cloud")) == []


def test_abliteration_joins_ladder_when_configured(monkeypatch):
    monkeypatch.setenv("ABLITERATION_API_KEY", "k")
    lad = build_endpoints(providers=["abliteration"], modes=("api",))
    assert [b.name for b in lad] == ["abliteration"]
    sink = {}
    lad[0].transport = _tx(200, {"choices": [{"message": {"content": "hey"}}]},
                           sink)
    out = lad[0].chat(_MSG, system="", max_tokens=8, temperature=0, seed=0)
    assert out["model_ref"] == "abliteration:abliterated-model-large-v2"
    assert sink["url"].startswith(
        "https://api.abliteration.ai/v1/chat/completions")
    assert sink["headers"]["Authorization"] == "Bearer k"


def test_abliteration_model_and_base_overridable(monkeypatch):
    monkeypatch.setenv("ABLITERATION_API_KEY", "k")
    monkeypatch.setenv("ABLITERATION_MODEL", "abliterated-model-large")
    monkeypatch.setenv("ABLITERATION_BASE_URL", "https://self-hosted.example/v1")
    lad = build_endpoints(providers=["abliteration"], modes=("api",))
    sink = {}
    lad[0].transport = _tx(200, {"choices": [{"message": {"content": "x"}}]},
                           sink)
    out = lad[0].chat(_MSG, system="", max_tokens=4, temperature=0, seed=0)
    assert out["model_ref"] == "abliteration:abliterated-model-large"
    assert sink["url"].startswith("https://self-hosted.example/v1")


def test_no_slot_dispatches_without_a_credential(monkeypatch):
    """The registry-wide invariant, stated once. Strip every slot credential
    and the whole configured ladder must be empty -- including the local-none
    and CLI slots, which are excluded here because their reachability is a
    binary on disk, not a credential."""
    from harness.endpoints import PROVIDERS
    for spec in PROVIDERS.values():
        if spec.get("key"):
            monkeypatch.delenv(spec["key"], raising=False)
    api_only = [n for n, s in PROVIDERS.items() if s.get("key")]
    assert build_endpoints(providers=api_only,
                           modes=("api", "provider", "cloud")) == []


def test_openai_compat_sends_no_auth_header_when_key_absent():
    """A credential-less backend must omit Authorization entirely rather than
    send `Bearer ` and let the provider decide what an empty token means."""
    sink = {}
    b = OpenAICompatBackend(
        "abliteration", "https://api.abliteration.ai/v1", "m",
        key_env="ABLITERATION_API_KEY", api_key="",
        transport=_tx(200, {"choices": [{"message": {"content": "ok"}}]}, sink))
    b.chat(_MSG, system="", max_tokens=8, temperature=0, seed=0)
    assert "Authorization" not in sink["headers"]
