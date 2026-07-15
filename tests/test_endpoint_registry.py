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
    unified_roster, make_endpoint_proposer, BackendProposer, LedgeredProposer, _NATIVE,
)
from harness import providers
from harness.local_session import SessionLedger
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


# --- LedgeredProposer: chain every endpoint call (increment 3) ------------------

class _StubProposer:
    model_ref = "prov:m9"

    def __init__(self):
        self.calls = 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        self.calls += 1
        return ProposerOutput(f"def f(): return {self.calls}\n", self.model_ref, seed,
                              "ph", "miss")


def test_ledgered_proposer_chains_every_call_verifiably():
    led = SessionLedger()
    p = LedgeredProposer(_StubProposer(), led, endpoint="prov")
    for i in range(3):
        p.generate("secret prompt text", seed=i, temperature=0.0, max_new_tokens=8)
    assert len(led.entries) == 3
    assert led.verify() is True                 # a clean chain re-derives
    assert all(e.kind == "endpoint_call" for e in led.entries)
    assert led.entries[0].meta["model_ref"] == "prov:m9"   # provenance chained


def test_ledger_tamper_is_detected():
    led = SessionLedger()
    p = LedgeredProposer(_StubProposer(), led, endpoint="prov")
    p.generate("x", seed=0, temperature=0.0, max_new_tokens=8)
    p.generate("y", seed=1, temperature=0.0, max_new_tokens=8)
    led.entries[0].meta["model_ref"] = "attacker:swapped"   # flip a recorded byte
    assert led.verify() is False, "a tampered endpoint-call entry passed verify -- broken"


def test_ledger_stores_no_prompt_text_and_no_secret():
    led = SessionLedger()
    p = LedgeredProposer(_StubProposer(), led, endpoint="prov")
    p.generate("SENSITIVE-PROMPT-CANARY", seed=0, temperature=0.0, max_new_tokens=8)
    blob = led.to_jsonl()
    assert "SENSITIVE-PROMPT-CANARY" not in blob   # commitments only, never the text
    assert "response_sha" in blob and "prompt_sha" in blob


def test_make_endpoint_proposer_wraps_when_ledger_given():
    led = SessionLedger()
    p = make_endpoint_proposer("stub", ledger=led)
    assert isinstance(p, LedgeredProposer)
    p.generate("x", seed=0, temperature=0, max_new_tokens=4)
    assert len(led.entries) == 1 and led.verify()
    # without a ledger, no wrapping (unchanged surface)
    assert not isinstance(make_endpoint_proposer("stub"), LedgeredProposer)


def test_every_usable_roster_name_can_actually_build_a_proposer():
    # unified_roster advertises usable endpoints as receipt_capable; each must
    # actually construct a proposer, not raise 'unknown endpoint'.
    r = unified_roster()
    for name in r["usable_names"]:
        p = make_endpoint_proposer(name)
        assert p is not None, name


def test_cli_credential_is_gated_on_the_binary_present(monkeypatch):
    import harness.endpoint_registry as er
    # no CLI on PATH -> cli rows are not advertised as usable
    monkeypatch.setattr(er.shutil, "which", lambda cmd: None)
    r = unified_roster()
    cli_rows = {row["name"]: row for row in r["endpoints"] if row["kind"] == "cli"}
    assert cli_rows, "expected cli rows in the roster"
    for name, row in cli_rows.items():
        assert row["credential"] == "cli-absent"
        assert name not in r["usable_names"]


def test_roster_carries_a_digest_that_moves_when_the_routable_set_changes(monkeypatch):
    import harness.endpoint_registry as er
    from harness import providers
    before = unified_roster()["roster_sha"]
    assert before and len(before) == 16
    # a mutation of the registry's routable identity moves the digest
    orig = dict(providers.REGISTRY)
    try:
        sample = next(iter(providers.REGISTRY.values()))
        providers.REGISTRY["zzz-new-provider"] = sample
        after = unified_roster()["roster_sha"]
        assert after != before
    finally:
        providers.REGISTRY.clear()
        providers.REGISTRY.update(orig)
    # stable when nothing changes
    assert unified_roster()["roster_sha"] == before
