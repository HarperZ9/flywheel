"""git_config_guard.py -- which lines a sandboxed command may add to .git/config.

A repository's config can name programs that git starts later: `core.hooksPath`,
`core.fsmonitor`, `core.sshCommand`, `core.pager`, `diff.external`, an alias
that begins with `!`, a filter driver, a credential helper, an `include`. A
command that runs inside the sandbox and writes one of those has arranged for
code to run outside it, the next time anyone runs git in the project.

Ordinary git work also writes this file: `git init` creates it, `git remote
add` and `git checkout -b` add lines to it. So the file stays writable and the
additions are checked. Each added entry has to be on the allowlist below, and
every key on the allowlist is one git reads as data and never as a command.
Removing a line is always allowed.

Everything here is a pure function of bytes, so the rule can be read and
tested on any host.
"""
from __future__ import annotations

import re
from collections import Counter

#: Sections that take no subsection, and the keys a command may add to them.
PLAIN = {
    "core": {"repositoryformatversion", "filemode", "bare", "logallrefupdates",
             "symlinks", "ignorecase", "precomposeunicode", "autocrlf",
             "longpaths"},
    "user": {"name", "email"},
    "init": {"defaultbranch"},
    "extensions": {"objectformat"},
}
#: Sections that need a subsection (`[remote "origin"]`), with their keys.
NAMED = {
    "branch": {"remote", "merge"},
    "remote": {"url", "fetch", "pushurl"},
    "submodule": {"url", "active"},
}
URL_KEYS = frozenset({"url", "pushurl"})

_HEADER = re.compile(r'^\[\s*([A-Za-z0-9.-]+)\s*(?:"((?:[^"\\]|\\.)*)")?\s*\]$')
_ENTRY = re.compile(r"^([A-Za-z][A-Za-z0-9-]*)\s*(?:=\s*(.*))?$")


def _safe_url(value: str) -> bool:
    """A remote address git treats as an address.

    `ext::sh -c ...` and every other `<helper>::<address>` form start a
    program, and a value that begins with `-` can be read as an option.
    """
    return bool(value) and not value.startswith("-") and "::" not in value \
        and not any(ord(ch) < 32 for ch in value)


def safe_entry(section: str, sub, key: str, value: str) -> bool:
    """True when git reads this entry as data and never as a command."""
    if value.endswith("\\"):          # a continued line hides what follows
        return False
    table = PLAIN if sub is None else NAMED
    if key not in table.get(section, ()):
        return False
    return key not in URL_KEYS or _safe_url(value)


def parse(data: bytes) -> list:
    """Every line of a config as (line, kind, entry).

    `kind` is "blank", "header", "entry" or "unknown". An entry is
    (section, subsection, key, value) with section and key in lower case. A
    line this parser cannot read is "unknown", and an unknown line is never
    safe: git may read more forms than this does, and guessing would let one
    through.
    """
    rows, section, sub = [], None, None
    for line in data.decode("utf-8", "replace").splitlines():
        text = line.strip()
        if not text or text[0] in "#;":
            rows.append((line, "blank", None))
            continue
        head = _HEADER.match(text)
        if head:
            section, sub = head.group(1).lower(), head.group(2)
            rows.append((line, "header", None))
            continue
        item = None if text.startswith("[") else _ENTRY.match(text)
        if item is None or section is None:
            if text.startswith("["):
                section, sub = "?", None
            rows.append((line, "unknown", None))
            continue
        entry = (section, sub, item.group(1).lower(), (item.group(2) or "").strip())
        rows.append((line, "entry", entry))
    return rows


def _label(row) -> str:
    line, kind, entry = row
    if kind == "unknown":
        return f"unreadable line {line.strip()[:60]!r}"
    section, sub, key, _value = entry
    return f"{section}.{sub}.{key}" if sub is not None else f"{section}.{key}"


def unsafe_additions(before: "bytes | None", after: bytes) -> list:
    """Names of the entries `after` adds that are not on the allowlist.

    An entry already in `before` with the same value is the user's own and is
    not judged. `before` is None for a config the command created.
    """
    had = Counter(row[2] if row[1] == "entry" else row[0].strip()
                  for row in parse(before or b"") if row[1] in ("entry", "unknown"))
    found = []
    for row in parse(after):
        if row[1] not in ("entry", "unknown"):
            continue
        token = row[2] if row[1] == "entry" else row[0].strip()
        if had[token] > 0:
            had[token] -= 1
        elif row[1] == "unknown" or not safe_entry(*row[2]):
            found.append(_label(row))
    return found


def strip_unsafe(data: bytes) -> bytes:
    """`data` with every entry that is not on the allowlist removed.

    Used for a config the command created, where there are no earlier bytes
    to put back and deleting the file would break the new repository.
    """
    kept = [line for line, kind, entry in parse(data)
            if kind in ("blank", "header") or (kind == "entry" and safe_entry(*entry))]
    return ("\n".join(kept) + "\n").encode("utf-8")
