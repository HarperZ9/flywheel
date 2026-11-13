"""One builder for the peer-sessions responses the desktop surface reads.

The Dart view is written against field names this module produced. A route
gate that counts paths cannot see a renamed field, so the shape of those three
responses is built here once, frozen into the committed Dart fixture, and
compared against a fresh build by test_peer_sessions_ui_fixture.py.

Values are made deterministic on purpose. File times are stamped, the clock is
fixed, and the temporary root is redacted, so the committed fixture carries no
path from the machine that generated it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from harness import peer_sessions_route as route
from harness.peer_mailbox import write_message
from tests.peer_session_fixtures import write_claude, write_codex

FIXTURE_CLOCK = "2026-09-11T00:00:00Z"
CLOCK_EPOCH = 1789084800  # 2026-09-11T00:00:00Z, the instant FIXTURE_CLOCK names
CODEX_MTIME = CLOCK_EPOCH - 120  # two minutes back, so the age reads in minutes
CLAUDE_MTIME = CLOCK_EPOCH - 172800  # two days back, so the age reads in hours
SENT = "20260910T185324Z"
BODY = "status: the observer slice is written and its gates are green\n"
ROOT_TOKEN = "<fixture-root>"
PATHS = (route.PREFIX, route.PREFIX + "/journey", route.PREFIX + "/mailbox")


def _stamp(path: Path, when: int) -> None:
    os.utime(path, (when, when))


def build_bodies(home: Path) -> dict:
    """Serve every path the view reads, from one transcript layout."""
    _stamp(write_codex(home), CODEX_MTIME)
    _stamp(write_claude(home), CLAUDE_MTIME)
    box = home / "state" / route.MAILBOX_DIRNAME
    box.mkdir(parents=True)
    write_message(box, sender="codex.root", to="claude.fable", body=BODY, sent_utc=SENT)
    out = {}
    for path in PATHS:
        body, code = route.handle_peer_sessions_get(
            path, "", state_root=home / "state", clock=lambda: FIXTURE_CLOCK, home=home)
        if code != 200:
            raise AssertionError(f"{path} answered {code}, not 200")
        out[path] = body
    return redact(out, home)


def redact(value, home: Path):
    """Replace the generating machine's temporary root with a fixed token."""
    roots = (str(home), str(home).replace("\\", "/"), str(home).replace("/", "\\"))
    if type(value) is dict:
        return {k: redact(v, home) for k, v in value.items()}
    if type(value) is list:
        return [redact(item, home) for item in value]
    if type(value) is str:
        for root in roots:
            value = value.replace(root, ROOT_TOKEN)
    return value


def skeleton(value):
    """The shape of a response with its values removed.

    Keys, nesting, list length and leaf type survive; digests, paths and
    numbers do not. That is the part a Dart field read depends on, and the
    part two runs on different machines can agree about.
    """
    if type(value) is dict:
        return {k: skeleton(value[k]) for k in sorted(value)}
    if type(value) is list:
        return [skeleton(item) for item in value]
    return type(value).__name__


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
