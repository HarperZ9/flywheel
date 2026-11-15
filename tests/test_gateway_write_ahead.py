"""Write-ahead accounting: a call is in the ledger before it is made.

Fifth review round of 2.0.0, the lead's ruling 1. Before it, the ledger entry
of a call was written after the provider answered, so a gateway process that
was killed in between left a billed call with no entry, and a call in flight
when the disk filled left none either (finding R4).

Now `endpoint_call_started` is appended and committed to the disk before the
request leaves, and the end entry names it. These tests show, on the home's
on-disk ledger:

  order      the started entry is written and committed before the upstream is
             contacted, on every model interface, plain and streamed;
  kill       a real process killed at each point around the two commits leaves
             exactly what the rule says: no provider request without a started
             entry on disk, and an unsettled call wherever a request could
             have left without its end entry;
  refuse     a started entry that cannot be written refuses the call with 503
             and nothing is sent.

tests/test_gateway_unsettled_calls.py has what happens to an unsettled call
afterwards: the report, the key's budget and `settle`. No provider is called.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from harness import gateway_ledger, gateway_ledger_cli
from tests import gateway_messages_support as support
from tests.gateway_crash_child import DIED, POINTS
from tests.gateway_disk_support import (  # noqa: F401  (fixtures and helpers)
    gateway_on_disk, home, kinds, late)
from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    BODIES, keyed, post, served, stream_bytes, turn2)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release

ROOT = Path(__file__).resolve().parents[1]
STARTED = "endpoint_call_started"


def _watch(monkeypatch) -> list:
    """Record, in order: each ledger line written (its kind), each commit, each contact."""
    import json

    from harness import endpoints_http, endpoints_stream, gateway_ledger_health as health
    seen, real_put, real_fsync = [], health._put, os.fsync

    def put(file, data):
        seen.append(("write", json.loads(data)["kind"]))
        return real_put(file, data)

    def fsync(fd):
        seen.append(("commit",))
        return real_fsync(fd)

    def watched(real):
        def guard(transport, *args, **kwargs):
            seen.append(("contact",))
            return real(transport, *args, **kwargs)
        return guard
    monkeypatch.setattr(health, "_put", put)
    monkeypatch.setattr(health.os, "fsync", fsync)
    monkeypatch.setattr(endpoints_http, "_guard", watched(endpoints_http._guard))
    monkeypatch.setattr(endpoints_stream, "_guard", watched(endpoints_stream._guard))
    return seen


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("path", ["/v1/messages", "/v1/responses"])
def test_the_started_entry_is_committed_before_the_upstream_is_contacted(
        keyed, served, monkeypatch, home, path, stream):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    answer = (support.stream_answer(stream_bytes("openai", "turn2")) if stream else turn2(1)[0])
    url, upstream, ledger, _disk = gateway_on_disk(monkeypatch, served, [answer], home)
    seen = _watch(monkeypatch)
    assert post(url, path, raw, {**BODIES[path], "stream": stream})[0] == 200
    assert seen == [("write", STARTED), ("commit",), ("contact",),
                    ("write", "endpoint_call"), ("commit",)]
    start, end = ledger.entries
    assert start.content == start.meta["call"] == end.meta["call"] and len(start.content) == 24
    assert start.meta["reserved"] == ledger.entries[0].meta["reserved"] != [0, 0]
    assert {name: start.meta[name] for name in support.SAME} == {
        name: end.meta[name] for name in support.SAME}
    assert start.meta["key"] == "ci-bot" and len(start.meta["prompt_sha"]) == 16
    assert len(upstream.requests) == 1


def test_control_a_started_entry_written_after_contact_is_seen_by_the_watch(
        keyed, served, monkeypatch, home):
    """Control for the test above: with the start moved behind the contact, the order shows it."""
    from harness import gateway_account, gateway_calls
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, _ledger, _disk = gateway_on_disk(monkeypatch, served, turn2(1), home)
    real = gateway_account.Call.reach

    def reach(self, send):              # the fault: contact first, then the started entry
        if self.state == "open":
            self.state = "contacted"
            got = send()
            self.call = gateway_calls.begin(self.ledger, self.base, self.reserved)
            self.base["call"] = self.call
            self.begun()
            return got
        return real(self, send)
    monkeypatch.setattr(gateway_account.Call, "reach", reach)
    seen = _watch(monkeypatch)
    # Since the sixth review round the transports refuse a request that leaves outside an
    # account (harness.gateway_reach), which stops this planted fault before the upstream:
    assert post(url, "/v1/messages", raw)[0] == 500 and _upstream.requests == []
    # With that rule off, the fault goes through, and the watch shows the wrong order.
    from harness import gateway_key_policy, gateway_reach
    gateway_key_policy.clear(keys, "ci-bot")    # the refused call suspended its key
    gateway_reach.release()
    del seen[:]
    assert post(url, "/v1/messages", raw)[0] == 200
    assert seen[:3] == [("contact",), ("write", STARTED), ("commit",)]


def test_a_started_entry_that_cannot_be_written_refuses_the_call_and_sends_nothing(
        keyed, served, monkeypatch, home):
    """R4, the stronger form: the call that meets a full disk is refused before contact."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger, disk = gateway_on_disk(monkeypatch, served, turn2(1), home)
    disk.full = True
    for body in ({**BODIES["/v1/messages"], "stream": True}, None):
        status, headers, answer = post(url, "/v1/messages", raw, body)
        assert status == 503, answer
        assert "nothing was sent upstream" in answer["error"]["message"]
        assert "retry-after" in {name.lower() for name in headers}
    assert upstream.requests == [], "a call with no started entry reached the provider"
    assert keys.row("ci-bot")["totals"]["tokens"] == 0 and "suspended" not in keys.row("ci-bot")
    disk.full = False
    assert post(url, "/v1/messages", raw)[0] == 200 and len(upstream.requests) == 1
    gateway_ledger.close_all()
    assert kinds(home) == ["ledger_gap", STARTED, "endpoint_call"]
    assert late(home) == [] and gateway_ledger_cli.main(["verify"]) == 0


