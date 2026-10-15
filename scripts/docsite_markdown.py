"""docsite_markdown.py -- the Markdown subset the Flywheel docs use, to HTML.

Standard library only. Handles ATX headings (with ids for anchors), paragraphs,
fenced code, bullet and numbered lists (one level), tables, block quotes,
horizontal rules, inline code, bold, italics and links. Every piece of text is
HTML-escaped before markup is added, so a doc cannot inject a script. Links to
another .md file are rewritten to the matching .html page when the target is
part of the site, and left pointing at the repository otherwise.
"""
from __future__ import annotations

import html
import re

REPO_BLOB = "https://github.com/HarperZ9/flywheel/blob/main/"


def slug(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_]+", "-", s)


def _inline(text: str, link_map: dict, here: str) -> str:
    codes: list = []

    def keep_code(m):
        codes.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"
    text = re.sub(r"`([^`]+)`", keep_code, text)
    text = html.escape(text, quote=False)

    def link(m):
        label, target = m.group(1), html.unescape(m.group(2))
        href = _resolve(target, link_map, here)
        return f'<a href="{html.escape(href)}">{label}</a>'
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\s][^*]*)\*(?![\w*])", r"<em>\1</em>", text)
    return re.sub("\x00(\\d+)\x00", lambda m: codes[int(m.group(1))], text)


def _resolve(target: str, link_map: dict, here: str) -> str:
    if re.match(r"^[a-z]+:", target) or target.startswith("#"):
        return target
    path, _, anchor = target.partition("#")
    base = here.rsplit("/", 1)[0] + "/" if "/" in here else ""
    norm = _normalize(base + path)
    if norm in link_map:
        return link_map[norm] + (f"#{anchor}" if anchor else "")
    return REPO_BLOB + norm + (f"#{anchor}" if anchor else "")


def _normalize(path: str) -> str:
    parts: list = []
    for p in path.split("/"):
        if p in ("", "."):
            continue
        if p == "..":
            if parts:
                parts.pop()
            continue
        parts.append(p)
    return "/".join(parts)


def _table(rows: list, link_map, here) -> str:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    head, body = cells[0], cells[2:]
    out = ["<table><thead><tr>"] + [f"<th>{_inline(c, link_map, here)}</th>" for c in head]
    out.append("</tr></thead><tbody>")
    for r in body:
        out.append("<tr>" + "".join(f"<td>{_inline(c, link_map, here)}</td>" for c in r) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def convert(md: str, *, link_map: "dict | None" = None, here: str = "") -> "tuple[str, list]":
    """(html, headings) where headings is [(level, text, id)]."""
    link_map = link_map or {}
    lines = md.replace("\r\n", "\n").split("\n")
    out, heads, i = [], [], 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(lines[i + 1:j])) + "</code></pre>")
            i = j + 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level, text = len(m.group(1)), m.group(2).strip()
            anchor = slug(text)
            heads.append((level, text, anchor))
            out.append(f'<h{level} id="{anchor}">{_inline(text, link_map, here)}</h{level}>')
            i += 1
            continue
        if line.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            out.append(_table(lines[i:j], link_map, here))
            i = j
            continue
        if re.match(r"^\s*([-*]|\d+\.)\s+", line):
            ordered = bool(re.match(r"^\s*\d+\.", line))
            items, j = [], i
            while j < len(lines) and (re.match(r"^\s*([-*]|\d+\.)\s+", lines[j]) or
                                      (lines[j].startswith("  ") and lines[j].strip())):
                if re.match(r"^\s*([-*]|\d+\.)\s+", lines[j]):
                    items.append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[j]))
                else:
                    items[-1] += " " + lines[j].strip()
                j += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(t, link_map, here)}</li>" for t in items)
                       + f"</{tag}>")
            i = j
            continue
        if line.startswith(">"):
            j, quoted = i, []
            while j < len(lines) and lines[j].startswith(">"):
                quoted.append(lines[j][1:].strip())
                j += 1
            out.append("<blockquote><p>" + _inline(" ".join(quoted), link_map, here)
                       + "</p></blockquote>")
            i = j
            continue
        if re.match(r"^\s*(-{3,}|\*{3,})\s*$", line):
            out.append("<hr>")
            i += 1
            continue
        if not line.strip() or line.lstrip().startswith("<"):
            i += 1                     # raw HTML in docs (badges, pictures) is dropped
            continue
        para = [line.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(#{1,6}\s|```|>|\s*([-*]|\d+\.)\s+|\s*\|)", lines[i]):
            para.append(lines[i].strip())
            i += 1
        out.append("<p>" + _inline(" ".join(para), link_map, here) + "</p>")
    return "\n".join(out), heads
