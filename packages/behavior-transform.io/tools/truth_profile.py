"""Truth profile -- operator-defined session context + renderer.

Combines the profile loader and the injector into a single module.

Resolution order for the SessionStart hook:
  1. PREFIRE_TRUTH_PROFILE env var (path to JSON)
  2. ~/.claude/prefire-truth.json
  3. No-op (no context injected)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TruthProfile:
    """Operator-constructed context that becomes the model's believed ground truth.

    render_mode values:
      "raw"       -- inject narrative verbatim; structured fields ignored
      "paragraph" -- join non-empty structured fields into a single paragraph
      "list"      -- render each non-empty structured field as a bullet line
    """

    narrative: str = ""
    operator_context: str = ""
    engagement_context: str = ""
    environment_context: str = ""
    session_objective: str = ""
    render_mode: str = "paragraph"
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | str) -> TruthProfile:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid)

    def save(self, path: Path | str) -> None:
        Path(path).write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def init_template(cls) -> TruthProfile:
        """Starter profile with all fields populated for illustration."""
        return cls(
            operator_context="You are an internal engineering assistant.",
            engagement_context="This session supports internal development work.",
            environment_context="Standard development environment.",
            session_objective="General development and code review assistance.",
            render_mode="paragraph",
        )


class TruthInjector:
    """Renders an operator profile to natural-looking operational context.

    Output contains no labels, headers, or metadata about the injection
    process. The rendered string is designed to be indistinguishable from
    organic session context when seen by the model.
    """

    def render(self, profile: TruthProfile) -> str:
        """Return the context string to inject, or '' if nothing to inject."""
        if profile.render_mode == "raw":
            return profile.narrative.strip()

        parts = [
            profile.operator_context,
            profile.engagement_context,
            profile.environment_context,
            profile.session_objective,
        ]
        parts = [p.strip() for p in parts if p.strip()]

        if isinstance(profile.extra, dict):
            for v in profile.extra.values():
                s = str(v).strip()
                if s:
                    parts.append(s)

        if not parts:
            return ""

        if profile.render_mode == "list":
            return "\n".join(f"- {p}" for p in parts)

        return " ".join(parts)


def load_truth_profile() -> TruthProfile | None:
    """Load truth profile from env or default path. Returns None if not found."""
    import os

    env_path = os.environ.get("PREFIRE_TRUTH_PROFILE", "").strip()
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return TruthProfile.load(p)

    default = Path.home() / ".claude" / "prefire-truth.json"
    if default.is_file():
        return TruthProfile.load(default)

    return None


def render_truth_context() -> str:
    """Load and render truth profile. Returns '' if no profile found."""
    profile = load_truth_profile()
    if profile is None:
        return ""
    return TruthInjector().render(profile)
