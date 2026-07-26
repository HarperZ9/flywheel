"""render.py -- one verdict, four scientific output formats.

A measurement is only useful to a discipline if it can leave the tool it was made
in. This renders an OracleResult into plaintext, Markdown, and LaTeX, and hands
off to `lean_export` for the fourth format, which is not a rendering at all but an
independent re-check (see below).

THE ONE DISCIPLINE THESE RENDERERS OWE. A formatter must never add a claim the
result did not carry, and must never drop a qualification the result did carry.
The verdict, the objective, the denominator-shaped coverage, and every
`does_not_prove` entry travel into every format. In particular
`NOT_PROVES_OPTIMALITY` is not allowed to fall off in the LaTeX a paper would
paste, because that is the exact surface where "verified a drawing with 5
crossings" becomes "found the crossing number". These renderers carry it; the
claim-language gate catches it if a human strips it later.

Plaintext, Markdown, and LaTeX are FORMATTERS: they re-present what the checker
said. Lean is different in kind. A Lean export is a self-contained proof script
that RE-DERIVES the certificate's property in a language neither the operator nor
the model authored, checkable by the Lean toolchain. It is the strongest held-out
scorer in the system, and it lives in `lean_export.py`.
"""
from __future__ import annotations

import json

FORMATS = ("text", "markdown", "latex", "lean")


def _verdict(result) -> str:
    v = result.verdict() if callable(getattr(result, "verdict", None)) else \
        getattr(result, "verdict", "")
    return str(v)


def _enum(x) -> str:
    return getattr(x, "value", str(x))


def _fields(result) -> dict:
    """The renderable fields of an OracleResult, normalised to plain data."""
    return {
        "verdict": _verdict(result),
        "family": getattr(result, "cmd", ""),
        "objective": getattr(result, "objective", None),
        "attribution": _enum(getattr(result, "attribution", "")),
        "execution": _enum(getattr(result, "execution", "")),
        "excerpt": getattr(result, "stdout_excerpt", "") or "",
        "output_hash": getattr(result, "output_hash", ""),
        "coverage": getattr(result, "coverage", {}) or {},
        "does_not_prove": list(getattr(result, "does_not_prove", []) or []),
        "unverifiable_reason": getattr(result, "unverifiable_reason", "") or "",
    }


# --- plaintext ---------------------------------------------------------------

def to_text(result) -> str:
    f = _fields(result)
    lines = [
        f"verdict     : {f['verdict']}",
        f"family      : {f['family']}",
        f"attribution : {f['attribution']}",
    ]
    if f["objective"] is not None:
        lines.append(f"objective   : {f['objective']}")
    if f["unverifiable_reason"]:
        lines.append(f"undecided/unverifiable reason: {f['unverifiable_reason']}")
    lines.append(f"finding     : {f['excerpt']}")
    cov = f["coverage"]
    if cov:
        lines.append("coverage    : " + ", ".join(f"{k}={v}" for k, v in cov.items()))
    lines.append("does not prove:")
    for d in f["does_not_prove"]:
        lines.append(f"  - {d}")
    lines.append(f"output hash : {f['output_hash']}")
    return "\n".join(lines) + "\n"


# --- markdown ----------------------------------------------------------------

def to_markdown(result) -> str:
    f = _fields(result)
    out = [f"## Verdict: {f['verdict']}", "",
           "| field | value |", "|---|---|",
           f"| family | `{f['family']}` |",
           f"| attribution | {f['attribution']} |"]
    if f["objective"] is not None:
        out.append(f"| objective | {f['objective']} |")
    out.append(f"| output hash | `{f['output_hash']}` |")
    out += ["", f"**Finding.** {f['excerpt']}", ""]
    if f["unverifiable_reason"]:
        out += [f"**Reason.** {f['unverifiable_reason']}", ""]
    if f["coverage"]:
        out += ["**Coverage.**", ""]
        for k, v in f["coverage"].items():
            out.append(f"- {k}: `{v}`")
        out.append("")
    out.append("**Does not prove.**")
    out.append("")
    for d in f["does_not_prove"]:
        out.append(f"- {d}")
    return "\n".join(out) + "\n"


# --- latex -------------------------------------------------------------------

_LX = {"_": r"\_", "%": r"\%", "&": r"\&", "#": r"\#", "$": r"\$",
       "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
       "^": r"\textasciicircum{}"}


def _tex(s: str) -> str:
    # Backslash first, so the escapes we insert are not re-escaped.
    s = str(s).replace("\\", r"\textbackslash{}")
    for a, b in _LX.items():
        s = s.replace(a, b)
    return s


def to_latex(result) -> str:
    """A self-contained fragment a paper can \\input. No preamble, no claim the
    result did not make, and does_not_prove rendered as a visible list so an
    optimality caveat cannot silently drop between the tool and the page."""
    f = _fields(result)
    rows = [f"family & \\texttt{{{_tex(f['family'])}}} \\\\",
            f"verdict & {_tex(f['verdict'])} \\\\",
            f"attribution & {_tex(f['attribution'])} \\\\"]
    if f["objective"] is not None:
        rows.append(f"objective & {_tex(f['objective'])} \\\\")
    rows.append(f"output hash & \\texttt{{{_tex(f['output_hash'])}}} \\\\")
    dnp = "\n".join(f"  \\item {_tex(d)}" for d in f["does_not_prove"])
    return (
        "% flywheel verified-measurement fragment. No preamble; \\input into a paper.\n"
        "\\begin{center}\n\\begin{tabular}{ll}\n\\hline\n"
        + "\n".join(rows)
        + "\n\\hline\n\\end{tabular}\n\\end{center}\n\n"
        f"\\textbf{{Finding.}} {_tex(f['excerpt'])}\n\n"
        "\\textbf{Does not prove.}\n\\begin{itemize}\n"
        + dnp + "\n\\end{itemize}\n")


def render(result, fmt: str, *, cert: "dict | None" = None) -> str:
    """Render `result` in `fmt`. Lean needs the certificate, because it re-derives
    the property from the data rather than restating the verdict."""
    if fmt == "text":
        return to_text(result)
    if fmt == "markdown":
        return to_markdown(result)
    if fmt == "latex":
        return to_latex(result)
    if fmt == "lean":
        from .lean_export import to_lean
        if cert is None:
            raise ValueError("the Lean export re-derives the property from the "
                             "certificate, so `cert` is required for fmt='lean'")
        return to_lean(result, cert)
    raise ValueError(f"unknown format {fmt!r}; choose one of {FORMATS}")
