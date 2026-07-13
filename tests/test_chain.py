"""M2 spanning-chain falsifier (harness/chain.py — the spine).

The binary-collapse guard: a clean chain validates to MATCH; corrupting any
stage's content (tamper) breaks the link at the next stage -> UNVERIFIABLE;
corrupting a prev_hash pointer -> UNVERIFIABLE. The chain head is bound into
the envelope so terminal-receipt tampering is also caught. If any corruption
ever validates to MATCH, the receipt chain is broken at the foundation.
"""
import copy
from pathlib import Path

import pytest

from harness.chain import (StageReceipt, append_stage, validate_chain,
                           chain_to_dicts, chain_from_dicts)


def _clean_chain():
    chain = []
    append_stage(chain, "boot", "task1", "roothash", "MATCH")
    append_stage(chain, "propose", "ph1", "cand1", "OK",
                 payload={"model_ref": "stub"})
    append_stage(chain, "policy", "ah1", "allow", "allow")
    append_stage(chain, "verify", "cand1", "orhash1", "PASS")
    append_stage(chain, "accept", "orhash1", "MATCH", "MATCH")
    return chain


def test_clean_chain_validates_match():
    v = validate_chain(_clean_chain())
    assert v.verdict == "MATCH", v.reason
    assert v.head_hash


def test_empty_chain_is_unverifiable():
    assert validate_chain([]).verdict == "UNVERIFIABLE"


@pytest.mark.parametrize("idx", [0, 1, 2, 3])
def test_tamper_nonterminal_stage_breaks_link(idx):
    chain = _clean_chain()
    chain[idx].outputs_hash = "TAMPERED"
    v = validate_chain(chain)
    assert v.verdict == "UNVERIFIABLE", f"stage {idx} tamper must break a link"


def test_tamper_terminal_stage_shifts_head():
    """Hash chains self-verify all LINKS; the head has no successor, so terminal
    tampering shifts the head_hash and is caught by the envelope's content_hash
    anchor (not by validate_chain alone). This is the honest tamper-evidence
    boundary: links are intrinsic, the head is externally anchored."""
    chain = _clean_chain()
    original_head = validate_chain(chain).head_hash
    chain[-1].outputs_hash = "TAMPERED"
    v = validate_chain(chain)
    assert v.verdict == "MATCH"  # links intact — head tamper isn't a link break
    assert v.head_hash != original_head, "terminal tamper must shift the head_hash"


def test_envelope_anchor_catches_terminal_tamper(tmp_path):
    from harness.envelope import ProofEnvelope
    from harness.task import load_task
    from harness.loop import run_loop
    from harness.proposer import StubProposer
    from harness.oracle import PytestOracle
    import copy
    task = load_task(Path(__file__).parent.parent / "tasks" / "example_pass",
                     workdir=tmp_path / "w")
    r = run_loop(task, StubProposer("def add(a, b):\n    return a + b\n"),
                 PytestOracle(), envelopes_dir=tmp_path / "env")
    original_content_hash = r.envelope.content_hash()
    tampered_env = copy.deepcopy(r.envelope)
    tampered_env.chain[-1]["outputs_hash"] = "forged"
    assert tampered_env.content_hash() != original_content_hash, (
        "terminal-receipt tamper must shift the envelope content_hash (the anchor)")


@pytest.mark.parametrize("idx", [1, 2, 3, 4])
def test_broken_link_collapses(idx):
    chain = _clean_chain()
    chain[idx].prev_hash = "wrongpointer"
    v = validate_chain(chain)
    assert v.verdict == "UNVERIFIABLE"
    assert v.broken_at == idx


def test_chain_roundtrips_through_dicts():
    chain = _clean_chain()
    dicts = chain_to_dicts(chain)
    assert validate_chain(dicts).verdict == "MATCH"
    rebuilt = chain_from_dicts(dicts)
    assert validate_chain(rebuilt).verdict == "MATCH"


def test_inserted_fake_receipt_collapses():
    chain = _clean_chain()
    fake = StageReceipt(stage="verify", inputs_hash="cand1",
                       outputs_hash="forged", verdict="PASS",
                       prev_hash="bogus")
    chain[3] = fake
    v = validate_chain(chain)
    assert v.verdict == "UNVERIFIABLE"
    assert "verify" in v.reason


def test_loop_envelope_carries_validating_chain(tmp_path):
    from harness.task import load_task
    from harness.loop import run_loop
    from harness.proposer import StubProposer
    from harness.oracle import PytestOracle
    task = load_task(Path(__file__).parent.parent / "tasks" / "example_pass",
                     workdir=tmp_path / "w")
    r = run_loop(task, StubProposer("def add(a, b):\n    return a + b\n"),
                 PytestOracle(), envelopes_dir=tmp_path / "env")
    assert r.envelope.chain, "envelope must carry a chain"
    v = validate_chain(r.envelope.chain)
    assert v.verdict == "MATCH", v.reason
    stages = [s["stage"] for s in r.envelope.chain]
    assert "propose" in stages and "verify" in stages and "accept" in stages


def test_loop_envelope_chain_tamper_detected(tmp_path):
    from harness.task import load_task
    from harness.loop import run_loop
    from harness.proposer import StubProposer
    from harness.oracle import PytestOracle
    task = load_task(Path(__file__).parent.parent / "tasks" / "example_pass",
                     workdir=tmp_path / "w")
    r = run_loop(task, StubProposer("def add(a, b):\n    return a + b\n"),
                 PytestOracle(), envelopes_dir=tmp_path / "env")
    tampered = copy.deepcopy(r.envelope.chain)
    tampered[1]["outputs_hash"] = "forged"
    assert validate_chain(tampered).verdict == "UNVERIFIABLE"
