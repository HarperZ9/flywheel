"""acp_cli.py -- delegate a turn to an ACP agent and keep the record of it.

Editors already speak the Agent Client Protocol, so an agent that speaks it
works in any of them. This command is the other end: it drives such an agent
from the terminal, holds it to a grant boundary, and writes down every frame
that crossed the wire.

Two subcommands.

`run` starts the agent, sends one prompt, and reports what the turn amounted
to. The agent's file reads and writes and its requests for permission are
answered by a policy, and the default policy refuses all three. Widen it on
purpose with `--workspace`, `--allow-writes` and `--allow-permission`:

    flywheel acp run --prompt "summarise the tests" --log-dir runs/one -- \
        my-acp-agent --stdio

`verify` rechecks a run somebody else did, on a machine that never saw it:

    flywheel acp verify --log runs/one/action-witness.jsonl \
        --transcript runs/one/frames.jsonl

The log holds a digest per frame, each link covering the one before it. The
transcript holds what those digests were taken over, and it is off by default
because it carries the prompt text verbatim. With both, `verify` reproduces
every byte and answers MATCH. With the log alone it answers UNVERIFIABLE,
which is the honest reading of a chain nobody can reproduce.

Exit codes, because a harness branches on them:

    run     0 the turn ended cleanly
            1 the agent refused
            3 the turn stopped for another reason, or never ran at all, so
              there is no answer here rather than a refused one

    verify  0 MATCH, every record links and every byte reproduced
            1 TAMPERED, a link or a digest does not hold
            3 UNVERIFIABLE, nothing here was checkable enough to decide

Two is skipped because argparse already spends it on a usage error.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from .acp_client import AcpClient, AuthRequired, VersionUnsupported
from .acp_connection import ConnectionClosed, PeerError
from .acp_policy import AllowAll, DenyAll, WorkspacePolicy
from .acp_turn import END_TURN, REFUSAL
from .acp_witness import AcpWitness, does_not_prove, transcript_resolver
from .action_witness import open_log, verify_log
from .byte_witness_verify import MATCH, TAMPERED

OK, FAILED, UNCHECKED = 0, 1, 3


def _policy(args: argparse.Namespace):
    """The grant boundary this run gets. Default-deny, widened by flags."""
    if args.allow_all:
        return AllowAll()
    if args.workspace is None:
        return DenyAll()
    return WorkspacePolicy(args.workspace, allow_writes=args.allow_writes,
                           allow_permission=args.allow_permission)


def _witness(args: argparse.Namespace):
    """The log and transcript this run writes to, or nothing if none was asked
    for. A run with no `--log-dir` still works and leaves no receipt."""
    if args.log_dir is None:
        return None
    run_id = args.run_id or time.strftime("acp-%Y%m%d-%H%M%S")
    log = open_log(run_id, directory=args.log_dir)
    transcript = args.transcript
    if transcript is None and args.keep_bytes:
        transcript = Path(args.log_dir) / "frames.jsonl"
    return AcpWitness(log, transcript=transcript)


def run(args: argparse.Namespace) -> int:
    witness = _witness(args)
    policy = _policy(args)
    client = AcpClient.spawn(args.agent, cwd=args.cwd, policy=policy,
                             observer=witness.observe_frame if witness else None)
    try:
        client.initialize(timeout=args.timeout)
        client.new_session(args.cwd, timeout=args.timeout)
        turn = client.prompt(args.prompt, timeout=args.turn_timeout)
    except (AuthRequired, ConnectionClosed, PeerError, TimeoutError,
            ValueError, VersionUnsupported) as exc:
        return _unreached(exc, client, args)
    finally:
        client.close()
    report = {"stop_reason": turn.stop_reason, "text": turn.text,
              "thinking_characters": len(turn.thinking),
              "tool_calls": [call.title for call in turn.tool_calls.values()],
              "protocol_version": client.protocol_version,
              "refusals": [d.method for d in policy.decisions if not d.allowed],
              "stderr": client.stderr[-2000:]}
    if witness is not None:
        witness.record_decisions(policy)
        report["receipt"] = witness.record_turn(turn)
        report["log"] = str(witness.log.path)
        report["transcript"] = (str(witness.transcript)
                                if witness.transcript else None)
    print(json.dumps(report, indent=2) if args.json else _render_run(report))
    if turn.stop_reason == END_TURN:
        return OK
    return FAILED if turn.stop_reason == REFUSAL else UNCHECKED


def _unreached(exc: Exception, client: AcpClient, args) -> int:
    """The turn never happened. Say why, and hand back what the agent said.

    Closed first, because the thread draining the agent's stderr is where its
    startup faults land and it has not finished while the pipe is still open.
    """
    client.close()
    report = {"error": f"{type(exc).__name__}: {exc}",
              "stderr": client.stderr[-2000:]}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"the turn did not run: {report['error']}")
        if report["stderr"].strip():
            print(report["stderr"].rstrip())
    return UNCHECKED


def _render_run(report: dict) -> str:
    lines = [f"stop reason      {report['stop_reason'] or 'none'}",
             f"protocol         v{report['protocol_version']}"]
    if report["tool_calls"]:
        lines.append(f"tool calls       {', '.join(report['tool_calls'])}")
    if report["refusals"]:
        lines.append(f"refused          {', '.join(report['refusals'])}")
    if "log" in report:
        lines.append(f"log              {report['log']}")
        if report["transcript"]:
            lines.append(f"transcript       {report['transcript']}")
        lines.append(f"head             {report['receipt']['link']}")
    else:
        lines.append("log              none: this run left no record")
    if report["text"]:
        lines += ["", report["text"]]
    return "\n".join(lines)


def verify(args: argparse.Namespace) -> int:
    resolve = None
    if args.transcript is not None:
        try:
            resolve = transcript_resolver(args.transcript)
        except (OSError, ValueError, KeyError) as exc:
            print(f"the transcript could not be read: {exc}")
            return UNCHECKED
    result = verify_log(args.log, resolve=resolve)
    print(json.dumps(result, indent=2) if args.json else _render_verify(result))
    if result["verdict"] == MATCH:
        return OK
    return FAILED if result["verdict"] == TAMPERED else UNCHECKED


def _render_verify(result: dict) -> str:
    lines = [f"verdict          {result['verdict']}",
             f"records checked  {result['checked']}",
             f"head             {result['head'] or 'none'}"]
    if result["failure_class"]:
        lines.append(f"failure          {result['failure_class']}")
    if result["broken_at"] is not None:
        lines.append(f"broken at        record {result['broken_at']}")
    lines += ["", result["detail"], "", "does not prove:"]
    lines += [f"  - {limit}" for limit in result["does_not_prove"]]
    return "\n".join(lines)


def _add_run(sub) -> None:
    parser = sub.add_parser("run", help="send one prompt to an ACP agent")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--cwd", type=Path, default=None,
                        help="the directory the agent works in. Defaults here.")
    parser.add_argument("--workspace", type=Path, default=None,
                        help="let the agent read files under this directory. "
                             "Without it every file request is refused.")
    parser.add_argument("--allow-writes", action="store_true",
                        help="let the agent write inside the workspace too.")
    parser.add_argument("--allow-permission", action="store_true",
                        help="answer the agent's permission requests yes. "
                             "Without it they are answered no.")
    parser.add_argument("--allow-all", action="store_true",
                        help="drop the boundary: any path, every request "
                             "granted. For a sandbox, not for a workstation.")
    parser.add_argument("--log-dir", type=Path, default=None,
                        help="write the run's action log here. Without it the "
                             "run leaves no receipt.")
    parser.add_argument("--run-id", default=None,
                        help="name the run. Defaults to the time it started.")
    parser.add_argument("--transcript", type=Path, default=None,
                        help="keep what each digest was taken over, here. It "
                             "holds the prompt and the answer verbatim.")
    parser.add_argument("--keep-bytes", action="store_true",
                        help="keep the transcript beside the log, under the "
                             "log directory.")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="seconds to wait for the handshake.")
    parser.add_argument("--turn-timeout", type=float, default=600.0,
                        help="seconds to wait for the turn to end.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("agent", nargs="+",
                        help="the agent to start, after a bare --")
    parser.set_defaults(handler=run)


def _add_verify(sub) -> None:
    parser = sub.add_parser("verify", help="recheck a run's log offline")
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--transcript", type=Path, default=None,
                        help="the bytes the log's digests were taken over. "
                             "Without it the answer is UNVERIFIABLE.")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(handler=verify)


def main(argv: list[str] | None = None) -> int:
    # No abbreviation. Argparse takes any unambiguous prefix by default, and a
    # near-miss of a flag that widens a grant has to be a usage error.
    parser = argparse.ArgumentParser(prog="flywheel acp", allow_abbrev=False,
                                     description=__doc__.splitlines()[0])
    parser.add_argument("--limits", action="store_true",
                        help="print what an ACP run record does not prove.")
    sub = parser.add_subparsers(dest="command")
    _add_run(sub)
    _add_verify(sub)
    args = parser.parse_args(argv)
    if args.limits:
        print("\n".join(f"  - {limit}" for limit in does_not_prove()))
        return OK
    if not getattr(args, "handler", None):
        parser.print_help()
        return UNCHECKED
    return args.handler(args)


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
