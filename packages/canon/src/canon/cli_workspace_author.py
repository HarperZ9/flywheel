"""`canon workspace focus|task|set-status|decide|constraint`: writing the
project's working state by hand.

Every command builds one validated record through workspace.authoring and puts
it in this project's store as an accepted workspace record. Nothing here writes
global scope or another project.
"""
from __future__ import annotations

from .cli_workspace_common import Output, WorkspaceContext, emit
from .workspace import authoring
from .workspace.describe import summary
from .schema import Record


def _stored(ctx: WorkspaceContext, out: Output, command: str, record: Record,
            verb: str) -> int:
    row = ctx.store.put(record, action=command.split()[-1])
    text = f"{verb} {summary(row.record)}"
    return emit(out, command=command, message=f"{verb} {record.id}",
                data={"record": row.to_dict()}, text=text)


def focus(parsed, ctx: WorkspaceContext, out: Output, command: str) -> int:
    branch = parsed.branch if parsed.branch is not None else \
        authoring.current_branch(ctx.identity.root)
    record = authoring.focus(ctx.store, goal=parsed.goal, areas=parsed.area,
                             branch=branch, notes=parsed.notes)
    return _stored(ctx, out, command, record, "focus set:")


def task(parsed, ctx: WorkspaceContext, out: Output, command: str) -> int:
    record = authoring.work_item(ctx.store, title=parsed.title,
                                 status=parsed.status, detail=parsed.detail)
    return _stored(ctx, out, command, record, "added")


def set_status(parsed, ctx: WorkspaceContext, out: Output, command: str) -> int:
    record = authoring.update_work_item(ctx.store, parsed.record_id,
                                        status=parsed.status, detail=parsed.detail)
    return _stored(ctx, out, command, record, f"now {parsed.status}:")


def decide(parsed, ctx: WorkspaceContext, out: Output, command: str) -> int:
    record = authoring.decision(
        ctx.store, title=parsed.title, decision_text=parsed.decision,
        context=parsed.context, status=parsed.status,
        rejected=[tuple(pair) for pair in parsed.reject])
    return _stored(ctx, out, command, record, "recorded")


def constraint(parsed, ctx: WorkspaceContext, out: Output, command: str) -> int:
    record = authoring.constraint(
        ctx.store, statement=parsed.statement,
        category="quirk" if parsed.quirk else "constraint",
        reason=parsed.reason, applies_to=parsed.applies_to)
    return _stored(ctx, out, command, record, "recorded")


AUTHOR_HANDLERS = {
    "focus": focus,
    "task": task,
    "set-status": set_status,
    "decide": decide,
    "constraint": constraint,
}
