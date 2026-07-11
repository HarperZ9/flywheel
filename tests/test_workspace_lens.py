"""Falsifier for the workspace advisory (harness/workspace_lens.py).

The contract: a WorkspaceCaution can request a DEMOTE, never an accept (there is
no such field). NullLens (the default) never cautions, so the engine is
unchanged. The demote-only integration itself is exercised in test_selector.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.workspace_lens import (
    WorkspaceCaution, NO_CAUTION, NullLens, AlwaysCautionLens, WorkspaceLens,
)


def test_null_lens_never_cautions():
    assert NullLens().caution("def f(a): return a").demote is False
    assert NO_CAUTION.demote is False


def test_always_caution_lens_demotes():
    c = AlwaysCautionLens(score=0.9, reason="suspicious workspace").caution("x")
    assert c.demote is True
    assert c.score == 0.9
    assert "suspicious" in c.reason


def test_caution_has_no_accept_field():
    # a caution can only ask to DEMOTE -- there is structurally no way to accept
    assert not hasattr(WorkspaceCaution(), "accept")
    assert not hasattr(WorkspaceCaution(), "promote")


def test_lenses_satisfy_protocol():
    assert isinstance(NullLens(), WorkspaceLens)
    assert isinstance(AlwaysCautionLens(), WorkspaceLens)
