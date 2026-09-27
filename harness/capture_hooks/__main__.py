"""`python -m harness.capture_hooks <event> --client claude-code|codex`.

Mounted on a client's prompt and Stop hooks. It finds the home and the
gateway without trusting the environment, proves the listener before sending
anything, signs each request, and fails visibly: a Claude Code Stop hook exits
1 with one stderr line, every other shape exits 0 with a `systemMessage`.
Each failure leaves one metadata record in the spool. An event over 16 MiB
or one that is not a JSON object is EVENT_UNREADABLE, and a prompt event
with no prompt field is PROMPT_MISSING: the hook never commits to an empty
prompt it did not read. With FLYWHEEL_CAPTURE=off it contacts no gateway,
says so once per session and counts the suppression.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys

from . import output, spool
from .client import CaptureFailure, open_channel, read_token
from .home import resolve_home
from .protocol import FREEZE_PATH, PROMPT_PATH, SESSION_PATH, STOP_PATH, commitment

EVENTS = ("prompt", "stop", "session-end")
CLIENTS = ("claude-code", "codex")
TIMEOUT = {"prompt": 10.0, "stop": 10.0, "session-end": 1.0}
MAX_EVENT = 16 * 1024 * 1024
_PROMPT_KEYS = ("prompt", "user_prompt", "message", "input")
_URL = re.compile(r"https?://[^\s)\]>\"']+")
_ANSWER_KEYS = ("answer", "final_message", "response", "output")


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


def _event(raw: bytes) -> tuple[dict, str | None]:
    """(event, None), or ({}, EVENT_UNREADABLE) for an oversized or malformed one."""
    if len(raw) > MAX_EVENT:
        return {}, "EVENT_UNREADABLE"
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        return {}, "EVENT_UNREADABLE"
    return (doc, None) if type(doc) is dict else ({}, "EVENT_UNREADABLE")


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
                         failure=output.failure_line(code, spooled, event=args.event))


def _turn_payload(args, event, kind: str, text, content_on: bool) -> dict:
    """Commitments and salts by default; the text only when content capture
    is in effect at the gateway."""
    payload = {"client": args.client, "session_id": spool.clean_session(event.get("session_id")),
               "prompt_key": spool.clean_key(event.get("prompt_id") or event.get("turn_id"))}
    if kind == "answer":
        payload["stop_hook_active"] = event.get("stop_hook_active") is True
    if text is None:
        return payload
    if content_on:
        return {**payload, "text": text}
    salt = os.urandom(32)
    return {**payload, "commitment": commitment(kind, salt, text),
            "salt": base64.b64encode(salt).decode("ascii")}


def _act(args, event, home) -> tuple[dict, list[str]]:
    channel = open_channel(home, read_token(home), TIMEOUT[args.event])
    content_on = channel.effective.get("content") == "on"
    messages = []
    if channel.effective.get("pending_change"):
        messages.append(output.PENDING_SETTINGS)
    if channel.effective.get("retention_pending"):
        messages.append(output.PENDING_RETENTION)
    if args.event == "session-end":
        if channel.effective.get("archive_transcripts") == "on":
            reason = event.get("reason") if type(event.get("reason")) is str else ""
            channel.request("POST", SESSION_PATH, {
                "client": args.client, "session_id": spool.clean_session(event.get("session_id")),
                "reason": reason[:64]})
        return {}, []
    if args.event == "stop":
        answer = event.get("last_assistant_message")
        answer = answer if type(answer) is str else (_text(event, _ANSWER_KEYS) or None)
        channel.request("POST", STOP_PATH, _turn_payload(args, event, "answer", answer,
                                                         content_on))
        return {}, messages
    if not any(type(event.get(key)) is str for key in _PROMPT_KEYS):
        raise CaptureFailure("PROMPT_MISSING")
    prompt = _text(event, _PROMPT_KEYS)
    payload = _turn_payload(args, event, "prompt", prompt, content_on)
    channel.request("POST", PROMPT_PATH, payload)
    result = {}
    urls = list(dict.fromkeys(u.rstrip(".,;") for u in _URL.findall(prompt)))[:5]
    if channel.effective.get("freeze_urls") == "on" and urls:
        keys = ("client", "session_id", "prompt_key")
        manifest = channel.request("POST", FREEZE_PATH,
                                   {**{k: payload[k] for k in keys}, "urls": urls})
        result["context"] = output.freeze_context(manifest)
    count, since = spool.unacknowledged(home)
    return result, messages + ([output.unacked_line(count, since)] if count else [])


def run(argv, raw: bytes, environ, cwd) -> tuple[int, str, str]:
    try:
        args = _parse(argv)
    except _Usage:
        return 1, "", "flywheel capture: hook mount is invalid (USAGE). Run: flywheel traces doctor\n"
    event, unreadable = _event(raw)
    if environ.get("FLYWHEEL_CAPTURE", "").strip().lower() == "off":
        return _suppressed(args, event, environ, cwd)
    home, refusal = resolve_home(args.home, environ, cwd)
    if refusal or unreadable:
        return _fail(args, event, home, refusal or unreadable)
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
