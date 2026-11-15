"""Crucible optional-peer: agrees when present, degrades cleanly when absent."""

from __future__ import annotations

import pytest

from proof_surface._crucible_peer import assess_with_crucible, crucible_available

_THESIS = {
    "title": "t",
    "disposition": "publishable",
    "claims": [{"text": "claim one", "falsification": "if not"}],
}
_MEASUREMENTS = {
    "measurements": [
        {
            "claim": "claim one",
            "deviation": 0.0,
            "tolerance": 0.5,
            "method": "m",
            "evidence": [],
        }
    ]
}


def test_never_raises_returns_none_or_valid_dict():
    result = assess_with_crucible(_THESIS, _MEASUREMENTS)
    assert result is None or (
        isinstance(result, dict)
        and result["overall"] in {"MATCH", "DRIFT", "UNVERIFIABLE"}
    )


def test_agrees_with_embedded_verdict_when_crucible_present():
    pytest.importorskip("crucible")
    assert crucible_available() is True
    result = assess_with_crucible(_THESIS, _MEASUREMENTS)
    assert result is not None
    assert result["overall"] == "MATCH"  # deviation 0 within tolerance 0.5
    assert result["counts"] == {"match": 1, "drift": 0, "unverifiable": 0}
    assert isinstance(result["seal"], str) and len(result["seal"]) == 64
