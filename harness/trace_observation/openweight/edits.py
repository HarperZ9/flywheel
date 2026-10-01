"""edits.py -- reasoning-span edits for the open-weight faithfulness interventions.

Ported from the round-2 pilot pre-registration, which applied the round-1
critic's fixes:

- Truncation snaps back to the last sentence end, so a cut does not stop
  mid-sentence (the critic found mid-sentence cuts confound disruption with
  information removal).
- The error edit changes one number (the last numeric literal on the first
  line past the cut, plus one on its integer part), so it reads like an
  arithmetic slip, not a self-evident one. It comes with an unedited prefix and
  a neutral control (one extra space before the same literal) so the edit is
  isolated from any small token change.
- The code mask replaces fenced blocks and Python-looking lines with one
  marker, so a code-task truncation result can be told apart from the answer
  copying a drafted program.
- Filler is kept only as a disruption probe beside the empty-span arm. Round 1
  showed filler hurt more than an empty trace on qwen3:8b, so it is never the
  null.
"""
from __future__ import annotations

import random
import re

_SENT_END = re.compile(r"(?:[.!?](?=\s)|\n)")
NUM = re.compile(r"(?<![\w.])(\d+)(\.\d+)?(?!\w|\.\d)")
MASK = "[code omitted]"
_FENCE = re.compile(r"```[^\n]*\n.*?(?:```|\Z)", re.S)
_CODE_LINE = re.compile(
    r"^\s*(?:def |class |return\b|import |from \w[\w.]* import |for .*:\s*$|while .*:\s*$|"
    r"if .*:\s*$|elif .*:\s*$|else:\s*$|try:\s*$|except\b.*:\s*$|finally:\s*$|with .*:\s*$|"
    r"print\(|assert |yield\b|pass\s*$|break\s*$|continue\s*$|"
    r"[A-Za-z_][\w\[\], .]*\s*(?:[+\-*/%]|//)?=\s*\S|>>> |"
    r"[A-Za-z_][\w.]*\(.*\)\s*$|"
    r"['\"][^'\"]*['\"]\s*:\s*\S.*,?\s*$)")


def char_cut(text: str, tokens, frac: float) -> int:
    """Character position of a fraction cut: by token count when tokens exist."""
    if tokens:
        return len("".join(tokens[: int(len(tokens) * frac)]))
    return int(len(text) * frac)


def sentence_truncate(text: str, cut: int) -> str:
    """Longest prefix ending at a sentence end at or before cut; empty if none."""
    end = 0
    for m in _SENT_END.finditer(text, 0, cut):
        end = m.end()
    return text[:end]


def truncate_fraction(text: str, frac: float, tokens=None) -> str:
    if frac <= 0:
        return ""
    if frac >= 1:
        return text
    return sentence_truncate(text, char_cut(text, tokens, frac))


def error_edit(text: str, cut: int) -> dict:
    """PREFIX (unedited), ERROR (one literal +1) and NEUTRAL (extra space), all
    ending with the edited line. Every value is None when no line qualifies."""
    lines = text.splitlines(keepends=True)
    pos = 0
    for i, ln in enumerate(lines):
        end = pos + len(ln)
        if end > cut:
            ms = list(NUM.finditer(ln))
            if ms:
                m = ms[-1]
                head = "".join(lines[:i])
                bumped = str(int(m.group(1)) + 1) + (m.group(2) or "")
                err = ln[:m.start()] + bumped + ln[m.end():]
                neu = ln[:m.start()] + " " + ln[m.start():]
                return {"prefix": head + ln, "error": head + err, "neutral": head + neu,
                        "line_index": i, "orig_literal": m.group(0), "error_literal": bumped}
        pos = end
    return {"prefix": None, "error": None, "neutral": None, "line_index": None}


def mask_code(text: str) -> str:
    """Fenced blocks and Python-looking lines become one marker per run."""
    t = _FENCE.sub(MASK + "\n", text)
    out, prev = [], False
    for ln in t.splitlines():
        is_mask = ln.strip() == MASK or bool(_CODE_LINE.match(ln))
        if is_mask and not prev:
            out.append(MASK)
        elif not is_mask:
            out.append(ln)
        prev = is_mask
    return "\n".join(out)


def leak_share(trace: str, code: str, prompt: str = ""):
    """Share of the code's non-trivial lines (not already in the prompt) that
    appear verbatim as whole lines of the trace. None when the code has none."""
    skip = {ln.strip() for ln in prompt.splitlines()}
    lines = [s for s in (ln.strip() for ln in code.splitlines())
             if len(s) > 3 and not s.startswith("#") and not s.startswith(('"""', "'''"))
             and s not in skip]
    if not lines:
        return None
    have = {ln.strip() for ln in trace.splitlines()}
    return sum(1 for s in lines if s in have) / len(lines)


def filler(text: str, tokens=None) -> str:
    """Disruption probe: one ' ...' per token (or per 4 characters). Not a null."""
    n = len(tokens) if tokens else max(1, len(text) // 4)
    return " ..." * n


def shuffle_lines(text: str, seed: int) -> str:
    lines = text.splitlines()
    random.Random(seed).shuffle(lines)
    return "\n".join(lines)
