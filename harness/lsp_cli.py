"""lsp_cli.py -- ask a language server about a file, and keep the record of it.

A language server knows what an editor knows: where a name is defined, what
refers to it, what the type is, what is wrong with the file. This command puts
that on the terminal and writes down every frame that crossed the wire, so the
answer can be rechecked later by someone who was not there.

Three subcommands.

`ask` starts the server, hands it the file, and asks one question at one
position:

    flywheel lsp ask --file harness/lsp_cli.py --line 40 --character 8 \
        --operation definition -- ruff server

`diagnostics` opens the file and reports what the server published about it:

    flywheel lsp diagnostics --file harness/lsp_cli.py --json -- ruff server

`verify` rechecks a run somebody else did, on a machine that never saw it:

    flywheel lsp verify --log runs/one/action-witness.jsonl \
        --transcript runs/one/frames.jsonl

Two details decide whether an answer is readable a week later, and both are on
the record. Positions are counted in the encoding the two sides negotiated, and
every answer is stamped with the document version it was asked at. An answer
that arrived after the file changed is reported as not current rather than
quietly presented as fresh.

Exit codes, because a harness branches on them:

    ask          0 the server answered
                 1 the server refused the request
                 3 nothing to check: it never started, it timed out, or it
                   answered with nothing

    diagnostics  0 the server published an empty set: it says the file is clean
                 1 the server published problems
                 3 the server published nothing in the time allowed, which is
                   unknown and is not the same as clean

    verify       0 MATCH, every record links and every byte reproduced
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
from .lsp_args import build_parser
from .lsp_client import LspClient, UnsupportedOperation
from .lsp_connection import ConnectionClosed, PeerError
from .lsp_pull import PULL, published_from_report
from .lsp_report import render_ask, render_diagnostics, render_verify
from .lsp_witness import LspWitness, does_not_prove, transcript_resolver

OK, FAILED, UNCHECKED = 0, 1, 3

#: What the fence is for. A server publishes diagnostics when it likes, and a
#: request it has to answer will not be answered before the notifications it
#: already queued. Asking anything, and ignoring the answer, is how a client
#: finds out that the server has finished with what it had to say so far.
FENCE = "hover"


def _witness(args: argparse.Namespace):
    """The log and transcript this run writes to, or nothing if none was asked
    for. A run with no `--log-dir` still works and leaves no receipt."""
    if args.log_dir is None:
        return None
    run_id = args.run_id or time.strftime("lsp-%Y%m%d-%H%M%S")
    log = open_log(run_id, directory=args.log_dir)
    transcript = args.transcript
    if transcript is None and args.keep_bytes:
        transcript = Path(args.log_dir) / "frames.jsonl"
    return LspWitness(log, transcript=transcript)


def _session(args: argparse.Namespace, witness):
    """Start the server and hand it the file. Returns (client, uri, error).

    The client comes back even when opening failed, and that is the point of the
    shape. It owns a child process that has to be stopped, and the reason it
    failed is usually on that child's error stream, which nothing else can read.
    """
    client = None
    try:
        root = args.root or Path.cwd()
        client = LspClient.start(
            args.server, root=root,
            observer=witness.observe_frame if witness else None)
        client.initialize(timeout=args.timeout)
        return client, client.open(args.file, args.language), None
    except (ConnectionClosed, OSError, PeerError, TimeoutError,
            ValueError) as exc:
        return client, "", exc


def _receipt(report: dict, witness, recorded: dict | None) -> None:
    """Put the record's own coordinates in the report, or say there is none."""
    if witness is None:
        report["log"] = None
        return
    report["log"] = str(witness.log.path)
    report["transcript"] = str(witness.transcript) if witness.transcript else None
    if recorded is not None:
        report["receipt"] = recorded


def ask(args: argparse.Namespace) -> int:
    witness = _witness(args)
    client, uri, error = _session(args, witness)
    try:
        if error is None:
            answer = client.ask_at(args.operation, uri, args.line,
                                   args.character, timeout=args.timeout,
                                   strict=args.strict, new_name=args.new_name,
                                   query=args.query)
    except (ConnectionClosed, LookupError, PeerError, TimeoutError,
            UnsupportedOperation, ValueError) as exc:
        error = exc
    if error is not None:
        return _unreached(error, client, args)
    report = {"operation": answer.operation, "method": answer.method,
              "uri": uri, "encoding": answer.encoding,
              "version": answer.stamp["version"], "current": answer.current,
              "server": client.summary(), "result": answer.result}
    _receipt(report, witness,
             witness.record_answer(answer) if witness else None)
    client.shutdown(timeout=args.timeout)
    client.close()
    print(json.dumps(report, indent=2) if args.json else render_ask(report))
    return OK if report["result"] else UNCHECKED


