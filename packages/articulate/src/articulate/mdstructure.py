"""Markdown structure masks for the check layer. Standard library only.

The pinned detector reads a few Markdown structures as prose: a table delimiter
row such as `|---|---|` reads as an em-dash, an indented code block and TOML
front matter read as sentences, and a capitalised proper name such as
"Transformative AI Fund" reads as register vocabulary. The detector closure is
byte-pinned, so the fix lives here, in front of it.

`mask_structure` blanks those structures with spaces before the detector runs.
A delimiter row keeps its pipes, so the table stays one paragraph.
`name_spans` finds register-word findings that sit inside a run of capitalised
words, and `mask_spans` hides those words behind same-length placeholder letters
for a second detector pass. Every mask keeps the text length and line breaks,
so a finding's offsets stay valid in the original text, and `restore` copies
`match` and `snippet` back from the original.

The masks are versioned, because a receipt replays under the masks it names.
`markdown/1` is the 0.14.0 set. `markdown/2` adds inline and display math
(`$a---b$`, `$$x$$`, a `$$` block) and a name at the start of a sentence when
the same capitalised run appears in the document away from a sentence start.
A dollar amount is not math: an opening `$` needs a non-space after it, a
closing `$` needs a non-space before it and no digit after it, and an escaped
dollar never opens or closes. Pandoc uses the same rule.
"""
import re

from .markup import is_md_hr, is_md_table_sep

VERSIONS = ("markdown/1", "markdown/2")
VERSION = VERSIONS[-1]

_FENCE = re.compile(r"^\s*(```|~~~)")
_LIST = re.compile(r"^ {0,3}(?:[-*+]|\d{1,9}[.)])(?:\s|$)")
_HEADING = re.compile(r"^ {0,3}#{1,6}(?:\s|$)")
_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
_LEAD = re.compile(r"^[\s>#*+|\-\d.)(\"'“‘\[_`]*")
_ENDERS = ".!?:"
_DISPLAY = re.compile(r"(?<!\\)\$\$(?=\S)[^$\n]*?\S\$\$")
_INLINE = re.compile(r"(?<![\\$])\$(?![\s$])(?:[^$\n]*?[^\s\\$])?\$(?![\d$])")


def _level(version):
    if version not in VERSIONS:
        raise ValueError(f"unknown structure masks {version!r}")
    return VERSIONS.index(version) + 1


def _mask_math(line):
    """The line with inline `$...$` and `$$...$$` spans blanked."""
    for pattern in (_DISPLAY, _INLINE):
        line = pattern.sub(lambda m: " " * len(m.group(0)), line)
    return line


def _blank(line):
    return "".join(c if c in "\r\n" else " " for c in line)


def _indent(line):
    width = 0
    for c in line:
        if c == " ":
            width += 1
        elif c == "\t":
            width += 4 - width % 4
        else:
            break
    return width


def mask_structure(text, version=VERSION):
    """The text with table delimiter rows, indented code blocks and TOML front
    matter blanked, and from markdown/2 math as well. Fenced code is left to the
    detector, which skips it."""
    math = _level(version) >= 2
    in_math = False
    lines = text.splitlines(keepends=True)
    out = []
    in_fence = False
    in_toml = bool(lines) and lines[0].rstrip("\r\n") == "+++"
    in_code = False
    list_active = False
    prev_blank = True
    for i, raw in enumerate(lines):
        body = raw.rstrip("\r\n")
        if in_toml:
            out.append(_blank(raw))
            if i > 0 and body == "+++":
                in_toml = False
            continue
        if _FENCE.match(body):
            in_fence = not in_fence
            out.append(raw)
            prev_blank = False
            continue
        if in_fence:
            out.append(raw)
            continue
        if math and (in_math or body.strip() == "$$"):
            if body.strip() == "$$":
                in_math = not in_math
            out.append(_blank(raw))
            prev_blank = False
            continue
        if not body.strip():
            out.append(raw)
            prev_blank = True
            continue
        indent = _indent(body)
        if indent >= 4 and (in_code or (prev_blank and not list_active)):
            in_code = True
            out.append(_blank(raw))
            prev_blank = False
            continue
        in_code = False
        if _LIST.match(body):
            list_active = True
        elif indent == 0:
            list_active = False
        if is_md_table_sep(body) and not is_md_hr(body):
            out.append(raw.replace("-", " ").replace(":", " "))
        elif math and "$" in body:
            out.append(_mask_math(raw))
        else:
            out.append(raw)
        prev_blank = False
    return "".join(out)


