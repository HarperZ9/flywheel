"""dap_report.py -- turn one debug run's report into something a person reads.

Split from the command so that what the command decides and what it prints stay
separable. The `--json` shape is the report dict these functions are handed, so
a change here is a change to the reading and not to the record.

Two things sit in the left column on purpose. Whether the program stopped, and
how many of the breakpoints the adapter says it actually bound. A run that set
four breakpoints and bound one is the ordinary case for a file the debuggee has
not loaded, and a reader who does not see that number will read a stack that
never happened as a stack that did.
"""
from __future__ import annotations

import json

__all__ = ["as_json", "render_error", "render_run", "render_verify"]


def render_run(report: dict) -> str:
    """One session, from what it asked for down to where it stopped."""
    lines = [f"adapter          {report['adapter']}",
             f"session          {report['request']}",
             f"breakpoints      {report['verified']} bound of "
             f"{report['requested']} asked for"]
    if report["unbound"]:
        for entry in report["unbound"]:
            lines.append(f"  not bound      {entry['source']}:{entry['line']}"
                         f"  {entry['message'] or 'the adapter gave no reason'}")
    lines += _stop_lines(report) + _record_lines(report)
    lines += _decision_lines(report["decisions"])
    return "\n".join(lines)


def _stop_lines(report: dict) -> list:
    """Where it stopped, or the fact that it did not.

    Not stopping gets a sentence rather than an empty stack. A program that ran
    to the end and a program still running when the clock expired are different
    facts, and neither of them is a stack of zero frames.
    """
    stop = report["stop"]
    if stop is None:
        if report["terminated"]:
            return ["stopped          no: the program ran to the end without "
                    f"stopping, exit {report['exit_code']}"]
        return ["stopped          no: nothing stopped in the time allowed, "
                "which is unknown and not the same as a clean run"]
    lines = [f"stopped          {stop['reason']} on thread "
             f"{stop['thread_id']}"]
    if stop["description"]:
        lines.append(f"                 {stop['description']}")
    stack = report["stack"]
    for frame in stack["frames"]:
        source = (frame.get("source") or {}).get("path", "")
        lines.append(f"  {frame.get('line', '?'):>6}  {frame.get('name', '')}"
                     f"  {source}")
    if stack["truncated"]:
        lines.append(f"  ... {stack['total']} frames in all, "
                     f"{len(stack['frames'])} read")
    return lines + _scope_lines(report["scopes"])


def _scope_lines(scopes: dict) -> list:
    """The names in each scope, and their values when the caller asked.

    An entry is a name on its own unless the run was started with `--values`.
    The command builds it that way; this only reads what it was given.
    """
    lines = []
    for name, entries in scopes.items():
        lines.append(f"  {name}")
        for entry in entries:
            lines.append(f"    {entry}")
    return lines


def _record_lines(report: dict) -> list:
    """Where the run's record went, or that there is not one."""
    if report.get("log") is None:
        return ["log              none: this run left no record"]
    lines = [f"log              {report['log']}"]
    if report.get("transcript"):
        lines.append(f"transcript       {report['transcript']}")
    if "receipt" in report:
        # The record this run folded, not the chain's head. Frames from the
        # disconnect land after it, so the two are different strings and calling
        # both of them the head would read as a broken chain.
        lines.append(f"receipt          {report['receipt']['link']}")
    return lines


def _decision_lines(decisions: list) -> list:
    """What the adapter asked this client to do, and what it was told.

    Printed even when the answer was no, because a refusal is the part a reader
    cannot reconstruct from the outcome. A run where an adapter asked to start a
    process and was refused looks, from its exit code alone, exactly like a run
    where it never asked.
    """
    if not decisions:
        return []
    lines = ["", "the adapter asked for:"]
    for decision in decisions:
        answer = "allowed" if decision["allowed"] else "refused"
        lines.append(f"  {answer}  {decision['method']}  "
                     f"{decision['detail']}")
        if decision["reason"]:
            lines.append(f"           {decision['reason']}")
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


def render_error(report: dict) -> str:
    """The session never ran. Say why, and hand back the adapter's complaint."""
    lines = [f"the session did not run: {report['error']}"]
    if report["stderr"].strip():
        lines.append(report["stderr"].rstrip())
    return "\n".join(lines)


def as_json(report: dict) -> str:
    return json.dumps(report, indent=2)
