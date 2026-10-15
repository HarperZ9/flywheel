"""compare.py -- normalize two builds' streams and find the first divergence.

The rules come from normalization.json and nothing else: absolute paths of the
run's own folders become a token, then the listed patterns and keys are
rewritten. Streams are compared in a fixed order: model requests, stream-json
events, workspace file hashes, exit code, ledger kinds. Within a stream the
first differing element wins, and inside it the first differing field.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

STREAMS = ("requests", "events", "files", "exit", "ledger")
_ABSENT = "<absent>"


def rules_path() -> Path:
    return Path(__file__).with_name("normalization.json")


def load_rules(path: "str | Path | None" = None) -> dict:
    return json.loads(Path(path or rules_path()).read_text(encoding="utf-8"))


def file_sha256(path: "str | Path") -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _path_forms(path: str) -> list:
    forms = {path, path.replace("\\", "/"), path.replace("\\", "\\\\"),
             os.path.realpath(path), os.path.realpath(path).replace("\\", "/")}
    return sorted((f for f in forms if f), key=len, reverse=True)


class Normalizer:
    def __init__(self, rules: dict, masks: dict) -> None:
        order = rules["path_masks"]["order"]
        token = rules["path_masks"]["token"]
        flags = re.IGNORECASE if os.name == "nt" else 0
        self._paths = []
        for name in order:
            if masks.get(name):
                for form in _path_forms(masks[name]):
                    self._paths.append((re.compile(re.escape(form), flags),
                                        token.replace("{name}", name)))
        self._patterns = [(re.compile(p["regex"]), p["replace"]) for p in rules["patterns"]]
        self._keys = dict(rules["keys"])

    def text(self, value: str) -> str:
        for rx, token in self._paths:
            value = rx.sub(token.replace("\\", "\\\\"), value)
        for rx, repl in self._patterns:
            value = rx.sub(repl, value)
        return value

    def value(self, obj):
        if isinstance(obj, str):
            return self.text(obj)
        if isinstance(obj, list):
            return [self.value(v) for v in obj]
        if isinstance(obj, dict):
            return {self.text(k): (self._keys[k] if k in self._keys and v is not None
                                   else self.value(v)) for k, v in obj.items()}
        return obj


def normalize(run: dict, rules: dict) -> dict:
    """The five streams of one run with only the frozen rules applied."""
    norm = Normalizer(rules, run.get("masks", {}))
    return {name: norm.value(run["streams"][name]) for name in STREAMS}


def digest(streams: dict) -> str:
    raw = json.dumps(streams, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _excerpt(value, at: int = 0) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    start = max(0, at - 60)
    cut = text[start:start + 200]
    return ("..." if start else "") + cut + ("..." if start + 200 < len(text) else "")


def first_difference(a, b, path: str = "") -> "dict | None":
    """The first field where a and b differ, as a path and both excerpts."""
    if a == b:
        return None
    if isinstance(a, dict) and isinstance(b, dict):
        for key in list(a) + [k for k in b if k not in a]:
            sub = first_difference(a.get(key, _ABSENT), b.get(key, _ABSENT), f"{path}.{key}")
            if sub is not None:
                return sub
    if isinstance(a, list) and isinstance(b, list):
        for i in range(max(len(a), len(b))):
            sub = first_difference(a[i] if i < len(a) else _ABSENT,
                                   b[i] if i < len(b) else _ABSENT, f"{path}[{i}]")
            if sub is not None:
                return sub
    at = 0
    if isinstance(a, str) and isinstance(b, str):
        at = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return {"path": path or ".", "a": _excerpt(a, at), "b": _excerpt(b, at)}


def _label(stream: str, item) -> str:
    if stream == "events" and isinstance(item, dict):
        kind = item.get("event") or item.get("type")
        return f"{kind} {item.get('name', '')}".strip()
    if stream == "files" and isinstance(item, list) and item:
        return str(item[0])
    if stream == "ledger":
        return str(item)
    return ""


def diverge(name: str, a: dict, b: dict) -> "dict | None":
    """The first diverging event of one scenario, or None when all five match."""
    for stream in STREAMS:
        sa, sb = a[stream], b[stream]
        if sa == sb:
            continue
        if not isinstance(sa, list) or not isinstance(sb, list):
            return {"scenario": name, "stream": stream, "index": None, "label": "",
                    **first_difference(sa, sb)}
        for i in range(max(len(sa), len(sb))):
            ea = sa[i] if i < len(sa) else _ABSENT
            eb = sb[i] if i < len(sb) else _ABSENT
            found = first_difference(ea, eb)
            if found is not None:
                label = _label(stream, ea if ea != _ABSENT else eb)
                return {"scenario": name, "stream": stream, "index": i, "label": label,
                        **found}
    return None
