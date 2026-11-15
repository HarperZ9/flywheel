"""Internal canon command-line entrypoint."""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from collections.abc import Mapping
from typing import TextIO

from .bootstrap import BootstrapConfig, BootstrapConfigError, run_bootstrap
from .cli_format import color_enabled, make_result, write_result
from .cli_init import run_init
from .cli_parser import ParserExit, build_canon_parser
from .exit_codes import EX_OK, EX_USAGE

COMMANDS = (
    "mcp",
    "check",
    "blocks",
    "init",
    "compile",
    "preview",
    "doctor",
    "export",
    "rescue",
    "undo",
    "bootstrap",
    "workspace",
    "handoff",
    "switch",
    "context",
)


def build_parser() -> argparse.ArgumentParser:
    """Build Canon's command parser."""
    return build_canon_parser(COMMANDS)


def run_cli(
    argv: list[str],
    *,
    stdin: TextIO | None = None,
    stdout: TextIO,
    stderr: TextIO,
    environ: Mapping[str, str],
) -> int:
    """Run canon's CLI with caller-owned streams and environment."""
    tokens = _argv_copy(argv, stderr)
    if tokens is None:
        return EX_USAGE
    tokens = _normalize_global_options(tokens)

    json_requested = _json_requested(tokens)
    parse_color = color_enabled(environ=environ, no_color="--no-color" in tokens, is_tty=_is_tty(stdout))
    parser_stderr = io.StringIO()
    parser = build_canon_parser(COMMANDS, stdout=stdout, stderr=parser_stderr)
    try:
        parsed = parser.parse_args(tokens)
    except ParserExit as error:
        if error.status == EX_OK:
            return error.status
        return _parse_error(stdout, stderr, json_requested=json_requested, color=parse_color)

    return _run_parsed(parsed, stdin=stdin, stdout=stdout, stderr=stderr, environ=environ)


def main(argv: list[str] | None = None) -> int:
    """Run canon from process-global streams."""
    tokens = list(sys.argv[1:] if argv is None else argv)
    return run_cli(tokens, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr, environ=os.environ)


def _run_parsed(
    parsed: argparse.Namespace,
    *,
    stdin: TextIO | None,
    stdout: TextIO,
    stderr: TextIO,
    environ: Mapping[str, str],
) -> int:
    color = color_enabled(environ=environ, no_color=parsed.no_color, is_tty=_is_tty(stdout))
    if parsed.command == "mcp":
        from .local_mcp import serve

        return serve(stdin=stdin, stdout=stdout)
    if parsed.command == "check":
        return _run_check(stdout)
    if parsed.command == "blocks":
        return _run_blocks(stdout)
    if parsed.command in ("compile", "preview"):
        from .cli_compile import run_compile_command

        return run_compile_command(parsed, stdin=stdin, stdout=stdout, stderr=stderr, color=color)
    if parsed.command == "doctor":
        from .doctor import run_doctor_command

        return run_doctor_command(parsed, stdin=stdin, stdout=stdout, stderr=stderr, color=color)
    if parsed.command == "export":
        from .cli_export import run_export_command

        return run_export_command(parsed, stdin=stdin, stdout=stdout, stderr=stderr, color=color)
    if parsed.command == "undo":
        from .cli_export import run_undo_command

        return run_undo_command(parsed, stdout=stdout, stderr=stderr, color=color)
    if parsed.command in ("workspace", "handoff", "switch"):
        return _run_workspace_family(parsed, stdout=stdout, stderr=stderr, environ=environ, color=color)
    if parsed.command == "rescue":
        from .cli_rescue import run_rescue_command

        return run_rescue_command(parsed, stdin=stdin, stdout=stdout, stderr=stderr, color=color)
    if parsed.command == "context":
        return _run_context(parsed, stdin, stdout, stderr, environ, color)
    return write_result(
        _command_result(parsed),
        stdout=stdout,
        stderr=stderr,
        json_output=parsed.json_output,
        color=color,
    )


