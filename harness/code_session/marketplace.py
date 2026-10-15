"""marketplace.py -- plugin catalogs you add, search and install from.

A marketplace is a folder or git repository holding `.claude-plugin/marketplace.json`
or `marketplace.json`, the shape Claude Code marketplaces use:

    {"name": "team-tools",
     "plugins": [{"name": "reviewer", "description": "...", "source": "./plugins/reviewer"},
                 {"name": "deploy", "source": {"source": "github", "repo": "org/deploy"}},
                 {"name": "lint", "source": {"source": "url", "url": "https://host/lint.git"}}]}

`flywheel plugin marketplace add <folder or git URL>` copies the catalog into
FLYWHEEL_HOME/code-marketplaces/<name>/ (a git source is cloned at its default
branch and the commit recorded). `flywheel plugin search [words]` lists what the
added marketplaces offer, and `flywheel plugin install NAME@MARKETPLACE` installs
one through the same review-and-confirm step as a direct install. Nothing is
installed from a marketplace without that step.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from .plugins import PluginError, _NAME, _fetch

FOLDER = "code-marketplaces"


def _catalog(folder: Path) -> dict:
    for candidate in (folder / ".claude-plugin" / "marketplace.json", folder / "marketplace.json"):
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except ValueError as e:
                raise PluginError(f"{candidate} is not valid JSON") from e
            if isinstance(data, dict) and isinstance(data.get("plugins"), list):
                return data
    raise PluginError("no marketplace.json with a plugins list")


def add(source: str, home: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        folder, origin = _fetch(source, Path(tmp))
        cat = _catalog(folder)
        name = str(cat.get("name") or folder.name)
        if not _NAME.match(name):
            raise PluginError(f"marketplace name {name!r} is not a safe folder name")
        dest = Path(home) / FOLDER / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(folder, dest, ignore=shutil.ignore_patterns(".git"))
        (dest / ".flywheel-origin").write_text(origin, encoding="utf-8")
    return {"name": name, "source": origin, "plugins": len(cat["plugins"])}


def markets(home: str) -> dict:
    base = Path(home) / FOLDER
    out = {}
    for folder in sorted(base.iterdir()) if base.is_dir() else []:
        try:
            out[folder.name] = (folder, _catalog(folder))
        except PluginError:
            continue
    return out


def search(home: str, words: str = "") -> list:
    rows = []
    want = words.lower().split()
    for market, (_folder, cat) in markets(home).items():
        for entry in cat["plugins"]:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            text = f"{entry.get('name')} {entry.get('description', '')}".lower()
            if all(w in text for w in want):
                rows.append((f"{entry['name']}@{market}", entry.get("description", "")))
    return rows


def resolve(spec: str, home: str) -> str:
    """NAME@MARKET -> a folder path or git URL that plugins.install accepts."""
    name, sep, market = spec.partition("@")
    found = markets(home).get(market) if sep else None
    if found is None:
        raise PluginError(f"no marketplace named {market!r}; add it first")
    folder, cat = found
    entry = next((e for e in cat["plugins"] if isinstance(e, dict) and e.get("name") == name), None)
    if entry is None:
        raise PluginError(f"{market} has no plugin named {name!r}")
    src = entry.get("source")
    if isinstance(src, str):
        target = (folder / src).resolve()
        if folder.resolve() not in (target, *target.parents):
            raise PluginError("a marketplace path source must stay inside the marketplace")
        return str(target)
    if isinstance(src, dict) and src.get("source") == "github" and src.get("repo"):
        return f"https://github.com/{src['repo']}.git"
    if isinstance(src, dict) and src.get("source") in ("url", "git") and src.get("url"):
        return str(src["url"])
    raise PluginError(f"{name}@{market} has a source Flywheel does not read")
