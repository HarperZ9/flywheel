"""dap_cli.py -- debug a program under an adapter, and keep the record of it.

A debug session is the highest-value thing an agent does that nobody can check
afterwards. It reads a live process: a breakpoint hit, a stack, a variable. Those
readings become claims in the answer, and the wire they came off is gone the
moment the adapter exits. This command runs the session and writes down every
frame that crossed, so somebody who was not there can recheck it.

Two subcommands.

`run` starts an adapter, sets breakpoints, and reports the first stop:

    flywheel dap run --program app.py --break app.py:42 \
        --log-dir runs/one --keep-bytes -- python -m debugpy.adapter

`verify` rechecks a run somebody else did, on a machine that never saw it:

    flywheel dap verify --log runs/one/action-witness.jsonl \
        --transcript runs/one/frames.jsonl

This client starts no process on an adapter's behalf unless it is told to. A
debug adapter can ask its client to run a command line of the adapter's choosing,
and the answer here is no until `--allow-terminal`, which allows it inside the
root and nowhere else. Either answer goes on the record, because a run where an
adapter asked and was refused looks, from its exit code alone, exactly like a run
where it never asked.

Exit codes, because a harness branches on them:

    run     0 the program stopped, and the record says where
            1 the adapter refused: the launch failed, or it answered an error
            3 nothing to check: it never started, it timed out, or it never
              stopped, which is unknown and not the same as a clean run

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

from .action_witness import open_log, verify_log
from .byte_witness_verify import MATCH, TAMPERED
from .dap_args import breakpoints_from, build_parser
from .dap_client import DapClient
from .dap_peer import AdapterError, ConnectionClosed
from .dap_policy import AllowTerminal, DenyAll
from .dap_report import as_json, render_error, render_run, render_verify
from .dap_witness import DapWitness, does_not_prove, transcript_resolver

OK, FAILED, UNCHECKED = 0, 1, 3

#: What goes wrong on the way to a stop. An adapter that died, a request that
#: was never answered, and an argument this side could not make sense of.
TROUBLE = (AdapterError, ConnectionClosed, OSError, TimeoutError, ValueError)


def _witness(args: argparse.Namespace):
    """The log and transcript this run writes to, or nothing if none was asked
    for. A run with no `--log-dir` still works and leaves no receipt."""
    if args.log_dir is None:
        return None
    run_id = args.run_id or time.strftime("dap-%Y%m%d-%H%M%S")
    log = open_log(run_id, directory=args.log_dir)
    transcript = args.transcript
    if transcript is None and args.keep_bytes:
        transcript = Path(args.log_dir) / "frames.jsonl"
    return DapWitness(log, transcript=transcript)


def _policy(root: Path, args: argparse.Namespace):
    """What this client will do for the adapter. Refuse, unless told to allow.

    The allow is bounded by the root rather than by trust in the adapter. An
    adapter is a program the operator chose, and the command line it asks to run
    is one it composed at runtime from a configuration this side never read.
    """
    return AllowTerminal(root) if args.allow_terminal else DenyAll()


def _session_arguments(args: argparse.Namespace) -> dict:
    """The launch or attach body, and the breakpoints to set before running.

    `--launch-json` is merged last, so an adapter's own keys win over the ones
    built here. Adapters require keys no other adapter has heard of, and a
    command that could only send the ones it knew about would work against the
    one adapter it was written for.
    """
    if (args.program is None) == (args.attach_pid is None):
        raise ValueError("a session is launched with --program or attached "
                         "with --attach-pid, not both and not neither")
    extra = json.loads(args.launch_json) if args.launch_json else {}
    if not isinstance(extra, dict):
        raise ValueError("--launch-json carries a JSON object")
    if args.program is not None:
        body = {"program": str(args.program), "noDebug": False}
        key = "launch"
    else:
        body = {"processId": int(args.attach_pid)}
        key = "attach"
    return {key: dict(body, **extra),
            "breakpoints": breakpoints_from(args.breakpoints),
            "timeout": args.timeout}


def _unbound(session) -> list:
    """Every breakpoint the adapter did not bind, with the reason it gave.

    The count alone would not tell a reader which line the debugger will never
    stop on, and that is the line somebody is about to wait for.
    """
    return [{"source": source, "line": entry.get("line"),
             "message": str(entry.get("message", ""))}
            for source, placed in session.breakpoints.items()
            for entry in placed if not entry.get("verified")]


def _scopes_at(client: DapClient, frame_id: int, *, values: bool) -> dict:
    """The variables on one frame, as names or as names and values.

    Values are the debuggee's memory, so they are printed only when the caller
    asked for them. The record carries neither: the frame chain already binds
    the frames that carried the values, and a fold that copied them would be a
    second transcript wearing the clothes of a receipt.
    """
    collected: dict = {}
    for scope, entries in client.frame_variables(frame_id).items():
        collected[scope] = [
            f"{entry.get('name', '')} = {entry.get('value', '')}" if values
            else f"{entry.get('name', '')}  {entry.get('type', '')}".rstrip()
            for entry in entries]
    return collected


def _at_stop(client: DapClient, stop, args: argparse.Namespace) -> dict:
    """The stack at the stop, and the variables on its top frame."""
    stack = client.stack_trace(stop.thread_id, levels=args.stack_levels,
                               timeout=args.timeout)
    frames = stack["frames"]
    scopes = _scopes_at(client, frames[0]["id"], values=args.values) \
        if frames else {}
    return {"stack": stack, "scopes": scopes}


def _receipt(report: dict, witness, client: DapClient) -> None:
    """Put the record's own coordinates in the report, or say there is none."""
    if witness is None:
        report["log"] = None
        return
    witness.record_decisions(client.policy)
    report["log"] = str(witness.log.path)
    report["transcript"] = str(witness.transcript) if witness.transcript else None
    report["receipt"] = witness.record_session(client.session,
                                               adapter=report["adapter"])


