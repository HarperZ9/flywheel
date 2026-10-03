"""Find private detail in an installed-app acceptance artifact.

make_installed_lanes_evidence.py refuses an artifact when any string in it,
a JSON key included, holds a local path, a user folder, a network path, an
e-mail address, a token or a name on the deny list (the runner account, the
local user and --deny). A network path counts at the start of a string, and
anywhere in it when written with two leading backslashes; a forward-slash
one counts only at the start, so a URL such as https://host/path stays clean.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PRIVATE = (
    ("local path", re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")),
    ("user folder", re.compile(r"(?i)[\\/](?:users|home)[\\/]")),
    ("network path", re.compile(r"^(?:\\\\|//)[^\\/]|\\\\[^\\/\s]+\\")),
    ("e-mail address", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("token", re.compile(r"\b(?:gh[opsur]_[A-Za-z0-9]{20,}|github_pat_\w{20,}"
                         r"|sk-[A-Za-z0-9_-]{16,})")),
)


def _strings(node, where: str):
    if isinstance(node, dict):
        for key, value in node.items():
            yield f"{where}.{key}", str(key)
            yield from _strings(value, f"{where}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _strings(value, f"{where}[{i}]")
    elif isinstance(node, str):
        yield where, node


def private_detail(root: Path, deny: list[str]) -> list[str]:
    """Every string in the artifact's files that holds a path, address, token or name."""
    names = [re.compile(rf"(?i)(?<![A-Za-z0-9]){re.escape(n)}(?![A-Za-z0-9])")
             for n in deny if n]
    found = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        text = path.read_bytes().decode("utf-8-sig")
        if path.suffix == ".json":
            strings = _strings(json.loads(text), "$")
        else:
            strings = ((f"line {i + 1}", line) for i, line in enumerate(text.splitlines()))
        for where, value in strings:
            rules = [rule for rule, rx in PRIVATE if rx.search(value)]
            rules += ["account name" for rx in names if rx.search(value)]
            found.extend(f"{rel}: {where}: {rule}" for rule in rules)
    return found
