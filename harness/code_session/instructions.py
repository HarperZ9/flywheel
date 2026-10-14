"""instructions.py -- the project's own instructions, folded into the session.

A repository states its house rules once, in a file the agent reads on every
session. The field has settled on a few names: AGENTS.md (read by nearly every
harness), CLAUDE.md, and a tool-specific file. Flywheel reads all three names,
from the working folder up to the repository root, plus one user-level file in
the Flywheel home, so a rule written for another harness is not silently
ignored here.

Order matters when two files disagree: the user file comes first and the file
nearest the working folder comes last, so the most specific rule is the one the
model read most recently. Text is folded in verbatim, never summarized, and the
whole set is capped so a huge file degrades to a flagged truncation instead of
filling a small model's context. Every file read is listed by path and sha256 so
the session ledger can say exactly which rules were in force.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

NAMES = ("AGENTS.md", "CLAUDE.md", "FLYWHEEL.md")
USER_FILE = "AGENTS.md"
MAX_BYTES = 32 * 1024


@dataclass(frozen=True)
class Instruction:
    path: str
    text: str
    sha256: str
    truncated: bool

    def record(self) -> dict:
        return {"path": self.path, "sha256": self.sha256, "truncated": self.truncated}


def _repo_top(start: Path) -> Path:
    """The nearest ancestor holding .git, else the start folder itself."""
    for folder in (start, *start.parents):
        if (folder / ".git").exists():
            return folder
    return start


def _chain(root: Path, stop: "Path | None" = None) -> list[Path]:
    """Folders from the repository top down to root, top first.

    The walk never climbs to `stop` (the user's home by default) or above it:
    a home folder that happens to be a Git repository must not hand every
    project the home folder's own instruction files."""
    stop = (stop if stop is not None else Path.home()).resolve()
    top = _repo_top(root)
    chain = [root]
    folder = root
    while folder != top and folder.parent != folder:
        folder = folder.parent
        if folder == stop or folder in stop.parents:
            break
        chain.append(folder)
    return list(reversed(chain))


def candidate_files(root: str, home: "str | None") -> list[Path]:
    """Every instruction file that exists, in the order the model reads them."""
    found: list[Path] = []
    if home:
        user = Path(home) / USER_FILE
        if user.is_file():
            found.append(user)
    for folder in _chain(Path(root).resolve()):
        for name in NAMES:
            p = folder / name
            if p.is_file() and p not in found:
                found.append(p)
    return found


def load_instructions(root: str, home: "str | None" = None,
                      max_bytes: int = MAX_BYTES) -> list[Instruction]:
    """Read the instruction files, capping the total at max_bytes."""
    out: list[Instruction] = []
    budget = max_bytes
    for p in candidate_files(root, home):
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        digest = hashlib.sha256(raw).hexdigest()
        keep = raw[:max(budget, 0)]
        text = keep.decode("utf-8", errors="replace")
        out.append(Instruction(str(p), text, digest, truncated=len(keep) < len(raw)))
        budget -= len(keep)
    return out


def system_addendum(instructions: list[Instruction], root: str) -> str:
    """The text appended to the system prompt; empty when there is none."""
    if not instructions:
        return ""
    blocks = []
    for ins in instructions:
        try:
            shown = os.path.relpath(ins.path, root)
        except ValueError:          # another drive on Windows
            shown = ins.path
        tail = "\n[... truncated ...]" if ins.truncated else ""
        blocks.append(f"Project instructions ({shown}):\n{ins.text}{tail}")
    return "\n\n".join(blocks)


INIT_TEMPLATE = """# Agent instructions

This file tells coding agents (Flywheel, and any harness that reads AGENTS.md)
how to work in this repository. Edit it; agents read it at the start of every
session.

## Project

{languages}

## Commands

{commands}

## Rules

- Run the tests before calling a change finished.
- Keep changes small and focused on the task.
"""

_LANG_MARKERS = (("pyproject.toml", "Python"), ("setup.py", "Python"),
                 ("package.json", "JavaScript or TypeScript"), ("Cargo.toml", "Rust"),
                 ("go.mod", "Go"), ("pom.xml", "Java"), ("build.gradle", "Java or Kotlin"),
                 ("pubspec.yaml", "Dart or Flutter"), ("CMakeLists.txt", "C or C++"))
_TEST_HINTS = (("pyproject.toml", "python -m pytest"), ("package.json", "npm test"),
               ("Cargo.toml", "cargo test"), ("go.mod", "go test ./..."))


def draft_agents_md(root: str) -> str:
    """A starting AGENTS.md from what the folder shows; a draft, never a claim."""
    base = Path(root)
    langs = sorted({lang for marker, lang in _LANG_MARKERS if (base / marker).exists()})
    tests = [cmd for marker, cmd in _TEST_HINTS if (base / marker).exists()]
    languages = ("Languages detected from build files: " + ", ".join(langs) + "."
                 if langs else "No build file was found; describe the project here.")
    commands = ("\n".join(f"- Test (guessed from the build file, check it): `{c}`" for c in tests)
                if tests else "- Test: (add the command that runs the tests)")
    return INIT_TEMPLATE.format(languages=languages, commands=commands)


def write_init(root: str) -> "tuple[bool, str]":
    """Create AGENTS.md if absent. Never overwrites an existing file."""
    target = Path(root) / "AGENTS.md"
    if target.exists():
        return False, f"{target} already exists; nothing was changed"
    target.write_text(draft_agents_md(root), encoding="utf-8")
    return True, f"wrote {target}; edit it to match the project"
