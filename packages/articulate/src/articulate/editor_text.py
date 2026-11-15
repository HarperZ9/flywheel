"""Text helpers for the editor layer: the injection warning, math masking,
model-output cleanup and the deterministic detector summary.

Split out of editor.py, which re-exports every name here so existing imports of
articulate.editor keep working. Nothing here calls a model.
"""
import re


def injection_warning(text):
    """A one-block warning listing document lines that read as an assistant
    directive, or "" if none. The editor prints this before a rewrite; it does not
    block, because a document may quote such patterns in good faith."""
    from . import detector
    hits = detector.detect_injection(text)
    if not hits:
        return ""
    lines = [f"  L{h['line']} [{h['category']}] {h['label']}: {h['snippet']}" for h in hits]
    return ("[editor] WARNING: the document contains lines that read as instructions "
            "to an assistant. They are treated as content to edit, never obeyed:\n"
            + "\n".join(lines))


# Math spans a rewrite must never touch: a changed symbol, quantifier order, or
# inequality direction changes a theorem. Longest and display forms first so an
# inline pass does not split a display span.
_MATH_PATTERNS = [
    re.compile(r"\$\$.*?\$\$", re.S),
    re.compile(r"\\\[.*?\\\]", re.S),
    re.compile(r"\\\(.*?\\\)", re.S),
    re.compile(r"\$(?:\\.|[^$\\])*\$", re.S),
    re.compile(r"\\begin\{(equation|align|gather|multline|eqnarray|split|theorem"
               r"|lemma|proof|definition|proposition|corollary|claim)\*?\}"
               r".*?\\end\{\1\*?\}", re.S),
]
_MATH_PLACEHOLDER = "\u2983MATH{}\u2984"   # a distinctive bracket unlikely to be edited


def mask_math(text):
    """Replace every LaTeX math span with a numbered placeholder and return
    (masked_text, spans). The model never sees the math, so it cannot alter a
    formula. This is a structural guarantee that holds whatever the model returns."""
    spans = []

    def repl(m):
        spans.append(m.group(0))
        return _MATH_PLACEHOLDER.format(len(spans) - 1)

    for rx in _MATH_PATTERNS:
        text = rx.sub(repl, text)
    return text, spans


def splice_math(text, spans):
    """Restore masked math spans by placeholder, byte for byte."""
    for i, original in enumerate(spans):
        text = text.replace(_MATH_PLACEHOLDER.format(i), original)
    return text


def mechanical(path, profile=None):
    """Return (clean, summary_text) from the deterministic detector, for a file."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return True, "no mechanical findings"
    return mechanical_text(text, profile)


def assess(text, profile=None):
    """The full detector result under a profile/mode (findings + gate + low
    advisories). The editor threads the mode here, so it is no longer profile-blind."""
    from . import checkext
    return checkext.check_text(text, profile=profile)


def mechanical_text(text, profile=None):
    """Return (clean, summary_text) from the deterministic detector, for text."""
    r = assess(text, profile)
    hits = r["high"] + r["medium"]
    lines = [f"  L{h['line']} [{h['tier']} {h['category']}] {h['label']}: {h['snippet']}"
             for h in hits]
    tex = f"texture score {r['texture_score']}/100"
    summary = (f"{len(hits)} mechanical tell(s); {tex}\n" + "\n".join(lines)) if hits \
        else f"clean of mechanical tells; {tex}"
    return len(hits) == 0, summary


def strip_preamble(out):
    """Drop a leading 'Here is the rewrite:' style line if the model adds one."""
    out = re.sub(r"^\s*```[a-z]*\n", "", out)
    out = re.sub(r"\n```\s*$", "", out)
    lines = out.splitlines()
    if lines and re.match(r"(?i)^(here('?s| is)|sure|below|the rewrite|rewritten)\b.*:$",
                          lines[0].strip()):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines)
