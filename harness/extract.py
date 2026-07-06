"""extract.py — pull runnable code out of a chat model's answer.

Instruct code models wrap answers in markdown fences (```python ... ```) and
often add prose, despite "output only the function". Writing that verbatim into a
candidate file makes it un-importable — the exact reason a served model can score
0% while the harness itself is fine. This is the model-output -> candidate
adapter: take the fenced code (all blocks, in order); if a fence was opened but
truncated (hit max_new_tokens), take everything after it; otherwise pass bare code
through unchanged. Idempotent on already-clean code (StubProposer, references).
"""
from __future__ import annotations

import re

_FENCED = re.compile(r"```[ \t]*[A-Za-z0-9_+-]*[ \t]*\n(.*?)```", re.DOTALL)
_OPEN_FENCE = re.compile(r"```[ \t]*[A-Za-z0-9_+-]*[ \t]*\n(.*)\Z", re.DOTALL)


def extract_code(text: str) -> str:
    if not text:
        return ""
    blocks = _FENCED.findall(text)
    if blocks:
        code = "\n".join(b.rstrip() for b in blocks).strip()
        if code:
            return code + "\n"
    m = _OPEN_FENCE.search(text)          # opened but truncated fence
    if m and m.group(1).strip():
        return m.group(1).strip() + "\n"
    stripped = text.strip()
    return stripped + "\n" if stripped else ""
