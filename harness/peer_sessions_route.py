"""peer_sessions_route.py -- the local peer sessions, served read only.

GET /api/peer-sessions           the registry of discovered transcript files
GET /api/peer-sessions/journey   that same registry, as journey events
GET /api/peer-sessions/mailbox   the file mailbox, headers and hashes only

What this serves is an observation of files on the operator's own disk: the
transcripts Claude Code and Codex write while they run, and the file mailbox
this harness uses to leave them notes. It starts no process, attaches to no
session, and posts nothing anywhere. A record here says a file was present
and what its bytes hashed to. That is not a claim that a session is running,
and every response carries the sentence that says so.

Three things are deliberately not parameters. The home directory is not read
from the query string, so a caller cannot aim the observers at a directory of
their choosing. The read windows are fixed below rather than accepted from a
caller, so one request cannot ask the gateway to read gigabytes. Message
bodies are never returned, because the body is the part of a peer's file this
route has no reason to hand to a browser.

The prefix sits under private custody in `harness/gateway_custody.py`. Local
session paths and peer correspondence belong to the operator, not to whoever
reached the port.
"""
from __future__ import annotations

import errno
from pathlib import Path
import urllib.parse

from .evidence_public import TransportError, error_response
from .peer_mailbox import MailboxError, listing
from .peer_session_io import SourceRejected
from .peer_session_journey import registry_to_events
from .peer_session_registry import build_registry, default_roots, discover
from .peer_session_types import MAILBOX_SCHEMA, PUBLICATION_STATE

PREFIX = "/api/peer-sessions"
JOURNEY_SCHEMA = "flywheel.hosted-peer-session-journey/v1"
#: The mailbox lives beside the other state this gateway owns, so a peer
#: writing to it needs no path from here and no access to anything else.
MAILBOX_DIRNAME = "peer-mailbox"
#: One GET reads every observed transcript at its head and at its tail. These
#: windows are smaller than the command line's for that reason, and each
#: session reports the window it was read through, so a short read is visible
#: in the record rather than silently changing what a field means.
HEAD_BYTES = 65_536
TAIL_BYTES = 262_144
DEFAULT_LIMIT = 12
MAX_LIMIT = 48
DEFAULT_MAIL_LIMIT = 64
MAX_MAIL_LIMIT = 256
DIGITS = frozenset("0123456789")


def _query(qs: str | None) -> dict:
    return urllib.parse.parse_qs(qs or "", keep_blank_values=True)


def _count(query: dict, key: str, default: int, ceiling: int) -> int:
    """A bounded non-negative count from the query string.

    `int()` accepts a leading sign, surrounding whitespace and non-ASCII
    digits, any of which would make two spellings of one request. The
    characters are checked first, so the only accepted spelling is the one a
    caller would write.
    """
    values = query.get(key)
    if not values:
        return default
    raw = values[-1]
    if not raw or not DIGITS.issuperset(raw):
        raise TransportError("INVALID_REQUEST", f"{key} must be a whole number", 422)
    number = int(raw)
    if number > ceiling:
        raise TransportError("INVALID_REQUEST", f"{key} may not exceed {ceiling}", 422)
    return number


def _now(clock) -> str:
    """The read time, taken from the gateway's clock when it passed one."""
    if clock is None:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return clock()


def _registry(query: dict, *, home, clock) -> dict:
    return build_registry(discover(default_roots(home)), observed_at=_now(clock),
                          limit=_count(query, "limit", DEFAULT_LIMIT, MAX_LIMIT),
                          head_bytes=HEAD_BYTES, tail_bytes=TAIL_BYTES)


def _journey(query: dict, *, home, clock) -> dict:
    """The registry as journey events, with the registry digest beside them.

    The digest is what ties the events to the observation they came from. A
    reader who has only the events cannot otherwise tell which registry they
    were derived from, and the two are served by separate requests.
    """
    registry = _registry(query, home=home, clock=clock)
    result = registry_to_events(registry, occurred_at=registry["observed_at"])
    return {"schema": JOURNEY_SCHEMA, **result, "observed_at": registry["observed_at"],
            "registry_sha256": registry["registry_sha256"],
            "discovered": registry["discovered"],
            "observe_failures": registry["observe_failures"],
            "publication_state": PUBLICATION_STATE,
            "does_not_prove": registry["does_not_prove"]}


def _empty_mailbox(box: Path, limit: int) -> dict:
    """The shape a listing has, for a mailbox nobody has written to yet.

    An absent directory is the ordinary state before the first message, so it
    reads as an empty mailbox rather than as an error. `mailbox_present` is
    what separates that from a directory holding no messages.
    """
    return {"schema": MAILBOX_SCHEMA, "mailbox": str(box), "mailbox_present": False,
            "messages": [], "listed": 0, "matched": 0, "limit": limit,
            "omitted_over_limit": 0, "skipped_unnamed": 0,
            "does_not_prove": "An absent mailbox proves no file was present at read time; it "
                              "does not prove no peer wrote one elsewhere."}


def _mailbox(query: dict, *, state_root, clock) -> dict:
    box = Path(state_root) / MAILBOX_DIRNAME
    limit = _count(query, "limit", DEFAULT_MAIL_LIMIT, MAX_MAIL_LIMIT)
    if box.is_symlink() or not box.is_dir():
        return {**_empty_mailbox(box, limit), "read_at": _now(clock)}
    rows = listing(box, include_body=False, limit=limit)
    return {**rows, "mailbox_present": True, "read_at": _now(clock)}


def handle_peer_sessions_get(path: str, qs: str = "", *, state_root, clock=None,
                             home=None) -> tuple[dict, int]:
    """Serve one read-only peer-session route. Returns (body, status)."""
    try:
        query = _query(qs)
        if path == PREFIX:
            return _registry(query, home=home, clock=clock), 200
        if path == PREFIX + "/journey":
            return _journey(query, home=home, clock=clock), 200
        if path == PREFIX + "/mailbox":
            return _mailbox(query, state_root=state_root, clock=clock), 200
        raise TransportError("NOT_FOUND", "unknown peer-sessions route", 404)
    except TransportError as exc:
        return error_response(exc)
    except OSError as exc:
        # An OSError's text repeats the path it failed on and a localized
        # system string. Only the errno name crosses the boundary.
        name = errno.errorcode.get(exc.errno, "unknown")
        return error_response(TransportError("SOURCE_UNREADABLE",
                                             f"the source could not be read ({name})", 503))
    except (MailboxError, SourceRejected, ValueError) as exc:
        return error_response(TransportError("INVALID_REQUEST", str(exc), 422))


__all__ = ["DEFAULT_LIMIT", "MAILBOX_DIRNAME", "MAX_LIMIT", "PREFIX",
           "handle_peer_sessions_get"]
