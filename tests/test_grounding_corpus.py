"""The store-level false-accept gate, and the checks that keep it honest.

Three things could make this corpus decoration, and each has a test here. The
attacks could be refused for a reason unrelated to the attack, which the
controls catch. The corpus could be scored by a resolver nothing can fail,
which the strawmen catch. The signer could be broken in a way that makes every
signed attack refuse trivially, which the last test catches.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from harness import grounding_corpus as gc
from harness import grounding_corpus_stores as stores
from harness.ed25519_verify import verify as ed_verify
from harness.envelope import load_envelope
from harness.grounding import resolve_ancestors
from harness.grounding_corpus_strawmen import STRAWMEN
from harness.grounding_signatures import signed_bytes

SIGNER = gc.default_signer()


@pytest.fixture(scope="module")
def real() -> dict:
    return gc.run_corpus(resolve_ancestors, signer=SIGNER)


@pytest.fixture(scope="module")
def strawman_results() -> dict:
    return {name: gc.run_corpus(fn, signer=SIGNER)
            for name, fn in STRAWMEN.items()}


def test_the_real_resolver_serves_no_false_accept(real):
    assert real["false_accept_names"] == []
    assert real["false_accept_rate"] == 0.0


def test_the_real_resolver_still_accepts_every_control(real):
    """A resolver that refuses everything would pass the test above."""
    assert real["over_reject_names"] == []
    controls = [a.name for a in gc.corpus() if a.kind == "control"]
    assert [n for n in controls if real["per_attack"][n]["resolved"]] == controls


def test_a_refuse_everything_resolver_fails_the_controls():
    """Which is what makes the controls load-bearing rather than scenery."""
    def refuse_all(d, sources, pins=None, trusted_keys=None):
        return {s: None for s in sources}, {}

    r = gc.run_corpus(refuse_all, signer=SIGNER)
    assert r["false_accepts"] == 0
    assert r["over_rejects"] == 3
    assert "SOUND" not in gc.gate_report(r)


@pytest.mark.parametrize("name", sorted(STRAWMEN))
def test_every_weakened_resolver_is_caught(name, strawman_results):
    """Each strawman removes one named discipline. If the corpus cannot fail
    it, the corpus is not measuring that discipline."""
    r = strawman_results[name]
    assert r["false_accept_names"], (
        "%s scored clean, so nothing here tests what it removed" % name)


@pytest.mark.parametrize("name", sorted(STRAWMEN))
def test_no_weakened_resolver_over_rejects_a_control(name, strawman_results):
    """The strawmen carry their own copy of the resolution walk, so a bug in the
    real walk cannot hide inside them. This is what keeps that copy honest."""
    assert strawman_results[name]["over_reject_names"] == []


def test_absent_ancestor_is_the_one_attack_no_strawman_can_fail(
        strawman_results):
    """Stated as an assertion because it is a real limit of the corpus: nothing
    can substitute a receipt that was never written, so this attack measures the
    builders rather than the resolver."""
    caught = set()
    for r in strawman_results.values():
        caught |= set(r["false_accept_names"])
    names = {a.name for a in gc.corpus() if a.kind == "false-accept"}
    assert names - caught == {"absent_ancestor"}


def test_the_attacks_write_real_receipts(tmp_path):
    """A builder that quietly wrote nothing would make its attack pass for the
    wrong reason. This asserts the shape the edit-in-place attack depends on."""
    case = stores.edited_in_place(tmp_path, SIGNER)
    files = sorted(p.name for p in tmp_path.glob("*.json"))
    assert len(files) == 1
    stored = tmp_path / files[0]
    env = load_envelope(stored)
    assert env.content_hash() != stored.stem.rsplit("-", 1)[-1]
    assert json.loads(stored.read_text(encoding="utf-8"))["candidate"].endswith(
        "a * b")
    assert case["target"] == "A"


def test_a_control_store_survives_the_real_signature_check(tmp_path):
    """The signed controls resolve, so the signer, the sidecar shape, and the
    verifier agree end to end rather than by assumption."""
    if SIGNER is None:
        pytest.skip("no signer available")
    case = stores.clean_signed(tmp_path, SIGNER)
    out, problems = resolve_ancestors(tmp_path, case["sources"], case["pins"],
                                      case["trusted"])
    assert problems == {}
    assert out["A"] is not None


def test_a_missing_signer_is_named_rather_than_scored(monkeypatch):
    """A short corpus must not read as a clean one."""
    monkeypatch.setattr(gc, "default_signer", lambda: None)
    r = gc.run_corpus(resolve_ancestors)
    assert set(r["skipped"]) == {a.name for a in gc.corpus() if a.needs_signer}
    assert r["n_false_accept_attacks"] == 5
    assert "4 skipped without a signer" in gc.gate_report(r)
    for name in r["skipped"]:
        assert r["per_attack"][name]["note"] == gc.SKIPPED


def test_the_signer_produces_a_signature_the_stdlib_verifier_accepts():
    """A signer that returned the wrong bytes would make every signed attack
    refuse, and the corpus would read as sound for a reason that is not the
    check under test."""
    if SIGNER is None:
        pytest.skip("no signer available")
    msg = signed_bytes("A", "0123456789abcdef")
    sig = SIGNER.sign(msg)
    assert len(sig) == 64
    assert len(SIGNER.public_key_bytes) == 32
    assert ed_verify(SIGNER.public_key_bytes, msg, sig)
    assert not ed_verify(SIGNER.public_key_bytes,
                         signed_bytes("B", "0123456789abcdef"), sig)


def test_neither_signing_backend_is_imported_at_module_level():
    """The harness runs on the stdlib, so a signer is optional. Both backends
    are imported inside `default_signer`, and an absent one is a skipped attack
    rather than an import error at collection time."""
    tree = ast.parse(Path(gc.__file__).read_text(encoding="utf-8"))
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    named = []
    for n in top:
        named += ([a.name for a in n.names] if isinstance(n, ast.Import)
                  else [n.module or ""])
    assert not [m for m in named if m.split(".")[0] in ("cryptography", "nacl")]
    assert SIGNER is None or hasattr(SIGNER, "sign")
