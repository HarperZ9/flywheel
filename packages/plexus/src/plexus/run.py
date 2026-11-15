"""run.py — turn a plan into runnable output.

`plan_to` says what feeds a target; this emits the concrete, ordered invocation
sequence to actually produce it — a shell script you can read, edit, and run. It
does NOT execute anything itself (the tools live in their own environments); it
makes the plan actionable and auditable instead of leaving it as advice. Feedback
loops are emitted as a labelled comment, never silently linearized into a lie.
"""
from __future__ import annotations

from .mesh import Mesh
from .plan import _cli, plan_to


def pipeline_script(mesh: Mesh, target: str) -> str:
    """A runnable, commented shell script that invokes each upstream tool in
    dependency order to feed `target`."""
    plan = plan_to(mesh, target)
    if plan.get("error"):
        return f"# error: {plan['error']} ({target!r})"

    lines = ["#!/usr/bin/env bash", "set -euo pipefail",
             f"# plexus pipeline to feed: {target}",
             f"# sources: {', '.join(plan['sources']) or '(none)'}"]
    if plan["cyclic"]:
        lines.append(f"# NOTE: feedback loop {' <-> '.join(plan['cyclic'])} : "
                     "these tools mutually depend; run order among them is not linear")
    lines.append("")

    for organ in plan["order"]:
        if organ == target:
            continue
        inbound = [h for h in plan["hops"] if h["consumer"] == organ]
        produced = sorted({h["capability"] for h in plan["hops"] if h["producer"] == organ})
        note = f"produces: {', '.join(produced)}" if produced else "source"
        lines.append(f"# {organ}: {note}")
        lines.append(f"{_cli(mesh, organ)} run   # -> feeds "
                     f"{', '.join(sorted({h['consumer'] for h in plan['hops'] if h['producer'] == organ}))}")
        lines.append("")

    feeders = sorted({h["producer"] for h in plan["hops"] if h["consumer"] == target})
    lines.append(f"# {target}: consumes from {', '.join(feeders) or '(external inputs only)'}")
    lines.append(f"{_cli(mesh, target)} run")
    return "\n".join(lines)