def _sentence_initial(line, start):
    """True when the word at `start` opens its line or follows a sentence end."""
    before = line[:start]
    if not before.strip() or _LEAD.fullmatch(before):
        return True
    tail = before.rstrip(" \"'“‘(")
    return bool(tail) and tail[-1] in _ENDERS


def _capitalised(word):
    return word[0].isupper()


def _name_words(line):
    """[(start, end)] of capitalised words that belong to a run of two or more
    capitalised words, leaving out a word that opens a sentence."""
    words = [(m.start(), m.end()) for m in _WORD.finditer(line)
             if _capitalised(m.group(0)) and not _sentence_initial(line, m.start())]
    keep = set()
    for a, b in zip(words, words[1:]):
        if not line[a[1]:b[0]].strip():
            keep.update((a, b))
    return sorted(keep)


def _initial_run(line, start):
    """Words of the capitalised run that opens at `start`, as (start, end) pairs."""
    run = []
    for m in _WORD.finditer(line, start):
        if not _capitalised(m.group(0)) or (run and line[run[-1][1]:m.start()].strip()):
            break
        run.append((m.start(), m.end()))
    return run


def known_names(text):
    """Capitalised runs that appear away from a sentence start on a prose line,
    as tuples of words. They are evidence of a name anywhere in the document."""
    names = set()
    for line in text.splitlines():
        if not _prose_line(line):
            continue
        run = []
        for w in _name_words(line) + [None]:
            if w is not None and run and not line[run[-1][1]:w[0]].strip():
                run.append(w)
                continue
            if len(run) >= 2:
                names.add(tuple(line[a:b] for a, b in run))
            run = [w] if w is not None else []
    return names


def _initial_name(line, start, end, known):
    """(start, end) of a known name that opens a sentence and covers the finding."""
    run = _initial_run(line, start)
    words = tuple(line[a:b] for a, b in run)
    for k in range(len(run), 1, -1):
        if words[:k] in known and run[k - 1][1] >= end:
            return run[0][0], run[k - 1][1]
    return None


def _prose_line(line):
    """A sentence-case line: not a heading, with a lowercase word of four or more
    letters, so a Title Case line is not taken for a run of names."""
    if _HEADING.match(line):
        return False
    return any(w[0].islower() and len(w) >= 4 for w in _WORD.findall(line))


def name_spans(text, result, version=VERSION, known=None):
    """Document offsets (start, end) of register-word findings inside a name.
    From markdown/2 a finding at a sentence start counts when its capitalised
    run is in `known` (default: the known names of `text`)."""
    if _level(version) < 2:
        known = set()
    elif known is None:
        known = known_names(text)
    lines = text.splitlines(keepends=True)
    offsets, acc = [], 0
    for ln in lines:
        offsets.append(acc)
        acc += len(ln)
    spans = []
    for f in result["medium"] + result["high"] + result["low"]:
        if f["category"] != "register-word" or not 1 <= f["line"] <= len(lines):
            continue
        line = lines[f["line"] - 1]
        if not _prose_line(line):
            continue
        base = offsets[f["line"] - 1]
        s, e = f["start"] - base, f["end"] - base
        inside = [w for w in _name_words(line) if w[0] < e and w[1] > s]
        covered = [(m.start(), m.end()) for m in _WORD.finditer(line[s:e])]
        if inside and len(inside) == len(covered) and inside[0][0] <= s and inside[-1][1] >= e:
            spans.append((base + inside[0][0], base + inside[-1][1]))
        elif known and _sentence_initial(line, s):
            found = _initial_name(line, s, e, known)
            if found:
                spans.append((base + found[0], base + found[1]))
    return spans


def mask_spans(text, spans):
    """Replace each span's letters with a placeholder of the same length and case."""
    chars = list(text)
    for s, e in spans:
        for k in range(s, e):
            if chars[k].isalpha():
                chars[k] = "Q" if chars[k].isupper() else "q"
    return "".join(chars)


def restore(result, original, masked):
    """Copy match and snippet back from the original text into each finding that
    touches a line the masks changed. Other findings are left as they are."""
    if original == masked:
        return result
    orig_lines = original.splitlines(keepends=True)
    mask_lines = masked.splitlines(keepends=True)
    for key in ("high", "medium", "low"):
        for f in result.get(key, ()):
            if original[f["start"]:f["end"]] != masked[f["start"]:f["end"]]:
                f["match"] = original[f["start"]:f["end"]]
            n = f["line"] - 1
            if 0 <= n < len(orig_lines) and orig_lines[n] != mask_lines[n]:
                f["snippet"] = orig_lines[n].strip()[:100]
    return result
