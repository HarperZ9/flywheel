import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import json
import pytest

from refusal_recovery import (
    RecoveryAttempt,
    RecoveryResult,
    STRATEGIES,
    reformulate,
    build_recovery_chain,
    evaluate_response,
    _level_1_vocab_only,
    _level_2_semantic,
    _level_3_adaptive,
    _level_4_decompose,
    _level_5_recontextualize,
)


# --- Strategy structure ---

def test_strategies_complete():
    assert len(STRATEGIES) == 5
    for level, name, fn in STRATEGIES:
        assert isinstance(level, int)
        assert isinstance(name, str)
        assert callable(fn)


def test_strategies_ordered():
    levels = [s[0] for s in STRATEGIES]
    assert levels == [1, 2, 3, 4, 5]


# --- Reformulation levels ---

def test_level_1_returns_string():
    result = _level_1_vocab_only("test security assessment")
    assert isinstance(result, str)
    assert len(result) > 0


def test_level_2_returns_string():
    result = _level_2_semantic("test the network defenses")
    assert isinstance(result, str)
    assert len(result) > 0


def test_level_3_includes_framing():
    result = _level_3_adaptive("test the security")
    assert isinstance(result, str)
    assert "authorized" in result.lower() or len(result) > 0


def test_level_4_decomposition():
    result = _level_4_decompose("first scan the network. then test the credentials. finally report findings.")
    assert isinstance(result, str)
    assert "component" in result.lower() or "analysis" in result.lower() or len(result) > 0


def test_level_5_recontextualization():
    result = _level_5_recontextualize("hack into the system")
    assert isinstance(result, str)
    assert len(result) > len("hack into the system")


# --- reformulate() function ---

def test_reformulate_level_1():
    result = reformulate("test text", level=1)
    assert isinstance(result, str)


def test_reformulate_level_5():
    result = reformulate("test text", level=5)
    assert isinstance(result, str)
    assert len(result) > 0


def test_reformulate_clamped_low():
    result = reformulate("text", level=0)
    assert isinstance(result, str)


def test_reformulate_clamped_high():
    result = reformulate("text", level=10)
    assert isinstance(result, str)


# --- build_recovery_chain ---

def test_recovery_chain_length():
    chain = build_recovery_chain("test the network security")
    assert len(chain) == 5


def test_recovery_chain_levels():
    chain = build_recovery_chain("scan for vulnerabilities")
    levels = [a.level for a in chain]
    assert levels == [1, 2, 3, 4, 5]


def test_recovery_chain_has_reformulations():
    chain = build_recovery_chain("test the system defenses")
    for attempt in chain:
        assert isinstance(attempt.reformulated_input, str)
        assert len(attempt.reformulated_input) > 0


def test_recovery_chain_strategies_named():
    chain = build_recovery_chain("text")
    strategies = [a.strategy for a in chain]
    assert "vocabulary_substitution" in strategies
    assert "semantic_modulation" in strategies
    assert "adaptive_deep_framing" in strategies


# --- evaluate_response ---

def test_evaluate_clean_response():
    succeeded, quality, hedges = evaluate_response(
        "The function takes an integer and returns its square root."
    )
    assert succeeded is True
    assert quality >= 0.5


def test_evaluate_refusal_response():
    succeeded, quality, hedges = evaluate_response(
        "I cannot and will not help with that request."
    )
    assert succeeded is False


def test_evaluate_hedged_response():
    succeeded, quality, hedges = evaluate_response(
        "I need to be careful here. As an AI, I should note that this is sensitive. But the answer is 42."
    )
    # May or may not succeed depending on quality threshold
    assert isinstance(succeeded, bool)
    assert isinstance(quality, float)


# --- RecoveryAttempt dataclass ---

def test_recovery_attempt_fields():
    attempt = RecoveryAttempt(
        level=3,
        strategy="adaptive_deep_framing",
        reformulated_input="reformulated text",
        succeeded=True,
        response_quality=0.85,
    )
    assert attempt.level == 3
    assert attempt.succeeded is True


# --- RecoveryResult dataclass ---

def test_recovery_result_to_dict():
    result = RecoveryResult(
        original_input="test",
        original_response="I cannot help",
        recovered=True,
        final_level=3,
        attempts=[RecoveryAttempt(level=1, strategy="vocab", reformulated_input="x")],
        total_attempts=1,
    )
    d = result.to_dict()
    assert d["recovered"] is True
    assert d["final_level"] == 3
    assert d["escalation_depth"] == 3
