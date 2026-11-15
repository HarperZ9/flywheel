"""Split a file into entries for the negation-load check.

An entry is the unit a reader takes in at once. Each reader returns records:

    {"text": "...", "line": 12, "kind": "paragraph", "label": "## Install",
     "dialogue": False}

Readers:
  markdown  paragraphs and list items, with the nearest heading as the label.
            Fenced code, tables, front matter and HTML comments are skipped.
            Short list items that sit together join into one list entry.
  html      block elements (p, li, headings, cells, captions). Script, style,
            code and svg are skipped.
  lwd       Low Water script: narration lines in one block join into one
            entry; each `line:` and `opt:` is a dialogue entry.
  json      prose string values; a `lines` list joins into one entry, which
            covers explainer film scripts.
  js        string literals that read as prose, for extension UI strings.
Standard library only.
"""
from __future__ import annotations

import json
import os
import re
from html.parser import HTMLParser

MD_EXT = (".md", ".markdown", ".txt", ".rst", ".fountain")
HTML_EXT = (".html", ".htm")
JS_EXT = (".js", ".mjs", ".ts", ".jsx", ".tsx")
EXTENSIONS = MD_EXT + HTML_EXT + JS_EXT + (".lwd", ".json")

_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_EMPH = re.compile(r"(\*\*|__|\*|`)")
_SPEAKER = re.compile(r"^([A-Z][A-Z0-9 .'\-]{1,30}):\s+(\S.*)$")
_NARRATORS = {"NARRATOR", "NARRATION", "VO", "V.O.", "HOST", "GUIDE"}


def _clean_md(text):
    return _EMPH.sub("", _LINK.sub(r"\1", text)).strip()


def _rec(text, line, kind, label="", dialogue=False):
    return {"text": text, "line": line, "kind": kind, "label": label,
            "dialogue": dialogue}


def _speech(text):
    """(speaker, is_character_speech) for a `NAME: text` line."""
    m = _SPEAKER.match(text)
    if not m:
        return None, False
    who = m.group(1).strip()
    return who, who.upper() not in _NARRATORS


def _group_short(items, min_words):
    """Join runs of short list items into one list entry."""
    out, run = [], []
    for it in items + [None]:
        short = it is not None and it["kind"] == "item" and len(it["text"].split()) < min_words
        if short:
            run.append(it)
            continue
        if run:
            out.append(_rec("; ".join(r["text"] for r in run), run[0]["line"], "list",
                            run[0]["label"]))
            run = []
        if it is not None:
            out.append(it)
    return out


def markdown(text, min_words=8):
    lines = text.splitlines()
    out, buf, start, kind, label = [], [], 0, "paragraph", ""
    fence = comment = False
    i = 0
    if lines and lines[0].strip() == "---":
        while i + 1 < len(lines) and lines[i + 1].strip() != "---":
            i += 1
        i += 2

    def flush():
        if buf:
            body = _clean_md(" ".join(buf))
            who, speech = _speech(body)
            out.append(_rec(body, start, "dialogue" if who else kind,
                            label, dialogue=speech))
            buf.clear()

    for no in range(i, len(lines)):
        raw = lines[no]
        s = raw.strip()
        if s.startswith(("```", "~~~")):
            flush()
            fence = not fence
            continue
        if fence:
            continue
        if "<!--" in s:
            comment = "-->" not in s
            flush()
            continue
        if comment:
            comment = "-->" not in s
            continue
        h = _HEADING.match(raw)
        if not s or s.startswith("|") or h:
            flush()
            if h:
                label = h.group(2).strip()
            continue
        if _LIST.match(raw):
            flush()
            buf.append(_LIST.sub("", raw).strip())
            start, kind = no + 1, "item"
            continue
        if not buf:
            start, kind = no + 1, "paragraph"
        buf.append(s.lstrip("> ").strip())
    flush()
    return _group_short(out, min_words)


