"""rules.py -- standing allow and deny rules for a coding session.

Rules live in `.flywheel/permissions.json` in the project and in
`permissions.json` in the Flywheel home:

    {"allow": ["run:python -m pytest*", "write_file:src/*"],
     "deny":  ["run:git push*", "write_file:.env*", "*:secrets/*"]}

A rule is `TOOL:PATTERN`. TOOL is a tool name or `*`; PATTERN is a shell-style
wildcard matched against the call's subject: the command for `run`, the path
for a file tool, and the call's JSON for anything else. A deny rule wins over
every mode, `auto` included, and over an allow rule. An allow rule turns an
"ask" into a yes without a prompt; it never opens what plan mode closes.
Each match is recorded with the rule that matched.
"""
from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_FILE = Path(".flywheel") / "permissions.json"
USER_FILE = "permissions.json"


def subject(name: str, args: dict) -> str:
    if name == "run":
        return str(args.get("cmd", ""))
    if name == "web_fetch":
        return str(args.get("url", ""))
    if "path" in args:
        return str(args.get("path", "")).replace("\\", "/")
    return json.dumps(args, sort_keys=True)


def _matches(rule: str, name: str, subj: str) -> bool:
    tool, sep, pattern = rule.partition(":")
    if not sep:
        return False
    if tool != "*" and tool != name:
        return False
    return fnmatch.fnmatchcase(subj, pattern)


@dataclass
class Rules:
    allow: list = field(default_factory=list)
    deny: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def match(self, name: str, args: dict) -> "tuple[str, str] | None":
        """("deny" | "allow", rule) for the first matching rule, deny first."""
        subj = subject(name, args)
        for rule in self.deny:
            if _matches(rule, name, subj):
                return "deny", rule
        for rule in self.allow:
            if _matches(rule, name, subj):
                return "allow", rule
        return None


def _read(path: Path, rules: Rules) -> None:
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        rules.errors.append(f"{path}: {e.__class__.__name__}")
        return
    if not isinstance(data, dict):
        rules.errors.append(f"{path}: expected an object with allow and deny lists")
        return
    for key in ("allow", "deny"):
        items = data.get(key, [])
        if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
            rules.errors.append(f"{path}: {key} must be a list of strings")
            continue
        getattr(rules, key).extend(items)
    rules.sources.append(str(path))


def load_rules(root: str, home: "str | None") -> Rules:
    """User rules then project rules; both lists are merged."""
    rules = Rules()
    if home:
        _read(Path(home) / USER_FILE, rules)
    _read(Path(root) / PROJECT_FILE, rules)
    return rules