def test_a_start_that_reached_the_disk_and_was_not_committed_is_ended_as_not_sent(
        keyed, served, monkeypatch, home):
    """The started line lands and its commit fails. The call is refused; the line stays in
    the file, so the resumed ledger ends it: `not_sent`."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger, _disk = gateway_on_disk(monkeypatch, served, turn2(2), home)
    real, failing = os.fsync, [True]

    def fsync(fd):
        if failing[0]:
            raise OSError(5, "Input/output error")
        return real(fd)
    monkeypatch.setattr(os, "fsync", fsync)
    assert post(url, "/v1/messages", raw)[0] == 503 and upstream.requests == []
    failing[0] = False
    assert post(url, "/v1/messages", raw)[0] == 200 and len(upstream.requests) == 1
    gateway_ledger.close_all()
    found, = gateway_ledger.check(home)
    rows = found["rows"]
    assert [row.kind for row in rows][0] == STARTED and rows[-2].kind == STARTED
    ended, = late(home)
    assert (ended.kind, ended.content, ended.meta["call"]) == (
        "endpoint_call_failed", "not_sent", rows[0].content)
    assert "reserved" not in ended.meta and ended.meta["key"] == "ci-bot"
    assert gateway_ledger_cli.main(["verify"]) == 0


# --- A process killed at each point around the two commits ---------------------------------

def _killed(home, url, keys, point) -> None:
    row = keys.row("ci-bot")
    done = subprocess.run(
        [sys.executable, "-m", "tests.gateway_crash_child", str(home), url, "ci-bot",
         row["fingerprint"], point], cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    assert done.returncode == DIED, (point, done.returncode, done.stderr[-2000:])


# point -> (provider requests, entry kinds on disk, calls `verify` names unsettled)
LEFT = {
    "before_start": (0, [], 0),
    "start_written": (0, [STARTED], 1),     # written, never sent: reported, as it may have been
    "before_send": (0, [STARTED], 1),
    "after_reply": (1, [STARTED], 1),       # the case that had no entry before this round
    "end_written": (1, [STARTED, "endpoint_call"], 0),
    "done": (1, [STARTED, "endpoint_call"], 0),
}


@pytest.mark.parametrize("point", POINTS)
def test_a_gateway_killed_at_any_point_never_leaves_a_provider_call_without_its_start(
        keyed, tmp_path, monkeypatch, capsys, point):
    keys, _store = keyed
    keys.create("ci-bot")
    where = tmp_path / "home"
    monkeypatch.setenv("FLYWHEEL_HOME", str(where))
    with support.Upstream(turn2(1)) as upstream:
        _killed(where, upstream.url, keys, point)
        requests = len(upstream.requests)
    wanted_requests, wanted_kinds, unsettled = LEFT[point]
    found = gateway_ledger.check(where)
    on_disk = [entry.kind for segment in found for entry in segment["rows"]]
    assert all(segment["ok"] for segment in found), found
    assert (requests, on_disk) == (wanted_requests, wanted_kinds)
    assert requests == 0 or STARTED in on_disk      # the invariant, whatever the point
    assert gateway_ledger_cli.main(["verify"]) == (3 if unsettled else 0)
    said = capsys.readouterr().out
    assert said.count("UNSETTLED call") == unsettled
    # The key is debited after the reply is read and before the end entry is written.
    charged = keys.row("ci-bot")["totals"]["tokens"]
    assert charged == (460 if point in ("end_written", "done") else 0)


def test_the_points_cover_both_commits_of_a_call():
    """The table above names every point the child can die at, and both commit boundaries."""
    assert set(LEFT) == set(POINTS)
    assert {"start_written", "before_send", "after_reply", "end_written"} <= set(POINTS)
