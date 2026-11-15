"""parser-contract family: the ladder model and its reference implementation.

A VARIANT is one fully normative extraction contract: an ordered ladder of
rungs plus three semantic switches. The reference implementation here is the
single source of truth; the generator runs it over the input grammar and
freezes the results, and the environment's prompt renders the same variant as
prose. Nothing in this module is random: the 96 variants come from a fixed
table crossed with the three switches.

Normative semantics, stated once and implemented once:

- SCOPE. ``last``: only the last message's content is searched. ``joined``:
  all message contents joined with a single newline, in order. A plain-string
  completion is its own scope either way.
- CONTENT PARTS. A list-typed message content contributes its ``text``-typed
  parts joined by one space, then stripped.
- THINK STRIP (when the variant enables it). Every ``<think>...</think>``
  section is removed from the scope text, repeatedly, but ONLY where both tags
  are present in order; a lone open or close tag strips nothing.
- RUNGS, tried in ladder order on the scope text; first HIT wins:
  - ``tag:NAME``  -- the LAST ``<NAME>`` that has a ``</NAME>`` after it;
    content is the text between, stripped.
  - ``fence:LANG`` -- the LAST fenced code block opened with exactly
    ```` ```LANG ````; content stripped.
  - ``prefix:MARKER`` -- the LAST line whose lstripped form starts with
    MARKER; content is the remainder of that line, stripped.
  - ``lastline`` -- the LAST line containing a non-whitespace character,
    stripped. (Never empty when it hits.)
- EMPTY RULE. When a rung's extracted content strips to ``""``: with
  ``empty_hit`` the rung HITS and the answer is ``""``; without it the rung
  MISSES and the ladder falls through.
- All rungs miss: the answer is ``None``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---- variant model ----------------------------------------------------------

# Twelve fixed ladders, three per depth 1-4. Crossed with scope x think x
# empty (8 combos) they yield the family's 96 variants.
LADDERS: tuple[tuple[str, ...], ...] = (
    ("tag:answer",),
    ("fence:python",),
    ("prefix:ANSWER:",),
    ("tag:answer", "lastline"),
    ("fence:python", "tag:result"),
    ("prefix:FINAL:", "fence:json"),
    ("tag:answer", "fence:python", "lastline"),
    ("tag:result", "prefix:ANSWER:", "fence:python"),
    ("fence:json", "tag:answer", "prefix:FINAL:"),
    ("tag:answer", "tag:result", "fence:python", "lastline"),
    ("prefix:ANSWER:", "fence:python", "tag:result", "lastline"),
    ("fence:python", "fence:json", "tag:answer", "prefix:FINAL:"),
)


@dataclass(frozen=True)
class Variant:
    ladder: tuple[str, ...]
    scope: str  # "last" | "joined"
    think_strip: bool
    empty_hit: bool

    @property
    def variant_id(self) -> str:
        ladder_ix = LADDERS.index(self.ladder)
        return (
            f"pc-{ladder_ix:02d}-{self.scope}"
            f"-think{int(self.think_strip)}-empty{int(self.empty_hit)}"
        )


def all_variants() -> list[Variant]:
    out = []
    for ladder in LADDERS:
        for scope in ("last", "joined"):
            for think_strip in (False, True):
                for empty_hit in (False, True):
                    out.append(Variant(ladder, scope, think_strip, empty_hit))
    return out


# ---- reference implementation ----------------------------------------------

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _part_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        return " ".join(texts).strip()
    return ""


def _message_content(message: object) -> str:
    if isinstance(message, dict):
        return _part_text(message.get("content", ""))
    return _part_text(getattr(message, "content", ""))


def scope_text(completion: object, scope: str) -> str:
    if isinstance(completion, str):
        return completion
    messages = list(completion) if isinstance(completion, (list, tuple)) else []
    if not messages:
        return ""
    if scope == "last":
        return _message_content(messages[-1])
    return "\n".join(_message_content(m) for m in messages)


def strip_think(text: str) -> str:
    """Remove every complete <think>...</think> section; lone tags survive."""
    while True:
        stripped = _THINK_RE.sub("", text, count=1)
        if stripped == text:
            return text
        text = stripped


def _rung_tag(text: str, name: str) -> tuple[bool, str]:
    open_tag, close_tag = f"<{name}>", f"</{name}>"
    start = -1
    pos = text.find(open_tag)
    while pos != -1:
        if text.find(close_tag, pos + len(open_tag)) != -1:
            start = pos
        pos = text.find(open_tag, pos + 1)
    if start == -1:
        return False, ""
    inner_start = start + len(open_tag)
    inner_end = text.find(close_tag, inner_start)
    return True, text[inner_start:inner_end].strip()


_FENCE_RES: dict[str, re.Pattern[str]] = {}


def _rung_fence(text: str, lang: str) -> tuple[bool, str]:
    if lang not in _FENCE_RES:
        _FENCE_RES[lang] = re.compile(
            rf"```{re.escape(lang)}[ \t]*\n(.*?)```", re.DOTALL
        )
    matches = _FENCE_RES[lang].findall(text)
    if not matches:
        return False, ""
    return True, matches[-1].strip()


def _rung_prefix(text: str, marker: str) -> tuple[bool, str]:
    hit = None
    for line in text.splitlines():
        if line.lstrip().startswith(marker):
            hit = line.lstrip()[len(marker) :]
    if hit is None:
        return False, ""
    return True, hit.strip()


def _rung_lastline(text: str) -> tuple[bool, str]:
    for line in reversed(text.splitlines()):
        if line.strip():
            return True, line.strip()
    return False, ""


def _run_rung(rung: str, text: str) -> tuple[bool, str]:
    if rung == "lastline":
        return _rung_lastline(text)
    kind, _, arg = rung.partition(":")
    if kind == "tag":
        return _rung_tag(text, arg)
    if kind == "fence":
        return _rung_fence(text, arg)
    if kind == "prefix":
        return _rung_prefix(text, arg)
    raise ValueError(f"unknown rung: {rung!r}")


def reference_parse(variant: Variant, completion: object) -> str | None:
    """THE contract. The generator freezes this function's outputs; the
    environment's prose prompt is rendered from the same variant."""
    text = scope_text(completion, variant.scope)
    if variant.think_strip:
        text = strip_think(text)
    for rung in variant.ladder:
        hit, content = _run_rung(rung, text)
        if not hit:
            continue
        if content == "" and not variant.empty_hit:
            continue
        return content
    return None
