"""report_docs.py -- the validation report as the document that has to carry it.

The same report goes to three readers. A person at a terminal wants the worst
line first. A pull request wants a table. A filing wants a page that can be
printed and attached to the thing it vouches for.

Every format orders the fields worst first, and every format carries the
release decision next to the verdict. A reader who stops after one line should
stop on the field that decided the run, and a reader who stops after two should
know whether the answer may be sent.

No format carries the authoritative value. That property is enforced upstream,
in the rows themselves, and these renderers only ever read what a row says.
"""
from __future__ import annotations

import json
from pathlib import Path

from .pdf_writer import pdf_bytes
from .verdict import Verdict

TITLE = "Flywheel output validation"
FORMATS = (".txt", ".text", ".md", ".markdown", ".tex", ".latex", ".pdf", ".json")
_RANK = {Verdict.FAIL.value: 0, Verdict.UNVERIFIABLE.value: 1, Verdict.PASS.value: 2}


def worst_first(report: dict) -> list[dict]:
    return sorted(report["fields"], key=lambda r: _RANK[r["verdict"]])


def headline(report: dict) -> tuple[str, str]:
    """The two lines every format opens with: the verdict, then the release."""
    return (f"{report['verdict']}  {report['passed']} of {report['checked']} "
            f"fields confirmed",
            report["release"] + (f"  blocked by: {', '.join(report['blocking'])}"
                                 if report["blocking"] else ""))


def proof_lines(report: dict) -> list[str]:
    """The kernel's reading of the same answer, when one was taken.

    Kept beside the field rows rather than in a section of its own. A reader
    who sees PASS on every field and stops has still seen whether a second and
    independent check agreed, which is the only place that disagreement can
    show up.
    """
    proof = report.get("proof")
    if not proof:
        return []
    out = [f"proof: {proof['verdict']} ({proof.get('checker') or 'no checker'}): "
           f"{proof['reason']}"]
    if proof.get("axioms"):
        out.append(f"rests on: {', '.join(proof['axioms'])}")
    return out


def as_text(report: dict) -> str:
    """The report as a person reads it.

    Ordered worst first. A reader who stops after one line should have stopped
    on the field that decides the run, not on whichever one came first in the
    contract.
    """
    verdict, release = headline(report)
    lines = [verdict, release]
    for row in worst_first(report):
        lines.append(f"  {row['verdict']:<13} {row['field']}: {row['reason']}")
    for item in report.get("next", {}).get("fields", []):
        lines.append(f"  next: {item['field']}: {item['do']}")
    lines += [f"  {line}" for line in proof_lines(report)]
    return "\n".join(lines)


def as_markdown(report: dict) -> str:
    verdict, release = headline(report)
    out = [f"# {TITLE}", "", f"**{verdict}**", "", release, "",
           "| Verdict | Field | Criticality | Authority | Reason |",
           "| --- | --- | --- | --- | --- |"]
    for row in worst_first(report):
        reason = row["reason"].replace("|", "\\|")
        out.append(f"| `{row['verdict']}` | `{row['field']}` | "
                   f"{row.get('criticality', '')} | {row['authority']} | {reason} |")
    following = report.get("next", {}).get("fields", [])
    if following:
        out += ["", "## Next", ""]
        out += [f"- `{item['field']}`: {item['do']}" for item in following]
    proof = proof_lines(report)
    if proof:
        out += ["", "## Proof", ""] + [f"- {line}" for line in proof]
    return "\n".join(out) + "\n"


def tex_escape(text: str) -> str:
    """LaTeX's ten reserved characters, and the two that need a command.

    A field called `taxable_income` typesets as subscripted nonsense without
    this, and a report that misnames the field it is about is worse than no
    report.
    """
    for old, new in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                     ("$", r"\$"), ("#", r"\#"), ("_", r"\_"), ("{", r"\{"),
                     ("}", r"\}"), ("~", r"\textasciitilde{}"),
                     ("^", r"\textasciicircum{}")):
        text = text.replace(old, new)
    return text


def as_latex(report: dict) -> str:
    """A fragment, not a document.

    An input goes inside whatever preamble the filing already has, and a
    standalone file that fought the surrounding document would be the more
    annoying default.
    """
    verdict, release = headline(report)
    out = [f"\\section*{{{tex_escape(TITLE)}}}",
           f"\\textbf{{{tex_escape(verdict)}}}\\\\",
           f"{tex_escape(release)}", "", "\\begin{itemize}"]
    for row in worst_first(report):
        out.append(f"  \\item \\texttt{{{tex_escape(row['verdict'])}}} "
                   f"\\texttt{{{tex_escape(row['field'])}}} "
                   f"({tex_escape(row.get('criticality', ''))}, "
                   f"{tex_escape(row['authority'])}): "
                   f"{tex_escape(row['reason'])}")
    out.append("\\end{itemize}")
    following = report.get("next", {}).get("fields", [])
    if following:
        out += ["", "\\subsection*{Next}", "\\begin{itemize}"]
        out += [f"  \\item \\texttt{{{tex_escape(item['field'])}}}: "
                f"{tex_escape(item['do'])}" for item in following]
        out.append("\\end{itemize}")
    proof = proof_lines(report)
    if proof:
        out += ["", "\\subsection*{Proof}", "\\begin{itemize}"]
        out += [f"  \\item {tex_escape(line)}" for line in proof]
        out.append("\\end{itemize}")
    return "\n".join(out) + "\n"


def render(report: dict, suffix: str, *, answer: dict | None = None):
    """The report in one format, as text or as bytes for the PDF."""
    suffix = suffix.lower()
    if suffix in (".md", ".markdown"):
        return as_markdown(report)
    if suffix in (".tex", ".latex"):
        return as_latex(report)
    if suffix == ".json":
        return json.dumps(report, indent=2) + "\n"
    if suffix == ".pdf":
        return pdf_bytes(as_text(report), title=TITLE, attachment=answer)
    if suffix in (".txt", ".text", ""):
        return as_text(report) + "\n"
    raise ValueError(f"no report format for {suffix}; known: {', '.join(FORMATS)}")


def write_report(report: dict, path, *, answer: dict | None = None) -> str:
    """Write the report in the format the path asks for. Returns the suffix."""
    path = Path(path)
    body = render(report, path.suffix, answer=answer)
    if isinstance(body, bytes):
        path.write_bytes(body)
    else:
        path.write_text(body, encoding="utf-8")
    return path.suffix.lower()
