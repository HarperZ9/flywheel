"""Falsifier for the universal endpoint registry (harness/endpoint_registry.py).

Load-bearing properties: (1) the roster enumerates EVERY provider and never leaks
a credential value (presence only); (2) any backend bridges into a verified
Proposer that carries provider provenance in model_ref; (3) an unknown endpoint
fails loud. The accept authority is never the provider.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.endpoint_registry import (
    unified_roster, make_endpoint_proposer, BackendProposer, _NATIVE,
)
from harness import providers
from harness.proposer import ProposerOutput


def test_roster_enumerates_every_provider():
    r = unified_roster()
    names = {e["name"] for e in r["endpoints"]}
    for p in providers.REGISTRY:               # every registry provider present
        assert p in names
    assert "serve" in names                    # local 14B
    assert {"anthropic", "gemini"} <= names    # native, not just OpenAI-shaped
    assert all(e["receipt_capable"] for e in r["endpoints"])


def test_credential_is_presence_only_never_value(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-DO-NOT-LEAK-123")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    r = unified_roster()
    blob = json.dumps(r)
    assert "sk-secret-DO-NOT-LEAK-123" not in blob      # the VALUE never appears
    anth = next(e for e in r["endpoints"] if e["name"] == "anthropic")
    assert anth["credential"] == "present"             # only presence
    xai = next(e for e in r["endpoints"] if e["name"] == "xai")
    assert xai["credential"] == "absent"


def test_local_and_cli_credentials():
    r = unified_roster()
    ollama = next(e for e in r["endpoints"] if e["name"] == "ollama")
    assert ollama["credential"] == "local-none" and ollama["local"] is True
    cli = next(e for e in r["endpoints"] if e["name"] == "claude-cli")
    assert cli["credential"] == "cli-auth"             # its own login, not an env key


class FakeBackend:
    name = "fake"
    def chat(self, messages, *, system, max_tokens, temperature, seed):
        return {"text": "def f():\n    return 1\n", "model_ref": "fake:m1", "seed": seed}


def test_backend_proposer_bridges_to_verified_proposer():
    p = BackendProposer(FakeBackend())
    out = p.generate("write f", seed=7, temperature=0.0, max_new_tokens=64)
    assert isinstance(out, ProposerOutput)
    assert "return 1" in out.text
    assert out.model_ref == "fake:m1"                  # provider provenance rides the receipt
    assert out.seed == 7


def test_backend_proposer_extract_toggle():
    class ProseBackend:
        name = "prose"
        def chat(self, messages, **k):
            return {"text": "Here is prose, not code.", "model_ref": "prose:x", "seed": 0}
    kept = BackendProposer(ProseBackend(), extract=False).generate("x", seed=0, temperature=0, max_new_tokens=8)
    assert "prose" in kept.text.lower()                # general routing keeps prose


def test_make_proposer_for_registry_and_native():
    assert make_endpoint_proposer("stub").generate("x", seed=0, temperature=0, max_new_tokens=4).text
    assert make_endpoint_proposer("serve").model_ref == "serve"
    anth = make_endpoint_proposer("anthropic")
    assert isinstance(anth, BackendProposer)
    assert anth.backend.__class__.__name__ == "AnthropicBackend"


def test_unknown_endpoint_raises():
    import pytest
    with pytest.raises(ValueError):
        make_endpoint_proposer("no-such-provider-xyz")
