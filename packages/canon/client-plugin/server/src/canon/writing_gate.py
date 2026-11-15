"""writing_gate.py -- V2: the injected STE writing gate.

canon is self-contained and stdlib-only, and the STE linter (check_writing.py)
and its profiles live outside this repo. So the gate is an injected seam. canon
owns three things: the checker callable's shape, the per-surface profile
register, and the gate pipeline. The caller wires the real checker, keeping
profile loading on its own side:

    from local_model.scripts import check_writing, writing_profiles
    checker = lambda text, name: check_writing.check_text(
        text, writing_profiles.load(name))

A file passes iff the checker reports an empty `hard` list. That is the exact
signal check_writing --gate keys on (`return 1 if (args.gate and any_hard) else
0`), so the gate here and the linter's own CLI agree on the verdict.

The register binds each surface's rendered prose to an STE profile. The
instruction files (CLAUDE.md, AGENTS.md) are documentation register (readme);
SOUL.md is the voice surface (chat). The strict procedure profile governs error
messages and commits, no rendered surface, so it is unused here (D-37 null).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Callable, Optional

from canon.registry import Surface

# (text, profile_name) -> a score mapping whose `hard` key lists the
# hard-violation categories. The caller loads the profile, so canon never
# imports writing_profiles.
WritingChecker = Callable[[str, str], Mapping]

# A cheap pre-clean applied before the check. The wired instance is Forum's
# clarify tool (forum.prose.clarify), adapted by forum_clarify_pre_cleaner.
# Optional: the gate is the same with or without it.
PreCleaner = Callable[[str], str]

# Forum's prose pre-cleaner. Forum renamed humanize to clarify and keeps the
# humanize names as deprecated aliases for one release. canon imports no engine,
# so the caller wires the call (the MCP tool, `forum clarify`, POST /clarify, or
# forum.clarify.clarify_text) and canon validates the result envelope.
FORUM_CLARIFY_TOOL = "forum.prose.clarify"
FORUM_CLARIFY_SCHEMA = "forum.prose-clarification/v1"
# Deprecated: the schema id the humanize alias returns during the alias window.
FORUM_HUMANIZE_SCHEMA = "forum.prose-humanization/v1"
ACCEPTED_FORUM_PROSE_SCHEMAS: frozenset[str] = frozenset(
    {FORUM_CLARIFY_SCHEMA, FORUM_HUMANIZE_SCHEMA})

# text -> Forum's clarify result mapping, carrying `schema` and `output`.
ForumClarify = Callable[[str], Mapping]

HARD_KEY = "hard"

STE_PROFILE_BY_HARNESS_SCOPE: dict[tuple[str, str], str] = {
    ("claude-code", "global"): "readme",
    ("claude-code", "workspace"): "readme",
    ("codex", "workspace"): "readme",
    ("hermes", "workspace"): "chat",
}

DEFAULT_STE_PROFILE = "readme"


def forum_clarify_pre_cleaner(clarify: ForumClarify) -> PreCleaner:
    """Adapt a wired Forum clarify call into a PreCleaner.

    The returned callable passes the text to `clarify` and returns the result's
    `output`. It accepts both schema ids in ACCEPTED_FORUM_PROSE_SCHEMAS, so a
    caller still on the deprecated humanize alias keeps working during the alias
    window. Any other schema id, or an `output` that is not a string, raises
    ValueError. Like the gate's `hard` key, a malformed envelope is a wiring
    fault for the caller to see, and the gate does not score text it cannot
    trust came from Forum.
    """
    def pre_clean(text: str) -> str:
        payload = clarify(text)
        schema = payload.get("schema")
        if schema not in ACCEPTED_FORUM_PROSE_SCHEMAS:
            accepted = ", ".join(sorted(ACCEPTED_FORUM_PROSE_SCHEMAS))
            raise ValueError(
                f"unexpected Forum prose schema {schema!r}; expected one of "
                f"{accepted}")
        output = payload.get("output")
        if not isinstance(output, str):
            raise ValueError(
                f"Forum prose result has no string output (schema {schema})")
        return output

    return pre_clean


def ste_profile_for(surface: Surface) -> str:
    """The STE profile name that governs `surface`'s rendered prose, falling
    back to DEFAULT_STE_PROFILE for a surface not yet in the register."""
    return STE_PROFILE_BY_HARNESS_SCOPE.get(
        (surface.harness, surface.scope), DEFAULT_STE_PROFILE)


@dataclass(frozen=True, slots=True)
class GateResult:
    """One writing-gate pass. ok is true iff the checker reported no hard
    violations; hard lists the categories it did report; cleaned is the text
    actually scored (post pre-clean, if any); label names the source."""

    ok: bool
    profile: str
    hard: tuple[str, ...]
    cleaned: str
    label: str


def gate_text(text: str, profile: str, *, checker: WritingChecker,
              pre_clean: Optional[PreCleaner] = None,
              label: str = "") -> GateResult:
    """Score `text` against `profile` through the injected checker, pre-cleaning
    first when a pre_clean is given. Passes iff the checker reports an empty
    hard list.

    The gate trusts the checker's contract: it reads the `hard` key directly and
    does not catch a checker that raises. A raising checker, or a score with no
    `hard` key, is a wiring fault for the caller to see, not a canon refusal to
    absorb. Reading the key directly fails closed on a malformed score rather
    than green-lighting when the pass/fail signal is absent.
    """
    cleaned = pre_clean(text) if pre_clean is not None else text
    score = checker(cleaned, profile)
    hard = tuple(score[HARD_KEY])
    return GateResult(ok=not hard, profile=profile, hard=hard,
                      cleaned=cleaned, label=label)


def gate_surface(surface: Surface, text: str, *, checker: WritingChecker,
                 pre_clean: Optional[PreCleaner] = None) -> GateResult:
    """gate_text with the surface's registered profile and its path as label."""
    return gate_text(text, ste_profile_for(surface), checker=checker,
                     pre_clean=pre_clean, label=surface.relative_path)
