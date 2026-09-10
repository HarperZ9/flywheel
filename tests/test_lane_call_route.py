"""The lane call route: what the path says and what the grant authorized are
two different claims, and they have to agree.

A grant names a lane and a tool. The URL names a lane and a tool. If the two
disagree the request is refused rather than resolved in favour of either one:
picking the path would let a granted call be redirected, and picking the body
would let the route lie about where it went."""
import pytest

from harness.lane_call_route import handle_lane_call, parse_lane_path


def test_a_malformed_path_is_a_caller_mistake():
    assert parse_lane_path("/wrong/lane/relay/relay.status") is None
    assert parse_lane_path("/api/lane/gather") is None
    assert parse_lane_path("/api/lane//status") is None
    assert parse_lane_path("/api/lane/gather/ ") is None
    assert parse_lane_path("/api/lane/relay/relay.status/extra") is None
    assert parse_lane_path("/api/lane/relay/relay.status/") is None
    body, code = handle_lane_call("/api/lane/gather", {})
    assert code == 400 and "use /api/lane" in body["error"]


def test_the_path_splits_into_lane_and_tool():
    assert parse_lane_path("/api/lane/gather/gather.status") == (
        "gather", "gather.status")
    assert parse_lane_path("/api/lane/gather/gather.status?trace=1") == (
        "gather", "gather.status")


@pytest.mark.parametrize("body", [
    {"name": "forum", "tool": "gather.status", "args": {}},
    {"name": "gather", "tool": "forum.route", "args": {}},
])
def test_a_grant_for_another_target_refuses_rather_than_redirects(body):
    result, code = handle_lane_call("/api/lane/gather/gather.status", body)
    assert code == 409
    assert "do not match the route" in result["error"]


def test_an_absent_grant_leaves_the_path_standing_alone(monkeypatch):
    # A direct call that never reached the gate carries no name or tool. That
    # is not a mismatch; the path is then the only claim there is.
    called = {}

    def _fake(lane, tool, args, *, timeout, governance_tier,
              bulletin_access=None):
        called.update(lane=lane, tool=tool, args=args, timeout=timeout,
                      tier=governance_tier, bulletin_access=bulletin_access)
        return {"ok": True}

    import harness.lane_caller as caller
    monkeypatch.setattr(caller, "call_lane_tool", _fake)
    result, code = handle_lane_call("/api/lane/gather/gather.status", {})
    assert code == 200 and result == {"ok": True}
    assert called["lane"] == "gather" and called["tool"] == "gather.status"
    assert called["args"] == {} and called["tier"] == ""
    assert called["bulletin_access"] is None


def test_args_must_be_an_object_and_a_bad_timeout_falls_back(monkeypatch):
    result, code = handle_lane_call(
        "/api/lane/gather/gather.status", {"args": ["not", "an", "object"]})
    assert code == 400 and result["error"] == "'args' must be an object"

    seen = {}

    def _fake(lane, tool, args, *, timeout, governance_tier,
              bulletin_access=None):
        seen["timeout"] = timeout
        return {"ok": True}

    import harness.lane_caller as caller
    monkeypatch.setattr(caller, "call_lane_tool", _fake)
    # True is an int in Python, and a boolean timeout is a caller mistake
    # rather than a one-second budget: it falls back to the default.
    handle_lane_call("/api/lane/g/t", {"timeout": True})
    assert seen["timeout"] != 1


def test_bulletin_access_is_forwarded_to_the_lane_caller(monkeypatch):
    seen = {}

    def _fake(lane, tool, args, *, timeout, governance_tier,
              bulletin_access=None):
        seen.update(lane=lane, tool=tool, access=bulletin_access)
        return {"ok": True}

    import harness.lane_caller as caller
    monkeypatch.setattr(caller, "call_lane_tool", _fake)
    result, code = handle_lane_call(
        "/api/lane/bulletin/board_feed",
        {"name": "bulletin", "tool": "board_feed", "args": {},
         "bulletin_access": "off"})
    assert code == 200 and result == {"ok": True}
    assert seen == {"lane": "bulletin", "tool": "board_feed", "access": "off"}


def test_target_mismatch_refuses_before_bulletin_access_is_used(monkeypatch):
    def _fake(*_args, **_kwargs):
        raise AssertionError("caller should not run after route mismatch")

    import harness.lane_caller as caller
    monkeypatch.setattr(caller, "call_lane_tool", _fake)
    result, code = handle_lane_call(
        "/api/lane/gather/gather.status",
        {"name": "bulletin", "tool": "board_feed", "args": {},
         "bulletin_access": "off"})
    assert code == 409
    assert "do not match" in result["error"]


def test_a_governance_denial_is_an_answer_with_its_own_status(monkeypatch):
    def _denied(lane, tool, args, *, timeout, governance_tier,
                bulletin_access=None):
        return {"governance_denied": "tier T3 requires an approved TADR",
                "lane": lane}

    import harness.lane_caller as caller
    monkeypatch.setattr(caller, "call_lane_tool", _denied)
    result, code = handle_lane_call("/api/lane/gather/gather.run", {})
    assert code == 403
    assert result["governance_denied"].startswith("tier T3")


def test_a_lane_error_is_reported_as_the_callers_400(monkeypatch):
    def _err(lane, tool, args, *, timeout, governance_tier,
             bulletin_access=None):
        return {"error": "no such tool"}

    import harness.lane_caller as caller
    monkeypatch.setattr(caller, "call_lane_tool", _err)
    result, code = handle_lane_call("/api/lane/gather/nope", {})
    assert code == 400 and result["error"] == "no such tool"
