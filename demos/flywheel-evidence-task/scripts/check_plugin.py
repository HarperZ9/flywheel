#!/usr/bin/env python3
"""Check that the plugin package is internally consistent.

Reads the Claude and Codex manifests, the marketplace listing and the skill, and
fails when names, versions or referenced files disagree. A built-in control
corrupts a copy of the package and requires the check to catch it.

    python scripts/check_plugin.py
"""
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check(root):
    """Return a list of problems; an empty list means the package is consistent."""
    errors = []
    claude = load(root / ".claude-plugin" / "plugin.json")
    codex = load(root / ".codex-plugin" / "plugin.json")
    market = load(root / ".claude-plugin" / "marketplace.json")
    name = claude["name"]
    if codex["name"] != name:
        errors.append(f"codex name {codex['name']!r} != claude name {name!r}")
    if codex["version"] != claude["version"]:
        errors.append(f"version mismatch: claude {claude['version']} codex {codex['version']}")
    if name not in [p["name"] for p in market["plugins"]]:
        errors.append(f"marketplace.json does not list {name!r}")
    if not (root / claude["icon"]).is_file():
        errors.append(f"icon missing: {claude['icon']}")
    skills_dir = root / codex["skills"]
    skill_dir = skills_dir / name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return errors + [f"skill missing: {skill_md.relative_to(root)}"]
    text = skill_md.read_text(encoding="utf-8")
    front = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not front:
        return errors + ["SKILL.md has no frontmatter"]
    fm = front.group(1)
    skill_name = re.search(r"^name:\s*(\S+)", fm, re.M)
    skill_ver = re.search(r'^\s+version:\s*"?([^"\s]+)"?', fm, re.M)
    if not skill_name or skill_name.group(1) != name:
        errors.append("SKILL.md name does not match the plugin name")
    if not skill_ver or skill_ver.group(1) != claude["version"]:
        errors.append("SKILL.md version does not match the plugin version")
    if not re.search(r"^description:\s*\S", fm, re.M):
        errors.append("SKILL.md has no description")
    for target in re.findall(r"\]\(((?!https?:|#)[^)\s]+)\)", text):
        if not (skill_dir / target).exists():
            errors.append(f"SKILL.md links to a missing file: {target}")
    for needed in ("agents/openai.yaml", "references/constraints.md"):
        if not (skill_dir / needed).is_file():
            errors.append(f"skill file missing: {needed}")
    examples = list((skill_dir / "examples").glob("*.md"))
    if not examples:
        errors.append("no examples shipped with the skill")
    if f"## {claude['version']}" not in (root / "CHANGELOG.md").read_text(encoding="utf-8"):
        errors.append(f"CHANGELOG.md has no entry for {claude['version']}")
    return errors


def control():
    """The check must fail on a corrupted copy, or a pass means nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "pkg"
        shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git"))
        target = copy / ".codex-plugin" / "plugin.json"
        data = load(target)
        data["version"] = "9.9.9"
        target.write_text(json.dumps(data), encoding="utf-8")
        return bool(check(copy))


def main():
    errors = check(ROOT)
    for e in errors:
        print(f"FAIL {e}")
    if errors:
        return 1
    if not control():
        print("FAIL control: a corrupted copy was accepted")
        return 1
    print("plugin package consistent; corrupted-copy control rejected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
