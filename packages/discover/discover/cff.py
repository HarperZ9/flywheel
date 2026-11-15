"""A small reader for CITATION.cff files.

CFF is YAML. This reader handles the subset citation files use in practice:
top-level `key: value` pairs, quoted or plain scalars, lists of scalars and
lists of mappings (`authors`). It is not a general YAML parser; a file it cannot
read is reported as a finding, never a crash.
"""
from __future__ import annotations

import re

REQUIRED = ("cff-version", "message", "title", "authors")
KEY = re.compile(r"^([A-Za-z][\w-]*):\s*(.*)$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value.split(" #")[0].strip()


def parse(text: str) -> dict:
    data: dict = {}
    key = None
    item: dict | None = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[0].isspace() and not raw.startswith("-"):
            match = KEY.match(raw)
            if not match:
                raise ValueError(f"cannot read line: {raw!r}")
            key, value = match.group(1), match.group(2)
            data[key] = _scalar(value) if value.strip() else []
            item = None
            continue
        stripped = raw.strip()
        if key is None or not isinstance(data.get(key), list):
            raise ValueError(f"unexpected indented line: {raw!r}")
        if stripped.startswith("- "):
            body = stripped[2:]
            match = KEY.match(body)
            if match:
                item = {match.group(1): _scalar(match.group(2))}
                data[key].append(item)
            else:
                item = None
                data[key].append(_scalar(body))
            continue
        match = KEY.match(stripped)
        if match and item is not None:
            item[match.group(1)] = _scalar(match.group(2))
        else:
            raise ValueError(f"cannot read line: {raw!r}")
    return data


def problems(data: dict, version: str | None = None) -> list[str]:
    """Each way the parsed file falls short of CFF 1.2.0's required shape."""
    out = [f"missing required key {k}" for k in REQUIRED if not data.get(k)]
    authors = data.get("authors") or []
    for i, author in enumerate(authors if isinstance(authors, list) else []):
        if not isinstance(author, dict) or not (author.get("family-names") or author.get("name")):
            out.append(f"author {i + 1} has neither family-names nor name")
    if data.get("cff-version") and not str(data["cff-version"]).startswith("1."):
        out.append(f"cff-version {data['cff-version']} is not 1.x")
    if data.get("date-released") and not DATE.match(str(data["date-released"])):
        out.append("date-released is not YYYY-MM-DD")
    if version and data.get("version") and str(data["version"]).lstrip("v") != version.lstrip("v"):
        out.append(f"version {data['version']} differs from the package version {version}")
    return out
