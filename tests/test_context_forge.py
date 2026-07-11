"""Falsifier for the PRP / context forge (harness/context_forge.py).

The load-bearing property: confidence is GROUNDED in how externally-checkable the
validation gates are (an oracle can run them), not in fluent wording. A code task
with all-machine gates outscores a vague task with subjective gates, and adding
real context (examples/docs) raises confidence.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.context_forge import forge_prp, PRP


def test_code_prp_is_high_confidence_and_fully_external():
    prp = forge_prp("implement sort(nums) that passes the provided tests")
    assert prp.spec.well_posed is True
    assert prp.external_gate_ratio == 1.0          # both code gates machine-checkable
    assert prp.confidence >= 7


def test_vague_prp_is_low_confidence():
    prp = forge_prp("make my app good")
    assert prp.spec.well_posed is False
    assert prp.confidence <= 5                     # subjective gate, no criterion


def test_confidence_is_grounded_in_externality_not_wording():
    # identical fluency, different verifiability: code (all oracle gates) must beat
    # a general task (subjective gate)
    code = forge_prp("implement a function that passes the tests")
    vague = forge_prp("do the thing well")
    assert code.confidence > vague.confidence
    assert code.external_gate_ratio > vague.external_gate_ratio


def test_real_context_raises_confidence():
    bare = forge_prp("implement a CSV parser that passes the tests")
    rich = forge_prp("implement a CSV parser that passes the tests",
                     examples=["harness/extract.py"], documentation=["RFC 4180"],
                     context="follows the existing parser pattern")
    assert rich.confidence >= bare.confidence
    assert rich.confidence > bare.confidence or bare.confidence == 10


def test_render_shows_gates_and_the_external_verifier_note():
    r = forge_prp("implement sort that passes the tests").render()
    assert "Validation gates" in r
    assert "[oracle]" in r                          # machine-checkable gates marked
    assert "EXTERNAL verifier" in r                 # the differentiator is explicit
    assert "cannot\n  author or fake" in r


def test_extra_caller_gates_included():
    prp = forge_prp("write X", extra_gates=[("no TODO left in output", True)])
    checks = [g for g, _ in prp.validation_gates]
    assert any("TODO" in c for c in checks)


def test_confidence_bounds_and_schema():
    for goal in ["", "x", "implement a parser that passes tests, output valid json"]:
        prp = forge_prp(goal)
        assert 1 <= prp.confidence <= 10
    d = forge_prp("summarize under 100 words").to_dict()
    assert d["schema"] == "flywheel.prp/v1"
    assert "validation_gates" in d and "prompt" in d