def run(args: argparse.Namespace) -> int:
    witness = _witness(args)
    root = Path(args.root or Path.cwd()).resolve()
    client, error = None, None
    try:
        arguments = _session_arguments(args)
        client = DapClient.start(args.adapter, root=root,
                                 policy=_policy(root, args),
                                 observer=witness.observe_frame
                                 if witness else None)
        client.start_session(args.adapter_id, **arguments)
        stop = client.wait_for_stop(timeout=args.wait)
        report = _report(client, stop, args)
        if stop is not None and witness is not None:
            witness.record_stop(stop)
    except TROUBLE as exc:
        error = exc
    if error is not None:
        return _unreached(error, client, args)
    _receipt(report, witness, client)
    client.disconnect(timeout=args.timeout)
    client.close()
    print(as_json(report) if args.json else render_run(report))
    return OK if report["stop"] is not None else UNCHECKED


def _report(client: DapClient, stop, args: argparse.Namespace) -> dict:
    """What the session amounted to, in the shape both readers take."""
    verified, requested = client.session.verified_breakpoints()
    report = {"adapter": " ".join(args.adapter),
              "request": "attach" if args.attach_pid is not None else "launch",
              "capabilities": sorted(name for name, value
                                     in client.capabilities.items()
                                     if value is True),
              "requested": requested, "verified": verified,
              "unbound": _unbound(client.session),
              "terminated": client.session.terminated,
              "exit_code": client.session.settle_exit(),
              "stop": None, "stack": {"frames": [], "total": 0,
                                      "truncated": False},
              "scopes": {},
              "decisions": [{"method": d.method, "detail": d.detail,
                             "allowed": d.allowed, "reason": d.reason}
                            for d in client.policy.decisions],
              "does_not_prove": does_not_prove()}
    if stop is None:
        return report
    report["stop"] = {"reason": stop.reason, "thread_id": stop.thread_id,
                      "description": stop.description,
                      "hit_breakpoint_ids": list(stop.hit_breakpoint_ids)}
    return dict(report, **_at_stop(client, stop, args))


def _unreached(exc: Exception, client, args) -> int:
    """The session never ran. Say why, and hand back the adapter's own
    complaint, which is where an adapter that failed at startup puts it."""
    stderr = ""
    if client is not None:
        client.close()
        stderr = client.stderr_text()[-2000:]
    report = {"error": f"{type(exc).__name__}: {exc}", "stderr": stderr}
    print(as_json(report) if args.json else render_error(report))
    return FAILED if isinstance(exc, AdapterError) else UNCHECKED


def verify(args: argparse.Namespace) -> int:
    resolve = None
    if args.transcript is not None:
        try:
            resolve = transcript_resolver(args.transcript)
        except (OSError, ValueError, KeyError) as exc:
            print(f"the transcript could not be read: {exc}")
            return UNCHECKED
    result = verify_log(args.log, resolve=resolve)
    print(as_json(result) if args.json else render_verify(result))
    if result["verdict"] == MATCH:
        return OK
    return FAILED if result["verdict"] == TAMPERED else UNCHECKED


#: Which function answers for which subcommand. The parser names the
#: subcommand and stops there, so the flags stay readable without importing
#: anything that starts a process.
HANDLERS = {"run": run, "verify": verify}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser(__doc__.splitlines()[0])
    args = parser.parse_args(argv)
    if args.limits:
        print("\n".join(f"  - {limit}" for limit in does_not_prove()))
        return OK
    if not args.command:
        parser.print_help()
        return UNCHECKED
    return HANDLERS[args.command](args)


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
