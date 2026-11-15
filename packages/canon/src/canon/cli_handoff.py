"""`canon handoff` and `canon switch`: the brief for the next agent, and the
brief placed in that agent's own instruction file.

`handoff` prints the brief (or writes it to a new file) and can write the
receipt beside it; both files are checked before either is written, and a
failed second write removes the first. `switch` renders the target's workspace
instruction region with the brief inside, through the allow-list, and writes
it unless `--dry-run` is given; `--receipt` writes its receipt, and the store
keeps the last one per checkout and surface. A target with no instruction
file (markdown) carries no instruction block; both commands say how many they
left out and why, on stderr or the result line and as `omitted_blocks` in
`--json`. Both read only this project's pool plus any project named with
`--include-project`. Every failure, file IO included, ends as a named failure
code.
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

from .cli_files import check_new_files, instruction_writer, read_text, write_new_files
from .cli_workspace_common import (
    CommandFailure,
    Output,
    WorkspaceContext,
    build_context,
    emit,
    guarded,
)
from .workspace.backflow import pending_edits
from .workspace.brief import (
    BudgetError,
    SecretInRender,
    make_brief,
    omitted_blocks,
    omitted_note,
)
from .workspace.ledger import record_render_unlocked
from .workspace.pool import project_pool
from .workspace.switch import SwitchRefused, commit_switch, plan_switch
from .workspace.targets import UnknownTarget, target_for

def run_handoff_command(parsed: argparse.Namespace, *, stdout: TextIO, stderr: TextIO,
                        environ: Mapping[str, str], color: bool) -> int:
    out = Output(stdout, stderr, parsed.json_output, color)
    handler = _handoff if parsed.command == "handoff" else _switch

    def action() -> int:
        try:
            ctx = build_context(parsed, environ, out)
            return handler(parsed, ctx, out, environ)
        except UnknownTarget as exc:
            raise CommandFailure("invalid_args", str(exc)) from exc
        except BudgetError as exc:
            raise CommandFailure("budget_too_small", str(exc)) from exc
        except SwitchRefused as exc:
            raise CommandFailure(exc.code, str(exc)) from exc
        except SecretInRender as exc:
            raise CommandFailure("secret_quarantine", str(exc)) from exc
        except OSError as exc:
            raise CommandFailure("io_error", str(exc)) from exc

    return guarded(parsed.command, out, action)


def _pool(parsed, ctx: WorkspaceContext):
    declared = tuple(parsed.include_project)
    return project_pool(ctx.store, include_projects=declared), declared


def _receipt_text(receipt: dict) -> str:
    return json.dumps(receipt, sort_keys=True, indent=2) + "\n"


def _handoff(parsed, ctx: WorkspaceContext, out: Output, environ) -> int:
    target = target_for(parsed.to)
    pool, declared = _pool(parsed, ctx)
    hint = "The receipt lists every one." if parsed.receipt else None
    brief = make_brief(ctx.identity, pool, target, budget_bytes=parsed.budget_bytes,
                       budget_lines=parsed.budget_lines, declared=declared,
                       receipt_hint=hint)
    files = [(parsed.out, brief.text)] if parsed.out else []
    files += [(parsed.receipt, _receipt_text(brief.receipt))] if parsed.receipt else []
    write_new_files(files)
    omitted = omitted_blocks(brief)
    data = {"brief": brief.text, "receipt": brief.receipt, "omitted_blocks": omitted}
    message = f"brief for {target.name}: {len(brief.included)} records, " \
              f"{len(brief.left_out)} left out"
    note = omitted_note(omitted)
    message += f"; {note}" if note else ""
    if parsed.out:
        return emit(out, command="handoff", message=message, data=data,
                    text=f"{message}; wrote {parsed.out}")
    if note and not out.json_output:
        out.stderr.write(f"note: {note}\n")
    return emit(out, command="handoff", message=message, data=data, text=brief.text)


_DONE = {"write": "wrote", "create": "created", "unchanged": "unchanged"}
_WOULD = {"write": "would write", "create": "would create", "unchanged": "unchanged"}


def _status_words(status: str, dry_run: bool, rel: str | None) -> str:
    if rel is None:
        return "no instruction file for this target; the brief follows"
    return f"{(_WOULD if dry_run else _DONE)[status]} {rel}"


def _refuse_pending_edits(ctx: WorkspaceContext, plan, dry_run: bool) -> list[str]:
    """Edits made inside the region since canon last wrote it become proposals,
    and the switch stops until each one is accepted or rejected. Returns the
    ids of rejected edits the switch will overwrite, so the output names them."""
    report = pending_edits(ctx.store, plan, dry_run=dry_run)
    if report is None or not report["proposed"]:
        return [d["id"] for d in (report or {}).get("already_decided", []) if d.get("rejected")]
    rel = plan.surface.relative_path
    ids = ", ".join(p["id"] for p in report["proposed"])
    verb = "would become" if dry_run else "are now"
    raise CommandFailure(
        "edits_pending", f"{len(report['proposed'])} edits made inside the canon region "
        f"of {rel} {verb} proposals ({ids}); accept or reject each with "
        "canon workspace accept|reject, then switch again")


def _commit(ctx: WorkspaceContext, plan, target) -> None:
    """Write the file and its ledger entry under one project lock, so a held
    lock refuses before anything is written and a written file always has the
    ledger entry that marks it as canon's own."""
    write = instruction_writer(str(ctx.identity.root), create=plan.status == "create")
    with ctx.store.locked():
        commit_switch(plan, write, read_text)
        if plan.surface is not None:
            record_render_unlocked(ctx.store, plan.surface.relative_path, target.name,
                                   plan.interior, checkout=ctx.identity.checkout,
                                   owners=plan.owners, receipt=plan.receipt)


def _switch(parsed, ctx: WorkspaceContext, out: Output, environ) -> int:
    target = target_for(parsed.to)
    pool, declared = _pool(parsed, ctx)
    home = parsed.home or str(Path.home())
    hint = f"canon switch --to {target.name} --dry-run --receipt FILE lists every one."
    plan = plan_switch(ctx.identity, pool, target, home=home, read_text=read_text,
                       create=parsed.create, budget_bytes=parsed.budget_bytes,
                       budget_lines=parsed.budget_lines, declared=declared,
                       receipt_hint=hint, codex_home=environ.get("CODEX_HOME") or None)
    overwritten = _refuse_pending_edits(ctx, plan, parsed.dry_run)
    receipt = [(parsed.receipt, _receipt_text(plan.receipt))] if parsed.receipt else []
    check_new_files([path for path, _ in receipt])
    if not parsed.dry_run:
        _commit(ctx, plan, target)
    write_new_files(receipt)
    rel = plan.surface.relative_path if plan.surface else None
    lines = [f"{target.display}: {_status_words(plan.status, parsed.dry_run, rel)}",
             f"brief: {len(plan.brief.included)} records, "
             f"{len(plan.brief.left_out)} left out"]
    lines += [f"warning: {w}" for w in plan.warnings]
    if overwritten:
        verb = "would overwrite" if parsed.dry_run else "overwrote"
        lines.append(f"{verb} edits you rejected before: " + ", ".join(overwritten))
    if plan.surface is None or parsed.dry_run:
        lines += ["", plan.brief.text if plan.surface is None else plan.interior]
    data = {"target": target.name, "status": plan.status, "dry_run": parsed.dry_run,
            "surface": rel, "warnings": list(plan.warnings),
            "omitted_blocks": omitted_blocks(plan.brief),
            "brief": plan.brief.text, "receipt": plan.receipt}
    return emit(out, command="switch", message=lines[0], data=data, text="\n".join(lines))