def diagnostics(args: argparse.Namespace) -> int:
    witness = _witness(args)
    client, uri, error = _session(args, witness)
    try:
        if error is None:
            published = _wait_for_diagnostics(client, uri, args)
    except (ConnectionClosed, LookupError, PeerError, TimeoutError,
            ValueError) as exc:
        error = exc
    if error is not None:
        return _unreached(error, client, args)
    report = {"uri": uri, "model": published.model,
              "version": published.version,
              "current": published.current, "n": len(published.items),
              "published": published.version is not None or bool(
                  published.items),
              "server": client.summary(), "diagnostics": published.items}
    _receipt(report, witness,
             witness.record_published(published) if witness else None)
    client.shutdown(timeout=args.timeout)
    client.close()
    print(json.dumps(report, indent=2) if args.json
          else render_diagnostics(report))
    if not report["published"]:
        return UNCHECKED
    return FAILED if report["n"] else OK


def _wait_for_diagnostics(client: LspClient, uri: str,
                          args: argparse.Namespace):
    """Get the set the way this particular server hands it out.

    A server that advertised a diagnostic provider is asked, because that is the
    model it declared and it may never push anything. One that advertised
    nothing is waited on, because pushing is the only way it speaks. Neither
    path turns silence into a clean file.
    """
    if client.supports(PULL):
        return _pulled(client, uri, args)
    return _pushed(client, uri, args)


def _pulled(client: LspClient, uri: str, args: argparse.Namespace):
    """Ask, and go on asking while a server that is still starting says nothing.

    A full report always comes back stamped, so the loop only turns for the
    answers that carry no knowledge, and it always asks once even at no wait.
    """
    deadline = time.monotonic() + args.wait
    while True:
        published = published_from_report(
            client.ask(PULL, uri, timeout=args.timeout))
        if published.version is not None or time.monotonic() >= deadline:
            return published
        time.sleep(0.05)


def _pushed(client: LspClient, uri: str, args: argparse.Namespace):
    """Fence, then wait out the clock for a set that may never come.

    The fence catches a server that publishes on open. The wait covers one that
    indexes first. A set nobody published reads as no version, and the caller is
    told so.
    """
    try:
        client.ask(FENCE, uri, line=0, character=0, timeout=args.timeout)
    except (PeerError, TimeoutError):
        pass                  # the fence is a clock, not a question worth an answer
    deadline = time.monotonic() + args.wait
    while time.monotonic() < deadline:
        published = client.diagnostics(uri)
        if published.version is not None or published.items:
            return published
        time.sleep(0.05)
    return client.diagnostics(uri)


def _unreached(exc: Exception, client, args) -> int:
    """The question never got asked. Say why, and hand back the server's own
    complaint, which is where a server that failed at startup puts it."""
    stderr = ""
    if client is not None:
        client.close()
        stderr = client.stderr_text()[-2000:]
    report = {"error": f"{type(exc).__name__}: {exc}", "stderr": stderr}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"the request did not run: {report['error']}")
        if stderr.strip():
            print(stderr.rstrip())
    return FAILED if isinstance(exc, (PeerError, UnsupportedOperation)) \
        else UNCHECKED


def verify(args: argparse.Namespace) -> int:
    resolve = None
    if args.transcript is not None:
        try:
            resolve = transcript_resolver(args.transcript)
        except (OSError, ValueError, KeyError) as exc:
            print(f"the transcript could not be read: {exc}")
            return UNCHECKED
    result = verify_log(args.log, resolve=resolve)
    print(json.dumps(result, indent=2) if args.json else render_verify(result))
    if result["verdict"] == MATCH:
        return OK
    return FAILED if result["verdict"] == TAMPERED else UNCHECKED


#: Which function answers for which subcommand. The parser names the
#: subcommand and stops there, so the flags stay readable without importing
#: anything that starts a process.
HANDLERS = {"ask": ask, "diagnostics": diagnostics, "verify": verify}


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
