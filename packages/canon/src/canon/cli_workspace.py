"""`canon workspace ...`: the project's identity, its records, and the explicit
moves between projects and global scope.

Each handler takes the parsed arguments, the project context and the output
channel, and returns an exit code. Refusals raised underneath (isolation, a
malformed store, a held lock) are mapped to failure codes by `guarded`.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from typing import TextIO

from .cli_workspace_common import (
    CommandFailure,
    Output,
    WorkspaceContext,
    build_context,
    emit,
    guarded,
)
from .cli_import import IMPORT_HANDLERS
from .cli_workspace_author import AUTHOR_HANDLERS
from .workspace.describe import summary
from .workspace.moves import adopt, promote
from .workspace.rows import STATE_ACCEPTED, STATE_PROPOSED
from .workspace.switch import workspace_surface
from .workspace.target_fidelity import DECLARED_DOWNGRADES
from .workspace.targets import TARGETS


def run_workspace_command(parsed: argparse.Namespace, *, stdout: TextIO,
                          stderr: TextIO, environ: Mapping[str, str],
                          color: bool) -> int:
    out = Output(stdout, stderr, parsed.json_output, color)
    command = f"workspace {parsed.ws_command}"

    def action() -> int:
        ctx = build_context(parsed, environ, out)
        return _HANDLERS[parsed.ws_command](parsed, ctx, out, command)

    return guarded(command, out, action)


def _identity(parsed, ctx: WorkspaceContext, out: Output, command: str) -> int:
    public = ctx.identity.to_public()
    accepted = len(ctx.store.rows(STATE_ACCEPTED))
    proposed = len(ctx.store.rows(STATE_PROPOSED))
    text = "\n".join([
        f"project  {public['project_id']}",
        f"method   {public['method']}",
        f"key      {public['key']}",
        f"label    {public['label']}",
        f"records  {accepted} accepted, {proposed} proposed",
    ])
    data = {"identity": public, "accepted": accepted, "proposed": proposed}
    return emit(out, command=command, message="project identity", data=data, text=text)


def _list(parsed, ctx: WorkspaceContext, out: Output, command: str) -> int:
    state = STATE_PROPOSED if parsed.proposed else STATE_ACCEPTED
    rows = [r for r in ctx.store.rows(state)
            if parsed.kind is None or r.record.kind == parsed.kind]
    rows.sort(key=lambda r: (r.record.provenance.create_ord or 0, r.record.id))
    lines = [f"{state} records for {ctx.identity.label}: {len(rows)}"]
    lines += [f"- {summary(r.record)}" for r in rows]
    data = {"project_id": ctx.identity.project_id, "state": state,
            "records": [r.to_dict() for r in rows]}
    return emit(out, command=command, message=f"{len(rows)} {state} records",
                data=data, text="\n".join(lines))


def _promote(parsed, ctx: WorkspaceContext, out: Output, command: str) -> int:
    if not parsed.reason.strip():
        raise CommandFailure("invalid_args", "promotion needs a non-empty --reason")
    row = promote(ctx.store, parsed.record_id, reason=parsed.reason)
    text = (f"promoted {row.record.id} to global scope; every project now reads it. "
            "The promotion is logged in the project log and the global log.")
    data = {"record": row.to_dict(), "from_project": ctx.identity.project_id}
    return emit(out, command=command, message="promoted", data=data, text=text)


def _adopt(parsed, ctx: WorkspaceContext, out: Output, command: str) -> int:
    rows = adopt(ctx.store, parsed.from_project, reason=parsed.reason)
    lines = [f"adopted {len(rows)} records from {parsed.from_project} (logged):"]
    lines += [f"- {summary(r.record)}" for r in rows]
    data = {"from_project": parsed.from_project,
            "records": [r.to_dict() for r in rows]}
    return emit(out, command=command, message=f"adopted {len(rows)} records",
                data=data, text="\n".join(lines))


def _targets(parsed, ctx: WorkspaceContext, out: Output, command: str) -> int:
    rows = []
    for target in TARGETS:
        surface = workspace_surface(target)
        rows.append({"name": target.name, "file": surface.relative_path if surface else None,
                     "brief_bytes": target.brief_bytes, "brief_lines": target.brief_lines,
                     "file_bytes_limit": target.file_bytes_limit,
                     "file_lines_advice": target.file_lines_advice, "basis": target.basis,
                     "downgrades": DECLARED_DOWNGRADES.get(target.name, {})})
    lines = []
    for row in rows:
        lines.append(f"{row['name']}: {row['file'] or 'no file (paste the brief)'}; "
                     f"brief {row['brief_bytes']} bytes, {row['brief_lines']} lines")
        lines += [f"  declared {k}: {v}" for k, v in row["downgrades"].items()]
    return emit(out, command=command, message=f"{len(rows)} targets",
                data={"targets": rows}, text="\n".join(lines))


_HANDLERS = {
    "id": _identity,
    "list": _list,
    "promote": _promote,
    "adopt": _adopt,
    "targets": _targets,
    **AUTHOR_HANDLERS,
    **IMPORT_HANDLERS,
}
