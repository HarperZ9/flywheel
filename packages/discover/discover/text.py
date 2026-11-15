"""Reading a README opening and a changelog section.

Both checks are heuristics about form. They find the first prose paragraph and
the first runnable command; they cannot judge whether the sentence names a real
benefit. A person still reads it.
"""
from __future__ import annotations

import re

FENCE = re.compile(r"^\s*(```|~~~)\s*([\w+-]*)")
NOT_SHELL = {"python", "py", "json", "toml", "yaml", "yml", "rust", "rs", "c", "cpp", "c++",
             "js", "javascript", "ts", "typescript", "html", "css", "xml", "go", "java",
             "diff", "mermaid", "hlsl", "glsl", "bld", "ini", "csv"}
COMMAND = re.compile(r"^(?:\$\s+|>\s+|PS>\s+)?([a-z][\w.+-]*(?:/[\w.+-]+)*)(?:\s+\S|$)")
SKIP_LINE = re.compile(r"^\s*(?:#|<|!\[|\[!\[|\||>|\[.*\]\(.*\)\s*(\|.*)?$|-{3,}|\*{3,}|={3,})")
SENTENCE_END = re.compile(r"[.!?:](?:\s|$)")
LIST_START = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|#|\||`|>)")


def first_paragraph(lines: list[str]) -> tuple[int, str] | None:
    """Line number (1-based) and text of the first prose paragraph outside code."""
    in_fence = False
    in_html = False
    for i, raw in enumerate(lines):
        line = raw.strip()
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("<") and not line.endswith(">"):
            in_html = True
        if in_html:
            in_html = not line.endswith(">")
            continue
        if not line or SKIP_LINE.match(line) or LIST_START.match(line):
            continue
        para = [line]
        for nxt in lines[i + 1:]:
            if not nxt.strip() or FENCE.match(nxt) or LIST_START.match(nxt):
                break
            para.append(nxt.strip())
        return i + 1, " ".join(para)
    return None


def first_command(lines: list[str], window: int) -> tuple[int, str] | None:
    """The first shell-like command in a fenced block that starts within `window` lines."""
    in_fence = False
    lang = ""
    for i, raw in enumerate(lines):
        match = FENCE.match(raw)
        if match:
            if not in_fence and i >= window:
                return None
            in_fence = not in_fence
            lang = match.group(2).lower() if in_fence else ""
            continue
        if not in_fence or lang in NOT_SHELL:
            continue
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if COMMAND.match(line):
            return i + 1, line
    return None


def changelog_section(text: str, version: str | None) -> tuple[str, str] | None:
    """Heading and body of the section for `version`, or the newest section with content."""
    sections = re.split(r"(?m)^(##\s+.*)$", text)
    pairs = [(sections[k].strip(), sections[k + 1]) for k in range(1, len(sections) - 1, 2)]
    if version:
        token = re.compile(r"^##\s+\[?v?" + re.escape(version.lstrip("v")) + r"(?![\w.])")
        for heading, body in pairs:
            if token.search(heading):
                return heading, body
        return None
    # With no release named, read the newest released section; an Unreleased
    # section is often a placeholder. Fall back to it only when nothing else exists.
    filled = [(h, b) for h, b in pairs if paragraphs(b)]
    released = [(h, b) for h, b in filled if "unreleased" not in h.lower()]
    return (released or filled or [None])[0]


def paragraphs(body: str) -> list[str]:
    out, cur = [], []
    for line in body.splitlines():
        if line.strip().startswith("###"):
            continue
        if line.strip():
            if LIST_START.match(line) and cur:
                out.append(" ".join(cur))
                cur = []
            cur.append(line.strip())
        elif cur:
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def is_summary(paragraph: str) -> bool:
    """A prose sentence of six words or more, not a list item, heading or table."""
    if LIST_START.match(paragraph):
        return False
    return len(paragraph.split()) >= 6 and bool(SENTENCE_END.search(paragraph))
