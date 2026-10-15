"""skills.py -- Agent Skills (SKILL.md folders) for a coding session.

A skill is a folder holding SKILL.md, whose front matter gives a `name` and a
`description`. Folders are read from `.flywheel/skills/` and `.claude/skills/`
in the project and `skills/` in the Flywheel home. Only each skill's name and
description go into the system prompt; the model loads a skill's full text on
demand with the `skill` tool, so twenty installed skills cost twenty lines of
context, not twenty documents. A skill is instructions only: loading one grants
no permission.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIRS = (Path(".flywheel") / "skills", Path(".claude") / "skills")
MAX_BODY = 32 * 1024


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: str


def _front_matter(raw: str) -> dict:
    if not raw.startswith("---"):
        return {}
    end = raw.find("\n---", 3)
    if end == -1:
        return {}
    out = {}
    for line in raw[3:end].splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() in ("name", "description"):
            out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def load_skills(root: str, home: "str | None") -> dict:
    folders = [Path(root) / d for d in PROJECT_DIRS]
    if home:
        folders.append(Path(home) / "skills")
    from .plugins import plugin_roots
    folders += [r / "skills" for r in plugin_roots(home)]
    found: dict = {}
    for folder in folders:
        if not folder.is_dir():
            continue
        for skill_md in sorted(folder.glob("*/SKILL.md")):
            try:
                meta = _front_matter(skill_md.read_text(encoding="utf-8"))
            except OSError:
                continue
            name = meta.get("name") or skill_md.parent.name
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) and name not in found:
                found[name] = Skill(name, meta.get("description", ""), str(skill_md))
    return found


def system_text(skills: dict) -> str:
    if not skills:
        return ""
    lines = ['Skills you can load with TOOL skill {"name": "<name>"} when one fits the task:']
    lines += [f"- {s.name}: {s.description[:200]}" for s in skills.values()]
    return "\n".join(lines)


def read_skill(skills: dict, name: str) -> "tuple[bool, str]":
    skill = skills.get(name)
    if skill is None:
        return False, f"[error] no skill named {name!r}; known: {', '.join(sorted(skills)) or 'none'}"
    try:
        text = Path(skill.path).read_text(encoding="utf-8")
    except OSError as e:
        return False, f"[error] skill {name} could not be read: {e.__class__.__name__}"
    return True, text[:MAX_BODY]