class _Blocks(HTMLParser):
    BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "figcaption",
             "dd", "dt", "td", "th", "caption", "summary", "label", "button", "option",
             "div", "section", "article", "header", "footer", "aside", "main", "title"}
    SKIP = {"script", "style", "code", "pre", "svg", "noscript", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.buf, self.line, self.skip, self.label = [], [], 0, 0, ""
        self.tags = []

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        self.buf = []
        if not text:
            return
        tag = self.tags[-1] if self.tags else "div"
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.label = text
            return
        self.out.append(_rec(text, self.line, tag, self.label))

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK and not self.skip:
            self._flush()
            self.tags.append(tag)
            self.line = self.getpos()[0]
        elif tag == "br":
            self.buf.append(" ")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK and not self.skip:
            self._flush()
            if tag in self.tags:
                while self.tags and self.tags.pop() != tag:
                    pass

    def handle_data(self, data):
        if not self.skip:
            if not "".join(self.buf).strip():
                self.line = self.getpos()[0]
            self.buf.append(data)


def html(text, min_words=8):
    p = _Blocks()
    p.feed(text)
    p.close()
    p._flush()
    return p.out


_GATE = re.compile(r"\s*\{[^{}]*\}\s*$")
_OPT = re.compile(r'^"?(.*?)"?\s*->.*$')
_NARRATION_KEYS = ("nar", "voice", "about", "desc", "text", "stage")


def lwd(text, min_words=8):
    out, block, nar, nar_line = [], "", [], 0

    def flush():
        if nar:
            out.append(_rec(" ".join(nar), nar_line, "narration", block))
            nar.clear()

    for no, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if s.startswith("@"):
            flush()
            block = s
            continue
        key, _, val = s.partition(":")
        val = _GATE.sub("", val).strip()
        if key in _NARRATION_KEYS and val:
            if key == "voice" and ":" in val:
                val = val.split(":", 1)[1].strip()
            if not nar:
                nar_line = no
            nar.append(val)
        elif key == "line" and val:
            who, _speech_ = _speech(val)
            out.append(_rec(val.split(":", 1)[1].strip() if who else val, no,
                            "dialogue", block, dialogue=True))
        elif key == "opt" and val:
            out.append(_rec(_OPT.sub(r"\1", val).strip('"'), no, "choice", block,
                            dialogue=True))
    flush()
    return out


_SKIP_KEYS = re.compile(r"(?i)(^|_)(id|ids|key|path|file|url|href|src|sha\d*|hash|"
                        r"seed|schema|slug|voice|color|font|class|type)$")


def _prose(s):
    return len(s.split()) >= 4 and re.search(r"[A-Za-z]{2,} [A-Za-z]{2,}", s) \
        and not re.search(r"[{};=<>]|\b(?:function|return|const|var)\b|^\W", s)


def json_entries(text, min_words=8):
    try:
        data = json.loads(text)
    except ValueError:
        return []
    out = []

    def walk(node, path):
        if isinstance(node, dict):
            if isinstance(node.get("lines"), list) and all(isinstance(x, str) for x in node["lines"]):
                out.append(_rec(" ".join(node["lines"]), 0, "segment", path))
            for k, v in node.items():
                if k != "lines" and not _SKIP_KEYS.search(str(k)):
                    walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str) and _prose(node):
            out.append(_rec(node.strip(), 0, "string", path))
    walk(data, "")
    return out


_JS_STR = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"|`((?:[^`\\]|\\.)*)`")


def js(text, min_words=8):
    out = []
    for m in _JS_STR.finditer(text):
        raw = next(g for g in m.groups() if g is not None)
        s = re.sub(r"\$\{[^}]*\}", "X", raw)
        s = re.sub(r"<[^>]+>", " ", s)
        s = re.sub(r"\\[nt]", " ", s).replace("\\", "")
        s = re.sub(r"\s+", " ", s).strip()
        if _prose(s):
            out.append(_rec(s, text.count("\n", 0, m.start()) + 1, "string"))
    return out


def entries(text, path="", fmt=None, min_words=8):
    """Entries for one file; the format comes from `fmt` or the extension."""
    ext = fmt or os.path.splitext(path)[1].lower()
    if ext in HTML_EXT or ext == "html":
        return html(text, min_words)
    if ext in (".lwd", "lwd"):
        return lwd(text, min_words)
    if ext in (".json", "json"):
        return json_entries(text, min_words)
    if ext in JS_EXT or ext == "js":
        return js(text, min_words)
    return markdown(text, min_words)
