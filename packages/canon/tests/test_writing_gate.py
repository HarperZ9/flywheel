"""test_writing_gate.py -- V2: the injected STE writing gate.

canon is self-contained and stdlib-only, and the STE linter (check_writing.py)
and its profiles live outside this repo. So the gate is an injected seam: canon
defines the checker callable, the per-surface profile register, and the gate
pipeline; the caller wires the real checker as
`lambda text, name: check_writing.check_text(text, writing_profiles.load(name))`.

A file passes iff the checker reports an empty `hard` list -- the exact signal
check_writing --gate keys on. These tests inject a fake checker mirroring that
contract, so no external linter is imported.
"""
from __future__ import annotations

import pytest

from canon.registry import (
    ROOT_HOME,
    ROOT_WORKSPACE,
    Surface,
    pool_for,
)
from canon.schema import KIND_PERSONALITY_BLOCK, Provenance, Record
from canon.surface import render_surface
from canon.writing_gate import (
    ACCEPTED_FORUM_PROSE_SCHEMAS,
    DEFAULT_STE_PROFILE,
    FORUM_CLARIFY_SCHEMA,
    FORUM_CLARIFY_TOOL,
    FORUM_HUMANIZE_SCHEMA,
    GateResult,
    STE_PROFILE_BY_HARNESS_SCOPE,
    forum_clarify_pre_cleaner,
    gate_surface,
    gate_text,
    ste_profile_for,
)

CLAUDE_GLOBAL = Surface("claude-code", "global", ROOT_HOME, ".claude/CLAUDE.md")
CLAUDE_WS = Surface("claude-code", "workspace", ROOT_WORKSPACE, "CLAUDE.md")
CODEX_WS = Surface("codex", "workspace", ROOT_WORKSPACE, "AGENTS.md")
SOUL_WS = Surface("hermes", "workspace", ROOT_WORKSPACE, "SOUL.md")


def _block(id: str, scope: str, body: str, create_ord: int) -> Record:
    prov = Provenance(harness="claude-code", source_hash="a" * 64,
                      create_ord=create_ord)
    return Record(kind=KIND_PERSONALITY_BLOCK, id=id, scope=scope,
                  data={"title": id.title(), "body": body}, provenance=prov)


def _checker(hard_categories):
    """A fake WritingChecker mirroring check_writing.check_text: returns a score
    mapping whose `hard` key lists hard-violation categories. It also echoes the
    text and profile it saw, so a test can assert what it was called with."""
    calls: list[tuple[str, str]] = []

    def check(text: str, profile: str):
        calls.append((text, profile))
        return {"hard": list(hard_categories), "profile": profile}

    check.calls = calls  # type: ignore[attr-defined]
    return check


def test_gate_passes_when_no_hard_violations():
    result = gate_text("clean prose", "readme", checker=_checker([]))
    assert isinstance(result, GateResult)
    assert result.ok
    assert result.hard == ()


def test_gate_fails_on_a_hard_violation():
    result = gate_text("prose -- with an em dash", "readme",
                       checker=_checker(["em_dash"]))
    assert not result.ok
    assert result.hard == ("em_dash",)


def test_gate_calls_the_checker_with_the_named_profile():
    checker = _checker([])
    gate_text("some text", "chat", checker=checker)
    assert checker.calls == [("some text", "chat")]


def test_pre_clean_runs_before_the_check():
    checker = _checker([])
    result = gate_text("dirty", "readme", checker=checker,
                       pre_clean=str.upper)
    assert result.cleaned == "DIRTY"
    assert checker.calls == [("DIRTY", "readme")]  # checker saw cleaned text


def test_ste_profile_register_maps_each_surface():
    assert ste_profile_for(CLAUDE_GLOBAL) == "readme"
    assert ste_profile_for(CLAUDE_WS) == "readme"
    assert ste_profile_for(CODEX_WS) == "readme"
    assert ste_profile_for(SOUL_WS) == "chat"


def test_ste_profile_defaults_for_an_unregistered_surface():
    unknown = Surface("gemini", "workspace", ROOT_WORKSPACE, "GEMINI.md")
    assert ste_profile_for(unknown) == DEFAULT_STE_PROFILE
    assert ("gemini", "workspace") not in STE_PROFILE_BY_HARNESS_SCOPE


def test_gate_surface_uses_the_registered_profile_and_path_label():
    checker = _checker([])
    result = gate_surface(SOUL_WS, "voice prose", checker=checker)
    assert result.profile == "chat"
    assert result.label == "SOUL.md"
    assert checker.calls == [("voice prose", "chat")]


