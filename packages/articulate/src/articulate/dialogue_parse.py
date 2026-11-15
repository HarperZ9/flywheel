"""Read spoken lines, with their speakers, out of script files.

Each reader returns a list of line records:

    {"speaker": "KEEL", "text": "...", "file": path, "line": 12, "node": id or None,
     "group": "act1" or None}

Formats:
  lwd     Low Water's LWD/1: `line: NAME: text`, or `line: text` under a node's
          `speaker: NAME`. A trailing `{when: ...}` gate moves from the text to
          the record's "gate" field.
  colon   one `NAME: text` per line, the generic plain form.
  play    a printed play: `NAME. text` with the speech running to the next
          blank line, or `NAME.` alone on a line with the speech below it.
          Bracketed and parenthesised stage directions are dropped.
"""
import os
import re

_GATE = re.compile(r"\s*\{[^{}]*\}\s*$")
_LWD_LINE = re.compile(r"^line:\s*(?:([A-Z][A-Z0-9 .'\-]{0,30}):\s+)?(.*)$")
_COLON = re.compile(r"^\s*([A-Z][A-Za-z0-9 .'\-]{0,30}):\s+(\S.*)$")
_PLAY_INLINE = re.compile(r"^([A-Z][A-Z .'\-]{1,30}[A-Z])\.\s+(?=\S)(.*)$")
_PLAY_DIRECTED = re.compile(r"^([A-Z][A-Z .'-]{1,30}[A-Z])[.]?[ ]+([\[(].*)$")
_PLAY_ALONE = re.compile(r"^([A-Z][A-Z .'\-]{1,30}[A-Z])\.\s*$")
_STAGE = re.compile(r"\[[^\]]*\]|\(_[^)]*_\)|\([^)]*\)")


def _strip_gate(text):
    return _split_gate(text)[0]


def _split_gate(text):
    """('the line', 'when: has(x), once') from 'the line {when: has(x), once}'."""
    gates = []
    while True:
        m = _GATE.search(text)
        if not m:
            return text.strip(), "; ".join(reversed(gates))
        gates.append(m.group(0).strip()[1:-1].strip())
        text = text[:m.start()]


def _group(path):
    """The act or folder a file belongs to, for per-act counts."""
    parent = os.path.basename(os.path.dirname(os.path.abspath(path)))
    return parent or None


def parse_lwd(text, path="<text>"):
    out, speaker, node = [], None, None
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line.startswith("@"):
            parts = line.split(None, 1)
            node = parts[1].strip() if len(parts) > 1 else None
            speaker = None
            continue
        if line.startswith("speaker:"):
            speaker = line.split(":", 1)[1].strip() or None
            continue
        m = _LWD_LINE.match(line)
        if not m:
            continue
        who = (m.group(1) or speaker or "").strip()
        body, gate = _split_gate(m.group(2))
        if who and body:
            out.append({"speaker": who, "text": body, "file": path, "line": no,
                        "node": node, "group": _group(path), "gate": gate or None})
    return out


def parse_colon(text, path="<text>"):
    out = []
    for no, raw in enumerate(text.splitlines(), 1):
        m = _COLON.match(raw)
        if m and not raw.lstrip().startswith(("#", "http")):
            body = _strip_gate(m.group(2))
            if body:
                out.append({"speaker": m.group(1).strip().upper(), "text": body, "file": path,
                            "line": no, "node": None, "group": _group(path)})
    return out


def _clean_speech(chunks):
    text = " ".join(c.strip() for c in chunks)
    text = re.sub(r"\s+", " ", _STAGE.sub(" ", text)).strip()
    return text


def parse_play(text, path="<text>", known=None):
    """Printed-play layout. `known`, when given, limits speakers to those names, so a
    shouted all-caps word inside a speech is not read as a new speaker."""
    out, who, start, buf = [], None, 0, []

    def flush():
        if who and buf:
            body = _clean_speech(buf)
            if re.search(r"[A-Za-z]", body):
                out.append({"speaker": who, "text": body, "file": path, "line": start,
                            "node": None, "group": _group(path)})

    for no, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            flush()
            who, buf = None, []
            continue
        m = _PLAY_DIRECTED.match(raw) or _PLAY_INLINE.match(raw) or _PLAY_ALONE.match(raw)
        name = m.group(1).strip() if m else None
        if name and (known is None or name in known) and len(name.split()) <= 3:
            flush()
            who, start = name, no
            buf = [m.group(2)] if m.lastindex and m.lastindex >= 2 else []
        elif who is not None:
            buf.append(raw)
    flush()
    return out


def detect(text, path=""):
    """Pick a reader from the file name, then from the text."""
    low = path.lower()
    if low.endswith(".lwd") or re.search(r"(?m)^line:\s", text):
        return "lwd"
    inline = len(re.findall(r"(?m)^[A-Z][A-Z .'\-]{1,30}[A-Z]\.(?:\s|$)", text))
    colon = sum(1 for row in text.splitlines() if _COLON.match(row))
    return "play" if inline > colon else "colon"


READERS = {"lwd": parse_lwd, "colon": parse_colon, "play": parse_play}


def parse(text, path="<text>", fmt=None):
    fmt = fmt or detect(text, path)
    if fmt not in READERS:
        raise ValueError(f"unknown dialogue format {fmt!r}; use one of {sorted(READERS)}")
    return READERS[fmt](text, path)
