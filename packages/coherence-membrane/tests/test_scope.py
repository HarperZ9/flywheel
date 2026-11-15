"""Tests for consequence scope -- mediate consequence, never activity."""

from __future__ import annotations

from coherence_membrane.scope import ConsequenceScope, creative_profile


def test_consequential_actions_are_gated():
    scope = creative_profile()
    for action in ("publish", "export", "overwrite", "delete", "spend", "send", "deploy"):
        assert scope.requires_gate(action), action


def test_reversible_creative_actions_flow_free():
    scope = creative_profile()
    for action in ("draw", "edit_draft", "generate_variation", "undo", "preview", "paint"):
        assert not scope.requires_gate(action), action


def test_operator_can_widen_scope():
    scope = creative_profile().with_also("commit")
    assert scope.requires_gate("commit")
    assert scope.requires_gate("publish")


def test_operator_can_narrow_scope():
    scope = creative_profile().without("export")
    assert not scope.requires_gate("export")
    assert scope.requires_gate("publish")


def test_scope_is_frozen_value():
    a = creative_profile()
    b = a.with_also("commit")
    assert a is not b
    assert not a.requires_gate("commit")  # original unchanged