def _run_workspace_family(parsed: argparse.Namespace, **streams) -> int:
    """The W1 commands: `workspace ...`, `handoff` and `switch`."""
    if parsed.command == "workspace":
        from .cli_workspace import run_workspace_command

        return run_workspace_command(parsed, **streams)
    from .cli_handoff import run_handoff_command

    return run_handoff_command(parsed, **streams)


def _run_context(parsed: argparse.Namespace, stdin, stdout, stderr, environ, color) -> int:
    """`canon context purge` and `canon context retention`."""
    from .cli_context_purge import run_context_command

    return run_context_command(parsed, stdin=stdin, stdout=stdout, stderr=stderr,
                               environ=environ, color=color)


def _run_check(stdout: TextIO) -> int:
    from .local_mcp import _check

    report = _check()
    json.dump(report, stdout, indent=2)
    stdout.write("\n")
    return EX_OK if report["ok"] else 1


def _run_blocks(stdout: TextIO) -> int:
    from .local_mcp import _blocks

    json.dump(_blocks({}), stdout, indent=2)
    stdout.write("\n")
    return EX_OK


def _command_result(parsed: argparse.Namespace):
    if parsed.command == "init":
        return _init_result(parsed)
    if parsed.command == "bootstrap":
        return _bootstrap_result(parsed)
    return make_result(ok=True, command=parsed.command, failure_code="ok", message="ready")


def _init_result(parsed: argparse.Namespace):
    report = run_init(workspace=parsed.workspace, state_dir=parsed.state_dir, apply=parsed.apply)
    return make_result(
        ok=report.ok,
        command="init",
        failure_code=report.failure_code,
        message=report.message,
        data=report.data,
    )


def _bootstrap_result(parsed: argparse.Namespace):
    try:
        config = BootstrapConfig(
            workspace=parsed.workspace,
            state_dir=parsed.state_dir,
            target=parsed.target,
            tier=parsed.tier,
            profile=parsed.profile,
            offline=parsed.offline,
            run_id=parsed.run_id,
            records_path=parsed.records,
            atoms_path=parsed.atoms,
            readiness_response_path=parsed.readiness_response,
            started_at=parsed.started_at,
        )
    except BootstrapConfigError as exc:
        return make_result(ok=False, command="bootstrap", failure_code=exc.code, message="invalid bootstrap config")
    report = run_bootstrap(config)
    return make_result(
        ok=report.ok,
        command="bootstrap",
        failure_code=report.failure_code,
        message=report.message,
        data=report.to_result_data(),
    )


def _argv_copy(argv: list[str], stderr: TextIO) -> list[str] | None:
    if type(argv) is not list:
        stderr.write("canon: argv must be list[str]\n")
        return None
    if any(type(item) is not str for item in argv):
        stderr.write("canon: argv entries must be str\n")
        return None
    return list(argv)


def _normalize_global_options(tokens: list[str]) -> list[str]:
    global_options = [item for item in tokens if item in ("--json", "--no-color")]
    rest = [item for item in tokens if item not in ("--json", "--no-color")]
    return global_options + rest


def _is_tty(stream: TextIO) -> bool:
    isatty = getattr(stream, "isatty", None)
    if not callable(isatty):
        return False
    try:
        return bool(isatty())
    except OSError:
        return False


def _json_requested(tokens: list[str]) -> bool:
    return "--json" in tokens


def _parse_error(stdout: TextIO, stderr: TextIO, *, json_requested: bool, color: bool) -> int:
    result = make_result(ok=False, command="canon", failure_code="invalid_args", message="invalid arguments")
    return write_result(result, stdout=stdout, stderr=stderr, json_output=json_requested, color=color)


__all__ = ["COMMANDS", "build_parser", "run_cli", "main"]


if __name__ == "__main__":
    # MCP host configs launch "python -m canon.cli mcp"; without this guard the module
    # imports, does nothing, and exits 0, which a host reports as "Connection closed".
    raise SystemExit(main())
