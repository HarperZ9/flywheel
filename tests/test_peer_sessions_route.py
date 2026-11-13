"""The peer-sessions HTTP route: what it serves, and what it refuses to serve.

The observers themselves are tested in the peer_session_* tests. What is at
stake here is the seam: that the route hands back the observation unaltered,
that a caller cannot steer it at a directory or a window of their choosing,
that a message body never crosses it, and that its prefix is held privately.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from harness import peer_sessions_route as route
from harness.gateway_custody import is_private
from harness.peer_mailbox import write_message
from harness.peer_session_types import MAILBOX_SCHEMA, REGISTRY_SCHEMA
from tests.peer_session_fixtures import (CLAUDE_SESSION, CODEX_THREAD, assert_no_canary,
                                         write_claude, write_codex)

NOW = "2026-09-11T00:00:00Z"
SENT = "20260910T185324Z"


def clock() -> str:
    return NOW


@pytest.fixture
def home(tmp_path):
    write_codex(tmp_path)
    write_claude(tmp_path)
    return tmp_path


def get(path, qs="", *, home=None, state_root=None):
    return route.handle_peer_sessions_get(path, qs, state_root=state_root or (home or "."),
                                          clock=clock, home=home)


def test_the_registry_route_serves_the_observation_whole_and_still_hashed(home):
    """The digest is taken over the registry body before it is added. Anything the
    route appended to that body would break the recomputation below, which is the
    point of checking it here rather than trusting the response to be untouched."""
    body, code = get(route.PREFIX, home=home)
    assert code == 200 and body["schema"] == REGISTRY_SCHEMA
    assert body["observed_at"] == NOW and body["discovered"] == 2
    assert body["discovered_by_harness"] == {"claude_code": 1, "codex": 1}
    assert body["observe_failures"] == 0 and len(body["sessions"]) == 2
    rest = {k: v for k, v in body.items() if k != "registry_sha256"}
    canonical = json.dumps(rest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert body["registry_sha256"] == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert_no_canary(body)


def test_the_windows_are_fixed_by_the_route_not_named_by_the_caller(home):
    """A caller who could name the window could ask one GET to read gigabytes. The
    query names are accepted as ordinary unknown keys and change nothing."""
    plain, _ = get(route.PREFIX, home=home)
    steered, code = get(route.PREFIX, "head-bytes=67108864&tail_bytes=67108864&home=C:/", home=home)
    assert code == 200
    for session in plain["sessions"] + steered["sessions"]:
        assert session["windows"]["head"]["length"] <= route.HEAD_BYTES
        assert session["windows"]["tail"]["length"] <= route.TAIL_BYTES
    assert ([s["source"]["path"] for s in steered["sessions"]]
            == [s["source"]["path"] for s in plain["sessions"]])


def test_the_journey_route_ties_its_events_to_the_registry_it_came_from(home):
    """Events and registry are separate requests, so an event set with no digest
    beside it cannot be matched back to the observation that produced it."""
    registry, _ = get(route.PREFIX, home=home)
    body, code = get(route.PREFIX + "/journey", home=home)
    assert code == 200 and body["schema"] == route.JOURNEY_SCHEMA
    assert body["event_count"] == 3 and len(body["events"]) == 3
    assert body["registry_sha256"] == registry["registry_sha256"]
    assert body["observed_at"] == NOW and body["discovered"] == 2
    assert body["publication_state"] == "not_approved_for_publication"
    assert body["scope"] == registry["scope"]
    refs = [f["session_ref"] for e in body["events"][1:] for f in e["payload"]["facts"]]
    assert sorted(refs) == sorted([CODEX_THREAD, CLAUDE_SESSION])
    assert_no_canary(body)


def test_a_limit_of_zero_observes_nothing_and_still_counts_what_is_there(home):
    body, code = get(route.PREFIX, "limit=0", home=home)
    assert code == 200 and body["sessions"] == [] and body["discovered"] == 2
    assert body["unobserved_count"] == 2 and body["limit"] == 0
    one, _ = get(route.PREFIX, "limit=1", home=home)
    assert len(one["sessions"]) == 1 and one["unobserved_count"] == 1


@pytest.mark.parametrize("bad", ["-1", "1.5", "  2", "+2", "two", "", "1_0"])
def test_a_limit_that_is_not_a_whole_number_is_refused(home, bad):
    """int() would accept a sign, surrounding space, an underscore and non-ASCII
    digits, which makes several spellings of one request. Only one is accepted."""
    body, code = get(route.PREFIX, "limit=" + bad, home=home)
    assert code == 422 and body["error"]["code"] == "INVALID_REQUEST"
    assert "whole number" in body["error"]["message"]


def test_a_limit_past_the_ceiling_is_refused_rather_than_quietly_clamped(home):
    """Clamping would answer a different question than the one asked, and the
    caller would have no way to tell that it had been narrowed."""
    body, code = get(route.PREFIX, "limit=%d" % (route.MAX_LIMIT + 1), home=home)
    assert code == 422 and str(route.MAX_LIMIT) in body["error"]["message"]
    ok, code = get(route.PREFIX, "limit=%d" % route.MAX_LIMIT, home=home)
    assert code == 200 and ok["limit"] == route.MAX_LIMIT


def test_the_mailbox_route_reports_the_receipt_and_never_the_body(tmp_path):
    """A mailbox file is written by a peer. Its header and its hash are what this
    route is for; the body is the part it has no reason to hand to a browser."""
    state = tmp_path / "state"
    box = state / route.MAILBOX_DIRNAME
    box.mkdir(parents=True)
    secret = "peer body text that must not cross the route"
    record = write_message(box, sender="codex.root", to="claude.fable", body=secret,
                           sent_utc=SENT)
    body, code = get(route.PREFIX + "/mailbox", state_root=state)
    assert code == 200 and body["schema"] == MAILBOX_SCHEMA
    assert body["mailbox_present"] is True and body["read_at"] == NOW
    assert body["listed"] == 1 and body["matched"] == 1 and body["skipped_unnamed"] == 0
    row = body["messages"][0]
    assert row["from"] == "codex.root" and row["to"] == "claude.fable"
    assert row["receipt_state"] == "MATCH" and row["file_name_consistent"] is True
    assert row["body_sha256_computed"] == record["body_sha256_declared"]
    assert row["body_chars"] == record["body_chars"] == len(secret) + 1
    assert "body" not in row and secret not in json.dumps(body)


def test_a_mailbox_nobody_has_written_to_reads_as_empty_not_as_an_error(tmp_path):
    """An absent directory is the ordinary state before the first message. Serving
    500 there would report a fault where there is none."""
    body, code = get(route.PREFIX + "/mailbox", state_root=tmp_path / "state")
    assert code == 200 and body["mailbox_present"] is False
    assert body["messages"] == [] and body["listed"] == 0 and body["matched"] == 0
    assert route.MAILBOX_DIRNAME in body["mailbox"]
    assert "no file was present" in body["scope"]


def test_a_mailbox_path_that_is_a_file_is_not_read_as_a_mailbox(tmp_path):
    """Only a directory is a mailbox. A regular file at that path is a different
    object, and reading it as one would be reading whatever put it there."""
    state = tmp_path / "state"
    state.mkdir()
    (state / route.MAILBOX_DIRNAME).write_text("not a mailbox", encoding="utf-8")
    body, code = get(route.PREFIX + "/mailbox", state_root=state)
    assert code == 200 and body["mailbox_present"] is False and body["messages"] == []


def test_an_unknown_path_under_the_prefix_is_a_404_in_the_error_envelope(home):
    """The gateway dispatches the whole prefix here, so every path under it that
    this module does not serve has to end somewhere. It ends as a 404."""
    for path in (route.PREFIX + "/mail", route.PREFIX + "/journey/x", route.PREFIX + "x"):
        body, code = get(path, home=home)
        assert code == 404 and body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["message"] == "unknown peer-sessions route"


def test_every_path_this_module_serves_is_held_under_private_custody():
    """Local transcript paths and a peer's correspondence are the operator's. The
    auth check and the generated API document both read the same list."""
    for path in (route.PREFIX, route.PREFIX + "/journey", route.PREFIX + "/mailbox"):
        assert is_private(path), path


def test_the_gateway_dispatches_the_prefix_and_describes_it():
    """A route the gateway serves with no description fails the discovery gate.
    Checked here too, so the failure names this route rather than a count."""
    from harness.route_inventory import gateway_routes
    found = [r for r in gateway_routes() if r.path == route.PREFIX]
    assert len(found) == 1 and found[0].match == "prefix"
    assert found[0].methods == ("GET",) and found[0].description
