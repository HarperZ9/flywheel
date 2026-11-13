"""Command line for the hosted peer-session observers.

    python -m harness.peer_session_cli list      [--home DIR] [--limit N]
    python -m harness.peer_session_cli observe   PATH [--harness auto|claude_code|codex]
    python -m harness.peer_session_cli registry  [--home DIR] [--limit N] [--out FILE]
    python -m harness.peer_session_cli journey   [--home DIR] [--limit N] [--out FILE]
    python -m harness.peer_session_cli mailbox list DIR
    python -m harness.peer_session_cli mailbox send DIR --from ID --to ID --body-file FILE
    python -m harness.peer_session_cli mailbox verify FILE

Exit codes: 0 clean, 1 findings (observer issues, observe failures, DRIFT, a
mail file whose name disagrees with its header, or malformed mail), 2 usage or
rejected input. Output is JSON with sorted keys. Nothing here posts to a
network or writes outside --out and the mailbox.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import re
import sys

from .peer_mailbox import (MAX_MESSAGE_BYTES, MailboxError, list_messages, read_message,
                           write_message)
from .peer_session_io import (DEFAULT_HEAD_BYTES, DEFAULT_TAIL_BYTES, MAX_WINDOW_BYTES,
                              SourceRejected, is_link)
from .peer_session_journey import registry_to_events
from .peer_session_registry import (DEFAULT_LIMIT, build_registry, default_roots, discover,
                                    observe_entry)
from .peer_session_types import HARNESS_CLAUDE, HARNESS_CODEX, HARNESSES

CLAUDE_NAME = re.compile(r"[0-9a-f-]{36}\.jsonl\Z")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_out(path: str, data: bytes) -> None:
    """Write the output file without writing through a link.

    A symbolic link or junction planted at the --out path would redirect this
    write to any file the operator can write. The path is refused when it is a
    link, a dangling link, or an existing non-regular file. O_NOFOLLOW does not
    exist on Windows, so this is a check taken before the open, not a guarantee
    against a path swapped in that same instant.
    """
    p = Path(path)
    if p.is_symlink() or (p.exists() and (is_link(p) or not p.is_file())):
        raise SourceRejected("--out must be a regular file that is not a link")
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def _emit(obj, out, path: str | None) -> None:
    text = json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True)
    if path:
        data = (text + "\n").encode("utf-8")
        _write_out(path, data)
        out.write(json.dumps({"written": path, "bytes": len(data)}, sort_keys=True) + "\n")
    else:
        out.write(text + "\n")


def _count(value: str) -> int:
    """An argparse type for a count. A negative limit is a usage error here, so it
    can never read as "no limit" in one subcommand and a rejection in another."""
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer") from None
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return number


def _error(exc: Exception) -> dict:
    """Error output without an operating-system message.

    An OSError's text repeats the path it failed on and a localized system
    string, so only the errno name is reported. The two error types this package
    raises itself carry fixed text written in this repository, so those print in
    full.
    """
    if isinstance(exc, OSError):
        return {"error": type(exc).__name__, "errno": errno.errorcode.get(exc.errno, "unknown")}
    if isinstance(exc, (MailboxError, SourceRejected)):
        return {"error": type(exc).__name__, "detail": str(exc)}
    return {"error": type(exc).__name__}


def _guess_harness(path: str) -> str | None:
    name = Path(path).name
    if name.startswith("rollout-") and name.endswith(".jsonl"):
        return HARNESS_CODEX
    if CLAUDE_NAME.match(name):
        return HARNESS_CLAUDE
    return None


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="peer-sessions", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("list", "registry", "journey"):
        s = sub.add_parser(name)
        s.add_argument("--home", default=None, help="home directory holding .claude and .codex")
        s.add_argument("--limit", type=_count, default=DEFAULT_LIMIT)
        if name != "list":
            s.add_argument("--out", default=None)
            s.add_argument("--head-bytes", type=int, default=DEFAULT_HEAD_BYTES)
            s.add_argument("--tail-bytes", type=int, default=DEFAULT_TAIL_BYTES)
    o = sub.add_parser("observe")
    o.add_argument("path")
    o.add_argument("--harness", choices=("auto",) + HARNESSES, default="auto")
    o.add_argument("--head-bytes", type=int, default=DEFAULT_HEAD_BYTES)
    o.add_argument("--tail-bytes", type=int, default=DEFAULT_TAIL_BYTES)
    o.add_argument("--out", default=None)
    m = sub.add_parser("mailbox")
    ms = m.add_subparsers(dest="mail_command", required=True)
    ms.add_parser("list").add_argument("mailbox")
    send = ms.add_parser("send")
    send.add_argument("mailbox")
    send.add_argument("--from", dest="sender", required=True)
    send.add_argument("--to", required=True)
    send.add_argument("--body-file", required=True)
    send.add_argument("--in-reply-to", default=None)
    ms.add_parser("verify").add_argument("file")
    return p


def _roots(home):
    return default_roots(home) if home else default_roots()


def _cmd_list(args, out, now) -> int:
    entries = discover(_roots(args.home))
    shown = entries[:args.limit]
    _emit({"discovered": len(entries), "shown": len(shown), "observed_at": now(),
           "entries": shown}, out, None)
    return 0


def _cmd_observe(args, out, now) -> int:
    harness = args.harness if args.harness != "auto" else _guess_harness(args.path)
    if harness is None:
        out.write(json.dumps({"error": "harness_not_inferable", "path": args.path}) + "\n")
        return 2
    entry = {"path": args.path, "harness": harness}
    record = observe_entry(entry, observed_at=now(), head_bytes=args.head_bytes,
                           tail_bytes=args.tail_bytes)
    _emit(record, out, args.out)
    if not record.get("observed"):
        return 2
    return 1 if record.get("issues") else 0


def _registry(args, now) -> dict:
    """Build a registry after checking the window sizes once.

    An out-of-range window is rejected here rather than inside every observer,
    so a bad argument exits 2 as a rejected input instead of producing a
    registry in which every single session failed to be observed.
    """
    for name, value in (("head-bytes", args.head_bytes), ("tail-bytes", args.tail_bytes)):
        if type(value) is not int or value <= 0 or value > MAX_WINDOW_BYTES:
            raise SourceRejected(f"--{name} out of range")
    return build_registry(discover(_roots(args.home)), observed_at=now(), limit=args.limit,
                          head_bytes=args.head_bytes, tail_bytes=args.tail_bytes)


def _registry_flagged(registry: dict) -> bool:
    return bool(registry["observe_failures"]
                or any(s.get("issues") for s in registry["sessions"]))


def _cmd_registry(args, out, now) -> int:
    registry = _registry(args, now)
    _emit(registry, out, args.out)
    return 1 if _registry_flagged(registry) else 0


def _cmd_journey(args, out, now) -> int:
    """The journey carries the findings the registry carries, so it exits the same
    way. A session with issues is a finding even when its read succeeded."""
    registry = _registry(args, now)
    result = registry_to_events(registry, occurred_at=now())
    _emit(result, out, args.out)
    return 1 if _registry_flagged(registry) else 0


def _mail_clean(row: dict) -> bool:
    """Clean means the body hash matched and the file name agrees with the header.

    A file renamed to claim a different sender is a finding even though its body
    still hashes correctly, so the name check shares the exit code with DRIFT.
    """
    return row.get("receipt_state") == "MATCH" and row.get("file_name_consistent") is not False


def _body(path: str) -> str:
    """Read a message body, bounded and link-free, before anything is written."""
    p = Path(path)
    if is_link(p) or not p.is_file():
        raise MailboxError("--body-file must be a regular file that is not a link")
    if p.stat().st_size > MAX_MESSAGE_BYTES:
        raise MailboxError("--body-file is larger than a message may be")
    return p.read_text(encoding="utf-8")


def _cmd_mailbox(args, out, now) -> int:
    if args.mail_command == "list":
        rows = list_messages(args.mailbox)
        _emit({"mailbox": args.mailbox, "count": len(rows), "messages": rows}, out, None)
        return 0 if all(_mail_clean(r) for r in rows) else 1
    if args.mail_command == "verify":
        record = read_message(args.file)
        record.pop("body", None)
        _emit(record, out, None)
        return 0 if _mail_clean(record) else 1
    body = _body(args.body_file)
    record = write_message(args.mailbox, sender=args.sender, to=args.to, body=body,
                           sent_utc=now(), in_reply_to=args.in_reply_to)
    record.pop("body", None)
    _emit(record, out, None)
    return 0


COMMANDS = {"list": _cmd_list, "observe": _cmd_observe, "registry": _cmd_registry,
            "journey": _cmd_journey, "mailbox": _cmd_mailbox}


def main(argv=None, *, out=None, clock=None) -> int:
    out = out or sys.stdout
    now = clock or _now
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    try:
        return COMMANDS[args.command](args, out, now)
    except (MailboxError, SourceRejected, ValueError, OSError) as exc:
        out.write(json.dumps(_error(exc), sort_keys=True) + "\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
