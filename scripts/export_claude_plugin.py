#!/usr/bin/env python3
"""Export the Flywheel Verify Claude plugin as the root of its own repository.

The Claude directory validates a plugin from a Git repository. This repository
is too large for that check (more than 10,000 files and folders) and carries
line-ending rules in its root .gitattributes, so a directory listing has to come
from a small repository whose root is the plugin folder. This script builds that
tree from plugins/flywheel-verify, adds the single-plugin marketplace file
beside the manifest, and refuses to finish when the tree breaks one of the
directory's file rules.

    python scripts/export_claude_plugin.py --out DIR

DIR must be missing or empty. The script writes only inside DIR and runs no git
command, so creating and publishing the repository stays a separate step that a
person takes on purpose.

`layout_problems` is the rule check. tests/test_verify_plugin.py runs it on the
plugin folder and on an export, with controls that break each rule.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "plugins" / "flywheel-verify"

MAX_ENTRIES = 10_000             # files plus folders, or validation stops
MAX_FILES = 512                  # more is held for a reviewer
MAX_TEXT_BYTES = 256 * 1024      # a non-image file this size or larger is held
MAX_TOTAL_BYTES = 50 * 1024 * 1024
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
OS_FILES = {".DS_Store", "Thumbs.db", "desktop.ini", "__MACOSX"}
DEVICE_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                *(f"lpt{i}" for i in range(1, 10))}


class ExportError(Exception):
    """The export would produce a tree the directory refuses or holds."""


def _name_problems(rel: Path) -> list[str]:
    out = []
    for part in rel.parts:
        if ":" in part or part.endswith((".", " ")):
            out.append(f"{rel.as_posix()}: name is invalid on Windows")
        if part.split(".")[0].lower() in DEVICE_NAMES:
            out.append(f"{rel.as_posix()}: {part!r} is a reserved device name")
        if part in OS_FILES:
            out.append(f"{rel.as_posix()}: operating-system file")
    return out


def _file_problems(path: Path, rel: Path) -> list[str]:
    if path.suffix.lower() in IMAGE_SUFFIXES:
        return []
    if path.stat().st_size >= MAX_TEXT_BYTES:
        return [f"{rel.as_posix()}: {path.stat().st_size} bytes, over the text-file limit"]
    try:
        path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return [f"{rel.as_posix()}: not UTF-8 text; only text, images, and fonts pass"]
    return []


def _gitattributes_problems(path: Path, rel: Path) -> list[str]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        _pattern, *attrs = line.split()
        if attrs != ["-text"]:
            out.append(f"{rel.as_posix()}: {line!r} does more than turn conversion off")
    return out


def _walk(root: Path):
    """Every entry under root, without following a link into another folder."""
    stack = [root]
    while stack:
        folder = stack.pop()
        for entry in sorted(folder.iterdir()):
            yield entry
            if entry.is_dir() and not entry.is_symlink():
                stack.append(entry)


def layout_problems(root: Path) -> list[str]:
    """Each directory file rule the tree at `root` breaks, as readable lines."""
    out: list[str] = []
    if not (root / ".claude-plugin" / "plugin.json").is_file():
        out.append(".claude-plugin/plugin.json is missing")
    out += [f"{name} is missing" for name in ("README.md", "LICENSE")
            if not (root / name).is_file()]
    out += [f"{name} must not be at the plugin root" for name in ("bin", "CLAUDE.md")
            if (root / name).exists()]
    entries = files = total = 0
    seen: dict[str, str] = {}
    for path in _walk(root):
        rel = path.relative_to(root)
        entries += 1
        out += _name_problems(rel)
        key = rel.as_posix().lower()
        if key in seen:
            out.append(f"{rel.as_posix()}: differs from {seen[key]} only by case")
        seen[key] = rel.as_posix()
        if path.is_symlink():
            out.append(f"{rel.as_posix()}: symbolic link")
        elif path.is_file():
            files += 1
            total += path.stat().st_size
            out += _file_problems(path, rel)
            if path.name == ".gitattributes":
                out += _gitattributes_problems(path, rel)
    if entries >= MAX_ENTRIES:
        out.append(f"{entries} files and folders; the limit is under {MAX_ENTRIES}")
    if files > MAX_FILES:
        out.append(f"{files} files; more than {MAX_FILES} is held")
    if total >= MAX_TOTAL_BYTES:
        out.append(f"{total} bytes in all; the archive limit is 50 MiB")
    return out


def marketplace(manifest: dict) -> dict:
    """The one-plugin marketplace file that lets Claude Code install from the repo."""
    return {"name": manifest["name"],
            "owner": {"name": manifest["author"]["name"]},
            "description": manifest["description"],
            "plugins": [{"name": manifest["name"], "source": "./",
                         "description": manifest["description"]}]}


def export(out: Path, source: Path = SOURCE) -> list[str]:
    """Copy the plugin to `out` as a repository root; return the files written."""
    problems = layout_problems(source)
    if problems:
        raise ExportError("the plugin folder breaks directory rules:\n  "
                          + "\n  ".join(problems))
    if out.exists() and any(out.iterdir()):
        raise ExportError(f"{out} is not empty; export into a new folder")
    written = []
    for path in _walk(source):
        rel = path.relative_to(source)
        if path.is_dir():
            (out / rel).mkdir(parents=True, exist_ok=True)
            continue
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, out / rel)
        written.append(rel.as_posix())
    manifest = json.loads((source / ".claude-plugin" / "plugin.json").read_text(
        encoding="utf-8"))
    market = out / ".claude-plugin" / "marketplace.json"
    market.write_bytes((json.dumps(marketplace(manifest), indent=2) + "\n").encode("utf-8"))
    written.append(market.relative_to(out).as_posix())
    problems = layout_problems(out)
    if problems:
        raise ExportError("the exported tree breaks directory rules:\n  "
                          + "\n  ".join(problems))
    return sorted(written)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True,
                        help="a missing or empty folder to write the repository tree into")
    args = parser.parse_args(argv)
    try:
        written = export(args.out.resolve())
    except ExportError as exc:
        print(f"export refused: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {len(written)} files to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
