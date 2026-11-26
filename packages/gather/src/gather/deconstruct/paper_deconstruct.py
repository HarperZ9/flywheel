"""Deterministic whitepaper and research deconstructor (paper-deconstruction/1).

Supports PDF (optional pypdf/pdftotext + pure-Python stream fallback), arXiv/HTML,
and Markdown whitepapers using Python stdlib only in CI.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import zlib
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

PAPER_SCHEMA = "paper-deconstruction/1"

_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
_ARXIV_RE = re.compile(r"\b(?:arXiv:)?(\d{4}\.\d{4,5}(?:v\d+)?)\b", re.I)
_URL_RE = re.compile(r"https?://[^\s<>\"')]+", re.I)
_CITE_RE = re.compile(r"\[(\d{1,3}(?:\s*[-,]\s*\d{1,3})*)\]")
_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2})\b")
_DISPLAY_EQ_RE = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\begin\{equation\*?\}(.+?)\\end\{equation\*?\}", re.S)
_INLINE_EQ_RE = re.compile(r"(?<!\$)\$(?!\$)([^$\n]{3,160})(?<!\$)\$(?!\$)")
_FIG_RE = re.compile(r"^\s*(?:Figure|Fig\.)\s*\d+[:.]\s*(.+)$", re.M | re.I)
_TABLE_CAP_RE = re.compile(r"^\s*Table\s*\d+[:.]\s*(.+)$", re.M | re.I)
_METRIC_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(%|dB|dBFS|LUFS|ms|us|ns|Hz|kHz|FPS|GB|MB|x|ULP)\b"
    r"|\b(recall|precision|f1|accuracy|pass_rate|hit@5|sdr|flip)\s*(?:=|of|at|:)\s*(\d+(?:\.\d+)?%?)",
    re.I,
)

_FORMULA_SIGNATURES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("COL-001", re.compile(r"(?i)\bsrgb(?:_to_linear)?\b|0\.04045|12\.92")),
    ("COL-003", re.compile(r"(?i)\bcielab\b|\bxyz_to_lab\b|24389")),
    ("COL-005", re.compile(r"(?i)\boklab\b|0\.41222147")),
    ("COL-009", re.compile(r"(?i)\bciede2000\b|\bdelta\s*e\s*2000\b")),
    ("COL-030", re.compile(r"(?i)\bwcag\b.*\bcontrast\b|\(l1\s*\+\s*0\.05\)")),
    ("OPT-001", re.compile(r"(?i)\bsnell(?:'s)?\s+law\b|n_?1\s*\\?sin")),
    ("OPT-002", re.compile(r"(?i)\bfresnel\b.*(?:dielectric|reflectance)")),
    ("OPT-004", re.compile(r"(?i)\bschlick\b.*fresnel|f_?0\s*\+\s*\(1\s*-\s*f_?0\)")),
    ("OPT-008", re.compile(r"(?i)\bairy\s+(?:disc|disk|radius)\b|1\.21966")),
    ("OPT-014", re.compile(r"(?i)\bsellmeier\b")),
    ("OPT-033", re.compile(r"(?i)\bbeer[- ]lambert\b|e\^\{?-\\?alpha")),
    ("SIG-011", re.compile(r"(?i)6\.02\s*\*?\s*[nb]\s*\+\s*1\.76|quantis?ation\s+snr")),
    ("SIG-013", re.compile(r"(?i)\bshannon\s+entropy\b|-\\?sum.*\\?log_?2")),
    ("SIG-021", re.compile(r"(?i)\bfriis\b.*(?:noise|cascade)")),
    ("PHY-039", re.compile(r"(?i)\blandauer\b|k_?b\s*t\s*\\?ln\s*2")),
    ("HASH-FNV", re.compile(r"1469598103934665603|\bfnv-?1a\b", re.I)),
)


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str = ""
        self.headings: list[dict[str, Any]] = []
        self.figcaptions: list[str] = []
        self.table_count: int = 0
        self._buf: list[str] = []
        self._tag_stack: list[str] = []
        self._cur_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        self._tag_stack.append(t)
        if t == "table":
            self.table_count += 1
        if t in ("title", "h1", "h2", "h3", "figcaption"):
            self._cur_text = []

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if self._tag_stack and self._tag_stack[-1] == t:
            self._tag_stack.pop()
        text = " ".join("".join(self._cur_text).split())
        if t == "title" and text and not self.title:
            self.title = text
        elif t in ("h1", "h2", "h3") and text:
            self.headings.append({"level": int(t[1]), "heading": text})
            self._buf.append(f"\n{'#' * int(t[1])} {text}\n")
        elif t == "figcaption" and text:
            self.figcaptions.append(text)
            self._buf.append(f"\nFigure 0: {text}\n")
        elif t in ("p", "div", "li", "br", "tr"):
            self._buf.append("\n")

    def handle_data(self, data: str) -> None:
        if any(t in ("script", "style") for t in self._tag_stack):
            return
        if any(t in ("title", "h1", "h2", "h3", "figcaption") for t in self._tag_stack):
            self._cur_text.append(data)
        self._buf.append(data)


def _extract_pdf_fallback(raw: bytes) -> str:
    """Pure-Python PDF text-stream fallback for uncompressed and FlateDecode streams."""
    chunks: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.S):
        payload = match.group(1)
        try:
            payload = zlib.decompress(payload)
        except zlib.error:
            pass
        for lit in re.findall(rb"\(([^()\\]*(?:\\.[^()\\]*)*)\)\s*Tj", payload):
            chunks.append(lit.decode("latin-1", errors="replace"))
        for arr in re.findall(rb"\[(.*?)\]\s*TJ", payload, re.S):
            parts = re.findall(rb"\(([^()\\]*(?:\\.[^()\\]*)*)\)", arr)
            if parts:
                chunks.append("".join(p.decode("latin-1", errors="replace") for p in parts))
    if chunks:
        return "\n".join(chunks)
    printable = re.findall(rb"[\x20-\x7e]{12,}", raw)
    return "\n".join(p.decode("ascii", errors="ignore") for p in printable)


def _read_pdf_text(path: Path, raw: bytes) -> tuple[str, str]:
    try:
        import pypdf  # type: ignore[import-not-found]
        reader = pypdf.PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages), "pypdf"
    except Exception:
        pass
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        proc = subprocess.run([pdftotext, str(path), "-"], capture_output=True, text=True, timeout=30, check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout, "pdftotext"
    return _extract_pdf_fallback(raw), "stdlib_pdf_stream"


def _extract_sections_and_tables(text: str, extra_tables: int = 0) -> tuple[list[dict[str, Any]], int]:
    sections: list[dict[str, Any]] = []
    pipe_tables = 0
    in_table = False
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        m = re.match(r"^(#{1,4})\s+(.+)$", line.strip())
        if m:
            sections.append({"level": len(m.group(1)), "heading": m.group(2).strip(), "line": idx + 1})
        if "|" in line and re.match(r"^\s*\|?[\s:-]+\|[\s|:-]+$", line):
            if not in_table:
                pipe_tables += 1
                in_table = True
        elif not line.strip():
            in_table = False
    cap_tables = len(_TABLE_CAP_RE.findall(text))
    return sections, max(pipe_tables, cap_tables) + extra_tables


def _extract_equations_and_metrics(text: str) -> tuple[list[str], list[dict[str, str]]]:
    eqs: list[str] = []
    for m in _DISPLAY_EQ_RE.finditer(text):
        expr = next((g for g in m.groups() if g is not None), "").strip()
        if expr and expr not in eqs:
            eqs.append(expr)
    for m in _INLINE_EQ_RE.finditer(text):
        expr = m.group(1).strip()
        if expr and any(ch in expr for ch in ("=", "\\", "^", "_", "/")) and expr not in eqs:
            eqs.append(expr)
    metrics: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in _METRIC_RE.finditer(text):
        if m.group(1) and m.group(2):
            val, unit = m.group(1), m.group(2)
            key = f"{val}{unit}".lower()
            if key not in seen:
                seen.add(key)
                metrics.append({"value": val, "unit": unit, "raw": m.group(0)})
        elif m.group(3) and m.group(4):
            key = f"{m.group(3)}={m.group(4)}".lower()
            if key not in seen:
                seen.add(key)
                metrics.append({"metric": m.group(3).lower(), "value": m.group(4), "raw": m.group(0)})
    return eqs, metrics


def _extract_authors_and_title(text: str, html_title: str) -> tuple[str, list[str], str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = html_title
    if not title:
        for ln in lines[:10]:
            if ln.startswith("# "):
                title = ln[2:].strip()
                break
        if not title and lines:
            title = lines[0].lstrip("#").strip()[:200]
    authors: list[str] = []
    for ln in lines[:20]:
        m = re.match(r"^(?:Authors?|By)\s*:\s*(.+)$", ln, re.I)
        if m:
            authors = [a.strip() for a in re.split(r",|;| and ", m.group(1)) if a.strip()]
            break
    date_m = _DATE_RE.search(text[:2000])
    return title, authors, date_m.group(1) if date_m else ""


def deconstruct_paper(path: Path) -> dict[str, Any]:
    """Deterministically parse a PDF, HTML, or Markdown whitepaper into paper-deconstruction/1."""
    raw = path.read_bytes()
    source_sha = "sha256:" + hashlib.sha256(raw).hexdigest()
    suffix = path.suffix.lower()
    html_title = ""
    extra_tables = 0
    extra_figs: list[str] = []

    if suffix == ".pdf":
        text, backend = _read_pdf_text(path, raw)
        kind = "pdf"
    elif suffix in (".html", ".htm"):
        parser = _HtmlTextExtractor()
        parser.feed(raw.decode("utf-8", errors="replace"))
        text = "".join(parser._buf)
        html_title, extra_tables, extra_figs = parser.title, parser.table_count, parser.figcaptions
        backend, kind = "stdlib_html", "html"
    else:
        text, backend, kind = raw.decode("utf-8", errors="replace"), "stdlib_markdown", "markdown"

    title, authors, date = _extract_authors_and_title(text, html_title)
    sections, tables = _extract_sections_and_tables(text, extra_tables)
    equations, metrics = _extract_equations_and_metrics(text)
    figs = sorted(set(_FIG_RE.findall(text) + extra_figs))
    dois = sorted({m.group(0).rstrip(".,;)") for m in _DOI_RE.finditer(text)})
    arxiv_ids = sorted({m.group(1) for m in _ARXIV_RE.finditer(text)})
    urls = sorted({m.group(0).rstrip(".,;)") for m in _URL_RE.finditer(text)})
    cites = sorted({m.group(1) for m in _CITE_RE.finditer(text)})
    formulas = [fid for fid, rx in _FORMULA_SIGNATURES if rx.search(text)]

    return {
        "schema": PAPER_SCHEMA,
        "source_path": path.name,
        "source_kind": kind,
        "extraction_backend": backend,
        "source_sha256": source_sha,
        "title": title,
        "authors": authors,
        "date": date,
        "sections": sections,
        "equations_latex": equations,
        "tables_detected": tables,
        "figure_captions": figs,
        "citations_and_dois": {"dois": dois, "arxiv_ids": arxiv_ids, "urls": urls, "bracket_citations": cites},
        "claimed_metrics": metrics,
        "formula_matches": formulas,
        "char_count": len(text),
    }
