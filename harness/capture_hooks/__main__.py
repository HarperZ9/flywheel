"""`python -m harness.capture_hooks <event> --client claude-code|codex`.

Mounted on a client's prompt and Stop hooks. It finds the home and the
gateway without trusting the environment, proves the listener before sending
anything, signs each request, and fails visibly: a Claude Code Stop hook exits
1 with one stderr line, every other shape exits 0 with a `systemMessage`.
Each failure leaves one metadata record in the spool. With
FLYWHEEL_CAPTURE=off it contacts no gateway, says so once per session and
counts the suppression.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import output, spool
from .client import CaptureFailure, open_channel, read_token
from .home import resolve_home
from .protocol import PING_PATH, SCAFFOLD_PATH

EVENTS = ("prompt", "stop")
CLIENTS = ("claude-code", "codex")
TIMEOUT = {"prompt": 10.0, "stop": 10.0}
MAX_EVENT = 16 * 1024 * 1024
_PROMPT_KEYS = ("prompt", "user_prompt", "message", "input")
_ANSWER_KEYS = ("last_assistant_message", "answer", "final_message", "response", "output")


class _Usage(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # never exit 2: a usage fault is reported, not raised
        raise _Usage(message)


def _parse(argv):
    parser = _Parser(prog="python -m harness.capture_hooks", add_help=False)
    parser.add_argument("event", choices=EVENTS)
    parser.add_argument("--client", choices=CLIENTS, required=True)
    parser.add_argument("--home", default=None)
    return parser.parse_args(argv)


def _text(event: dict, keys) -> str:
    for key in keys:
        value = event.get(key)
        if type(value) is str and value.strip():
            return value
    return ""


def _event(raw: bytes) -> dict:
    try:
        doc = json.loads(raw[:MAX_EVENT].decode("utf-8") or "{}")
    except (UnicodeError, ValueError):
        return {}
    return doc if type(doc) is dict else {}


def _suppressed(args, event, environ, cwd):
    home, refusal = resolve_home(args.home, environ, cwd)
    first = True
    if refusal not in ("HOME_IN_WORKTREE", "HOME_UNRESOLVED") and home is not None:
        try:
            first = spool.note_suppression(home, args.client, event.get("session_id"), cwd)
        except OSError:
            first = True
    notice = output.suppression_line(str(cwd)) if first else None
    return output.render(args.client, args.event, messages=[notice])


def _fail(args, event, home, code):
    spooled = False
    if home is not None and code not in ("HOME_IN_WORKTREE", "HOME_UNRESOLVED"):
        spooled = spool.write_failure(home, args.client, args.event, event.get("session_id"),
                                      event.get("prompt_id") or event.get("turn_id"), code)
    return output.render(args.client, args.event,
                         failure=output.failure_line(code, spooled))


def _act(args, event, home) -> tuple[dict, list[str]]:
    channel = open_channel(home, read_token(home), TIMEOUT[args.event])
    if args.event == "stop":
        channel.request("POST", SCAFFOLD_PATH, {"prompt": _text(event, _PROMPT_KEYS),
                                                "answer": _text(event, _ANSWER_KEYS)})
        return {}, []
    channel.request("GET", PING_PATH)
    count, since = spool.unacknowledged(home)
    return {}, ([output.unacked_line(count, since)] if count else [])


def run(argv, raw: bytes, environ, cwd) -> tuple[int, str, str]:
    try:
        args = _parse(argv)
    except _Usage:
        return 1, "", "flywheel capture: hook mount is invalid (USAGE). Run: flywheel traces doctor\n"
    event = _event(raw)
    if environ.get("FLYWHEEL_CAPTURE", "").strip().lower() == "off":
        return _suppressed(args, event, environ, cwd)
    home, refusal = resolve_home(args.home, environ, cwd)
    if refusal:
        return _fail(args, event, home, refusal)
    try:
        result, messages = _act(args, event, home)
    except CaptureFailure as failure:
        return _fail(args, event, home, failure.code)
    return output.render(args.client, args.event, messages=messages,
                         context=result.get("context"))


def main(argv=None) -> int:
    try:
        code, out, err = run(sys.argv[1:] if argv is None else argv,
                             sys.stdin.buffer.read(MAX_EVENT + 1), os.environ, os.getcwd())
    except Exception as exc:  # the hook must never hide a failure or exit 2
        code, out, err = 1, "", f"flywheel capture: hook error ({type(exc).__name__}). " \
                                f"{output.DOCTOR}\n"
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
