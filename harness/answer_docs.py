"""answer_docs.py -- take the answer out of the document it arrived in.

An answer rarely arrives as a bare JSON file. It arrives as the memo, the
filing, the paper, the discharge summary. The check still needs the values and
the sources, so the document has to carry them somewhere a reader and a parser
can both find.

The rule is the same in every format: a marked block holds the answer as JSON,
and nothing outside that block is read. Nothing here parses prose, and nothing
here infers a value from a sentence. A number lifted out of a paragraph by a
regular expression would be a guess wearing a checker's authority, which is the
failure the whole feature exists to prevent.

    .json   the file
    .md     a fenced block tagged `flywheel-answer`, or the first `json` fence
    .tex    a `flywheelanswer` environment, comment markers stripped
    .pdf    the attached stream a Flywheel PDF carries

A PDF from somewhere else is refused rather than mined. Reading values off a
rendered page means reconstructing a layout, and a wrong reconstruction reads
exactly like a right one.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .pdf_writer import read_attachment

FENCE = re.compile(r"^[ \t]*(?:```|~~~)[ \t]*([^\n`~]*)\n(.*?)^[ \t]*(?:```|~~~)[ \t]*$",
                   re.S | re.M)
ENVIRONMENT = re.compile(r"\\begin\{flywheelanswer\}(.*?)\\end\{flywheelanswer\}", re.S)
VERBATIM = re.compile(r"\\begin\{(?:verbatim|lstlisting)\}(.*?)\\end\{(?:verbatim|lstlisting)\}",
                      re.S)
MARKER = "flywheel-answer"
SUFFIXES = (".json", ".md", ".markdown", ".tex", ".latex", ".pdf")


class DocumentError(ValueError):
    """Raised when a document holds no answer this module will read."""


def _object(text: str):
    value = json.loads(text)
    if not isinstance(value, dict):
        raise DocumentError("an answer is an object of fields, not a "
                            f"{type(value).__name__}")
    return value


def from_markdown(text: str) -> dict:
    """The marked fence, else the first `json` fence that holds an object.

    A document may carry several code blocks and only one of them is the
    answer, so the explicit marker wins. Falling back to the first `json` fence
    keeps the common case short, and a document where that guess is wrong can
    say which block it means.
    """
    blocks = [(info.strip().lower(), body) for info, body in FENCE.findall(text)]
    for info, body in blocks:
        if MARKER in info:
            return _object(body)
    for info, body in blocks:
        if info.split(" ")[0] in ("json", "jsonc"):
            try:
                return _object(body)
            except (DocumentError, json.JSONDecodeError):
                # The fallback is a guess at which block was meant, and a block
                # that does not parse or is not an object is evidence against
                # this one. A marked block gets no such benefit: there the
                # author said which block it is, and a bad one is an error.
                continue
    raise DocumentError("no fenced block tagged flywheel-answer, and no json "
                        "block holding an object of fields")


def from_latex(text: str) -> dict:
    """The `flywheelanswer` environment, with LaTeX's own wrappers removed.

    An author who has to keep the block out of the typeset output comments it
    line by line, and an author who wants it printed wraps it in verbatim.
    Both should reach the same parser.
    """
    found = ENVIRONMENT.search(text)
    if not found:
        raise DocumentError("no flywheelanswer environment")
    body = found.group(1)
    inner = VERBATIM.search(body)
    if inner:
        body = inner.group(1)
    stripped = "\n".join(re.sub(r"^[ \t]*%+[ \t]?", "", line)
                         for line in body.splitlines())
    return _object(stripped)


def from_pdf(data: bytes) -> dict:
    answer = read_attachment(data)
    if answer is None:
        raise DocumentError("this PDF carries no attached answer, and values "
                            "are not read off a rendered page")
    return answer


def read_answer(path) -> dict:
    """The answer in a file, whichever of the four formats it is in."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return from_pdf(path.read_bytes())
    text = path.read_text(encoding="utf-8")
    if suffix in (".md", ".markdown"):
        return from_markdown(text)
    if suffix in (".tex", ".latex"):
        return from_latex(text)
    if suffix == ".json":
        return _object(text)
    raise DocumentError(f"no reader for {suffix or 'a file with no suffix'}; "
                        f"known: {', '.join(SUFFIXES)}")