def test_gate_surfaces_a_malformed_score_missing_hard():
    # The gate reads the checker's pass/fail signal, the `hard` list. A checker
    # that returns a score without it is broken, and the gate must surface that
    # wiring fault (D-39), not silently green-light. Fail closed, not open.
    def broken(text: str, profile: str):
        return {"em_dash": 0}  # no `hard` key

    try:
        gate_text("text", "readme", checker=broken)
    except KeyError:
        return
    raise AssertionError("gate must raise on a score with no hard key")


def test_rendered_surface_fails_then_passes():
    # The exit criterion: the gate runs on the actual rendered file. Render a
    # surface interior, gate it with a checker that flags a hard violation
    # (fail), then with a clean checker (pass).
    pool = [_block("tone", "workspace", "W tone", 20)]
    rendered = render_surface(pool_for(CLAUDE_WS, pool), CLAUDE_WS.scope)

    failing = gate_surface(CLAUDE_WS, rendered, checker=_checker(["parataxis"]))
    assert not failing.ok
    assert failing.cleaned == rendered

    passing = gate_surface(CLAUDE_WS, rendered, checker=_checker([]))
    assert passing.ok


# -- the Forum clarify pre-cleaner ------------------------------------------

def _forum(schema, output="cleaned text"):
    """A fake wired Forum clarify call returning the result envelope shape of
    forum.clarify.clarify_text: a `schema` id and the rewritten `output`."""
    calls: list[str] = []

    def clarify(text: str):
        calls.append(text)
        return {"schema": schema, "engine": "forum-builtin", "output": output,
                "edits": ["simplified phrasing"]}

    clarify.calls = calls  # type: ignore[attr-defined]
    return clarify


def test_forum_constants_name_the_clarify_tool_and_both_schemas():
    assert FORUM_CLARIFY_TOOL == "forum.prose.clarify"
    assert FORUM_CLARIFY_SCHEMA == "forum.prose-clarification/v1"
    assert FORUM_HUMANIZE_SCHEMA == "forum.prose-humanization/v1"
    assert ACCEPTED_FORUM_PROSE_SCHEMAS == {
        "forum.prose-clarification/v1", "forum.prose-humanization/v1"}


def test_forum_clarify_pre_cleaner_feeds_output_to_the_checker():
    clarify = _forum(FORUM_CLARIFY_SCHEMA, output="Use the tool.")
    checker = _checker([])
    result = gate_text("In order to utilize the tool", "readme",
                       checker=checker,
                       pre_clean=forum_clarify_pre_cleaner(clarify))
    assert clarify.calls == ["In order to utilize the tool"]
    assert result.cleaned == "Use the tool."
    assert checker.calls == [("Use the tool.", "readme")]


def test_forum_clarify_pre_cleaner_accepts_the_deprecated_humanize_schema():
    # During the alias window a caller may still wire forum.prose.humanize.
    pre_clean = forum_clarify_pre_cleaner(_forum(FORUM_HUMANIZE_SCHEMA, "ok."))
    assert pre_clean("anything") == "ok."


def test_forum_clarify_pre_cleaner_rejects_an_unknown_schema():
    pre_clean = forum_clarify_pre_cleaner(_forum("forum.prose-other/v2"))
    with pytest.raises(ValueError, match="unexpected Forum prose schema"):
        pre_clean("text")


def test_forum_clarify_pre_cleaner_rejects_a_missing_schema():
    pre_clean = forum_clarify_pre_cleaner(lambda text: {"output": text})
    with pytest.raises(ValueError, match="unexpected Forum prose schema"):
        pre_clean("text")


def test_forum_clarify_pre_cleaner_rejects_a_non_string_output():
    pre_clean = forum_clarify_pre_cleaner(_forum(FORUM_CLARIFY_SCHEMA, None))
    with pytest.raises(ValueError, match="no string output"):
        pre_clean("text")


def test_a_rejected_envelope_never_reaches_the_checker():
    checker = _checker([])
    with pytest.raises(ValueError):
        gate_text("text", "readme", checker=checker,
                  pre_clean=forum_clarify_pre_cleaner(_forum("bogus/v1")))
    assert checker.calls == []


def test_real_forum_clarify_envelopes_pass_the_adapter():
    # Runs only where Forum with clarify is installed; canon never depends on it.
    clarify_mod = pytest.importorskip("forum.clarify")
    humanize_mod = pytest.importorskip("forum.humanize")
    if not hasattr(humanize_mod, "HUMANIZE_SCHEMA"):
        pytest.skip("installed Forum predates the clarify rename")
    text = "in order to utilize the tool"
    clarify = forum_clarify_pre_cleaner(
        lambda t: clarify_mod.clarify_text(t, engine="forum-builtin"))
    humanize = forum_clarify_pre_cleaner(
        lambda t: humanize_mod.humanize_text(t, engine="forum-builtin"))
    assert clarify(text) == "To use the tool."
    assert humanize(text) == "To use the tool."
