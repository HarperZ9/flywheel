"""`canon workspace import|accept|reject`: session transcripts in, proposals out,
and the person's decision on each proposal.

`import` reads one Claude Code session or Codex rollout file, scrubs it, and
writes proposed records with their origin. It prints what it proposed, what it
dropped by declared category, and what the scrubber redacted. `accept` moves a
proposal into the project's accepted records; `reject` removes it and logs the
reason, so the same proposal is not offered again.
"""
from __future__ import annotations

from .cli_workspace_common import CommandFailure, Output, WorkspaceContext, emit
from .workspace.describe import summary
from .workspace.import_common import ImportRefused
from .workspace.import_write import import_session


def _report_lines(report: dict, path: str) -> list[str]:
    verb = "would propose" if report["dry_run"] else "proposed"
    check = report["project_check"]
    lines = [f"{verb} {len(report['proposed'])} records from {path} "
             f"(project check: {check['status']} by {check['by']})"]
    lines += [f"- {p['kind']} {p['id']} ({p['rule']}, line {p['line']})"
              for p in report["proposed"]]
    for label, key in (("already accepted", "already_accepted"),
                       ("rejected before", "previously_rejected")):
        if report[key]:
            lines.append(f"{label}: {', '.join(p['id'] for p in report[key])}")
    drops = [f"{k}={v}" for k, v in report["declared_drops"].items() if v]
    lines.append("declared drops: " + (", ".join(drops) or "none"))
    if report["user_declared_drops"]:
        lines.append("drops you declared: " + ", ".join(
            f"{k}={v}" for k, v in report["user_declared_drops"].items()))
    secrets = [f"{k}={v}" for k, v in report["secrets_redacted"].items()]
    lines.append("secrets redacted: " + (", ".join(secrets) or "none"))
    if report["proposed"] and not report["dry_run"]:
        lines.append("review with `canon workspace list --proposed`, then "
                     "`canon workspace accept <id>` or `reject <id> --reason ...`")
    return lines


def run_import_cmd(parsed, ctx: WorkspaceContext, out: Output, command: str) -> int:
    try:
        report = import_session(ctx.identity, ctx.store, parsed.path,
                                source_format=parsed.source_format,
                                accept_foreign=parsed.accept_foreign_source,
                                user_drops=tuple(parsed.drop_type),
                                dry_run=parsed.dry_run)
    except ImportRefused as exc:
        raise CommandFailure(exc.code, str(exc)) from exc
    except OSError as exc:
        raise CommandFailure("io_error", f"cannot read {parsed.path}: {exc}") from exc
    lines = _report_lines(report, parsed.path)
    return emit(out, command=command, message=lines[0], data={"report": report},
                text="\n".join(lines))


def run_decide_cmd(parsed, ctx: WorkspaceContext, out: Output, command: str) -> int:
    accept = parsed.ws_command == "accept"
    reason = parsed.reason or ""
    if not accept and not reason.strip():
        raise CommandFailure("invalid_args", "a rejection needs --reason")
    row = ctx.store.decide(parsed.record_id, accept=accept,
                           reason=reason or "accepted without a stated reason",
                           force=accept and parsed.force)
    verb = "accepted" if accept else "rejected"
    return emit(out, command=command, message=f"{verb} {row.record.id}",
                data={"row": row.to_dict(), "accepted": accept},
                text=f"{verb} {summary(row.record)}")


def run_pull_cmd(parsed, ctx: WorkspaceContext, out: Output, command: str) -> int:
    from pathlib import Path

    from .cli_files import read_text
    from .workspace.backflow import pending_edits
    from .workspace.pool import project_pool
    from .workspace.switch import SwitchRefused, plan_switch
    from .workspace.targets import UnknownTarget, target_for

    try:
        target = target_for(parsed.target)
        if target.harness is None:
            raise CommandFailure("invalid_args", f"{target.name} has no instruction file "
                                                 "to read back")
        plan = plan_switch(ctx.identity, project_pool(ctx.store), target,
                           home=parsed.home or str(Path.home()), read_text=read_text,
                           check_limits=False)
    except UnknownTarget as exc:
        raise CommandFailure("invalid_args", str(exc)) from exc
    except SwitchRefused as exc:
        if exc.code == "not_found":
            raise CommandFailure("not_found", f"nothing to read back: the {target.display} "
                                              "instruction file does not exist") from exc
        raise CommandFailure(exc.code, str(exc)) from exc
    report = pending_edits(ctx.store, plan, dry_run=parsed.dry_run) or {
        "surface": plan.surface.relative_path if plan.surface else None,
        "proposed": [], "already_decided": [], "parse_error": None,
        "secrets_redacted": {}, "dry_run": parsed.dry_run}
    verb = "would propose" if parsed.dry_run else "proposed"
    lines = [f"{verb} {len(report['proposed'])} records from edits in {report['surface']}"]
    lines += [f"- {p['kind']} {p['id']} ({p['rule']}, line {p['line']})"
              for p in report["proposed"]]
    if report["already_decided"]:
        lines.append("already decided: " + ", ".join(p["id"] for p in report["already_decided"]))
    if report["parse_error"]:
        lines.append(f"the region no longer parses ({report['parse_error']}); its changed "
                     "lines were kept as one proposed note")
    return emit(out, command=command, message=lines[0], data={"report": report},
                text="\n".join(lines))


IMPORT_HANDLERS = {
    "import": run_import_cmd,
    "accept": run_decide_cmd,
    "reject": run_decide_cmd,
    "pull": run_pull_cmd,
}
