"""tool_rescue.py -- repairs under witness, never silent fixes.

The Forge pattern (Show HN 2026-05-19): a validate/rescue/retry proxy
lifts small-model tool-calling substantially -- but its repairs happen
silently inside the proxy. This import keeps the lift and adds the
witness: each rescue is a NAMED deterministic transform, and the record
of what was repaired (original line, transform, repaired line) travels
with the calls so the ledger can carry it. A transform either produces a
call the strict parser accepts, or the emission stays garbage -- rescue
never invents intent.
"""
from __future__ import annotations

import re

_TOOL_COLON = re.compile(r"^(\s*)TOOL:\s+", flags=re.MULTILINE)


def _strip_inline_backticks(text: str) -> str:
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("`") and s.endswith("`") and "TOOL" in s:
            out.append(s.strip("`"))
        else:
            out.append(line)
    return "\n".join(out)


def _single_to_double_quotes(text: str) -> str:
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith("TOOL ") and '"' not in line:
            out.append(line.replace("'", '"'))
        else:
            out.append(line)
    return "\n".join(out)


def _strip_tool_colon(text: str) -> str:
    return _TOOL_COLON.sub(r"\1TOOL ", text)


_TRANSFORMS = (
    ("strip_inline_backticks", _strip_inline_backticks),
    ("single_to_double_quotes", _single_to_double_quotes),
    ("strip_tool_colon", _strip_tool_colon),
)


def rescue_tool_calls(text: str) -> tuple:
    """Parse strictly first; on failure, apply named transforms one at a
    time (cumulatively) until the strict parser accepts. Returns
    (calls, repairs) where each repair names its transform and shows the
    original -- the witness a silent proxy never leaves."""
    from .local_tools import parse_tool_calls
    calls = parse_tool_calls(text)
    if calls:
        return calls, []
    current = text
    repairs: list = []
    for name, fn in _TRANSFORMS:
        transformed = fn(current)
        if transformed == current:
            continue
        attempt = parse_tool_calls(transformed)
        repairs.append({
            "transform": name,
            "original": current.strip()[:300],
            "repaired": transformed.strip()[:300],
        })
        current = transformed
        if attempt:
            return attempt, repairs
    return [], []
