"""`FLYWHEEL_GATEWAY_LEDGER_SYNC=0`: what holds and what does not, shown by tests.

The fourth independent review listed this setting among what it had not
examined. docs/KNOWN-LIMITS-2.0.0.md says: with it an entry is not committed
to the disk before the gateway goes on; a crash of the gateway process loses
nothing; a power loss can lose the newest entries.

These tests hold the two parts a test can reach. The started entry is still
written before the request leaves, with no commit. A gateway process that is
killed still leaves it, because the operating system has the bytes. The third
part, a power loss, is not reachable from a test: nothing here cuts power.
No provider is called.
"""
import pytest

from harness import gateway_ledger, gateway_ledger_cli
from tests import gateway_messages_support as support
from tests.gateway_disk_support import gateway_on_disk, home  # noqa: F401  (fixture)
from tests.gateway_keys_support import BODIES, keyed, post, served, turn2  # noqa: F401
from tests.test_gateway_write_ahead import LEFT, STARTED, _killed, _watch

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release


def test_with_sync_off_the_started_entry_is_still_written_before_contact(
        keyed, served, monkeypatch, home):
    monkeypatch.setenv(gateway_ledger.SYNC_ENV, "0")
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger, _disk = gateway_on_disk(monkeypatch, served, turn2(1), home)
    seen = _watch(monkeypatch)
    assert post(url, "/v1/messages", raw, BODIES["/v1/messages"])[0] == 200
    assert seen == [("write", STARTED), ("contact",), ("write", "endpoint_call")]   # no commit
    assert getattr(ledger, "commits", None) is None and len(upstream.requests) == 1
    support.recorded(ledger)


def test_control_with_sync_on_each_entry_is_committed(keyed, served, monkeypatch, home):
    monkeypatch.delenv(gateway_ledger.SYNC_ENV, raising=False)
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, ledger, _disk = gateway_on_disk(monkeypatch, served, turn2(1), home)
    seen = _watch(monkeypatch)
    assert post(url, "/v1/messages", raw, BODIES["/v1/messages"])[0] == 200
    assert seen == [("write", STARTED), ("commit",), ("contact",),
                    ("write", "endpoint_call"), ("commit",)]
    assert ledger.commits[0] == 2


# The two points that die at a commit cannot be reached: there is no commit.
@pytest.mark.parametrize("point", ["before_start", "before_send", "after_reply", "done"])
def test_with_sync_off_a_killed_gateway_still_leaves_what_it_wrote(
        keyed, tmp_path, monkeypatch, capsys, point):
    monkeypatch.setenv(gateway_ledger.SYNC_ENV, "0")    # the child process inherits it
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
    assert requests == 0 or STARTED in on_disk      # the invariant, without the commit
    assert gateway_ledger_cli.main(["verify"]) == (3 if unsettled else 0)
    assert capsys.readouterr().out.count("UNSETTLED call") == unsettled
