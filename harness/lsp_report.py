"""lsp_report.py -- turn one LSP run's report into something a person reads.

Split from the command itself so that what the command decides and what it
prints stay separable. The `--json` shape is the report dict these functions are
handed, so a change here is a change to the reading and not to the record.

The column layout is deliberate. A person scanning a terminal reads down the
left edge, and the two facts that decide whether an answer means anything, the
version and the encoding, sit in that column rather than inside a sentence.
"""
from __future__ import annotations

import json

__all__ = ["record_lines", "render_ask", "render_diagnostics", "render_verify"]


def render_ask(report: dict) -> str:
    lines = [f"method           {report['method']}",
             f"server           {report['server']['name'] or 'unnamed'}",
             f"encoding         {report['encoding']}",
             f"version          {report['version']}",
             f"current          {'yes' if report['current'] else 'no'}"]
    lines += record_lines(report)
    body = json.dumps(report["result"], indent=2) if report["result"] else \
        "the server had nothing to say about that position"
    return "\n".join(lines + ["", body])


def render_diagnostics(report: dict) -> str:
    """A published set, or the fact that nothing was published.

    Silence gets its own line rather than a count of zero. A server that has
    said nothing about a file and a server that has looked and found nothing
    are the same number and completely different facts.

    The model goes first because it decides how to read everything under it. An
    empty pulled set is an answer. An empty pushed one is the absence of one.
    """
    if not report["published"]:
        head = ["published        nothing: this server said nothing about the "
                "file, which is unknown and not clean"]
    else:
        head = [f"diagnostics      {report['n']}",
                f"version          {report['version']}",
                f"current          {'yes' if report['current'] else 'no'}"]
    lines = [f"model            {report['model']}"]
    lines += head + record_lines(report)
    for item in report["diagnostics"]:
        where = (item.get("range") or {}).get("start") or {}
        lines.append(f"  {where.get('line', '?')}:"
                     f"{where.get('character', '?')}  "
                     f"{item.get('message', '')}")
    return "\n".join(lines)


def record_lines(report: dict) -> list:
    """Where the run's record went, or that there is not one."""
    if report.get("log") is None:
        return ["log              none: this run left no record"]
    lines = [f"log              {report['log']}"]
    if report.get("transcript"):
        lines.append(f"transcript       {report['transcript']}")
    if "receipt" in report:
        # The record this run folded, not the chain's head. Frames from the
        # shutdown land after it, so the two are different strings and calling
        # both of them the head would read as a broken chain.
        lines.append(f"receipt          {report['receipt']['link']}")
    return lines


def render_verify(result: dict) -> str:
    """One verdict, and what it leaves open, which is never nothing."""
    lines = [f"verdict          {result['verdict']}",
             f"records checked  {result['checked']}",
             f"head             {result['head'] or 'none'}"]
    if result["failure_class"]:
        lines.append(f"failure          {result['failure_class']}")
    if result["broken_at"] is not None:
        lines.append(f"broken at        record {result['broken_at']}")
    lines += ["", result["detail"], "", "does not prove:"]
    return "\n".join(lines + [f"  - {limit}"
                              for limit in result["does_not_prove"]])
