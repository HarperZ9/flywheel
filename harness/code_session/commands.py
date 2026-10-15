"""commands.py -- custom slash commands from Markdown files.

A file `review.md` in `.flywheel/commands/` (the project), `.claude/commands/`
(read for compatibility) or `commands/` in the Flywheel home becomes
`/review`. Its body is the request sent to the agent, with `$ARGUMENTS`
replaced by whatever followed the command. Optional front matter between `---`
lines may give a `description:` shown by /help. A command is only text: it
cannot grant a permission or run anything the request itself could not.
The first definition of a name wins, project before user, and a built-in
command cannot be replaced.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIRS = (Path(".flywheel") / "commands", Path(".claude") / "commands")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


@dataclass(frozen=True)
class Command:
    name: str
    body: str
    description: str
    source: str

    def expand(self, arguments: str) -> str:
        text = self.body.replace("$ARGUMENTS", arguments.strip())
        if "$ARGUMENTS" not in self.body and arguments.strip():
            text = f"{text}\n\n{arguments.strip()}"
        return text


def _split_front_matter(raw: str) -> "tuple[str, str]":
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            head = raw[3:end]
            match = re.search(r"^description:\s*(.+)$", head, re.M)
            return (match.group(1).strip() if match else ""), raw[end + 4:].lstrip("\n")
    return "", raw


def load_commands(root: str, home: "str | None", reserved=()) -> dict:
    folders = [Path(root) / d for d in PROJECT_DIRS]
    if home:
        folders.append(Path(home) / "commands")
    found: dict = {}
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md")):
            name = path.stem
            if not _NAME.match(name) or name in found or name in reserved:
                continue
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError:
                continue
            desc, body = _split_front_matter(raw)
            found[name] = Command(name, body.strip(), desc or f"custom command from {path.name}",
                                  str(path))
    return found
