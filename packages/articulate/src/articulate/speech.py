"""The spoken view of findings: a script to read aloud, and SSML for a voice.

CORE asks for every finding in more than one view. The text report and the
editor highlight are visual and textual; this module adds the auditory pair.
`script` turns findings into plain sentences with no symbols, line numbers said
as words a voice reads cleanly, and the passage itself quoted after a pause.
`ssml` gives the same script as SSML 1.1 for any speech engine, with each
passage in its own paragraph and the device's span emphasised, so the listener
hears the repeated opener of an anaphora or the onsets of an alliteration where
the eye would see a highlight.

Nothing here makes a sound or calls a service; a caller hands the script or the
SSML to whatever voice the reader uses. Standard library only.
"""
from __future__ import annotations

import re
from xml.sax.saxutils import escape

_SAY = {
    "tricolon": "a set of three",
    "asyndeton": "a series with the joining words left out",
    "polysyndeton": "a series with a joining word before every item",
    "anaphora": "repeated openings",
    "anadiplosis": "a clause that starts with the word the last one ended on",
    "epizeuxis": "a word said again at once",
    "isocolon": "clauses of matching length",
    "zeugma": "one verb doing two different jobs",
    "oxymoron": "opposite words side by side",
}


def line_of(text, offset):
    return text.count("\n", 0, max(0, offset)) + 1


def _items(findings, text):
    """(line, name, detail, passage) for check findings or device findings."""
    out = []
    for f in findings:
        if "device" in f:
            name = _SAY.get(f["device"], f["device"])
            out.append((line_of(text, f["start"]), name, f.get("detail", ""), f["snippet"]))
        else:
            label = f["label"].replace("/", " or ").replace("(", "").replace(")", "")
            out.append((f["line"], label, f.get("tier", "").lower(), f.get("match") or f["snippet"]))
    return sorted(out, key=lambda r: r[0])


def _clean(s):
    s = re.sub(r"\s*\|\s*", ", ", str(s).replace("_", " "))
    s = re.sub(r"[.,;:]+(?=,)", "", s)
    return " ".join(s.split()).rstrip(" .,;:")


def script(findings, text):
    """Plain sentences for a voice to read: one per finding."""
    rows = _items(findings, text)
    if not rows:
        return "No findings."
    lines = [f"{len(rows)} finding{'s' if len(rows) != 1 else ''}."]
    for line, name, detail, passage in rows:
        extra = f", {_clean(detail)}" if detail else ""
        lines.append(f"Line {line}: {_clean(name)}{extra}. The passage reads: {_clean(passage)}.")
    return "\n".join(lines)


def ssml(findings, text):
    """The script as SSML 1.1, with the quoted passage emphasised after a pause."""
    rows = _items(findings, text)
    parts = ['<speak version="1.1" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en">']
    if not rows:
        parts.append("<p>No findings.</p>")
    for line, name, detail, passage in rows:
        extra = f", {escape(_clean(detail))}" if detail else ""
        parts.append(f"<p>Line {line}: {escape(_clean(name))}{extra}."
                     f'<break time="400ms"/><emphasis level="moderate">'
                     f"{escape(_clean(passage))}</emphasis></p>")
    parts.append("</speak>")
    return "\n".join(parts)
