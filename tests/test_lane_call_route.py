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


def test_a_lane_error_is_a_fixed_code_without_the_tool_text(monkeypatch):
    """O-7 default: the tool's own text does not pass; a fixed code and a
    reason slug do. (Before WP8 the text passed through as a 400.)"""
    def _err(lane, tool, args, *, timeout, governance_tier,
             bulletin_access=None):
        return {"error": "gather.nope error: secret-ish tool text"}

    import harness.lane_caller as caller
    monkeypatch.setattr(caller, "call_lane_tool", _err)
    result, code = handle_lane_call("/api/lane/gather/nope", {})
    assert code == 502 and result["code"] == "LANE_TOOL_ERROR"
    assert result["reason"] == "tool_reported_error"
    assert "secret-ish" not in str(result)


# ---- WP8: fixed lane error codes, pinned against the real lane_caller -----

class _Client:
    """Stands in for MCPClient inside lane_caller._call."""
    error = None
    result: dict = {"ok": True, "text": "{}"}

    def __init__(self, command, *, timeout, client_name):
        pass

    def __enter__(self):
        if _Client.error is not None:
            raise _Client.error
        return self

    def __exit__(self, *_exc):
        return False

    def call_text(self, tool, args):
        return _Client.result


@pytest.fixture
def real_caller(monkeypatch, tmp_path):
    """lane_caller runs for real; only the launch and the client are fakes."""
    import harness.lane_probe_cache as probes
    import harness.lanes as lanes
    import harness.mcp_client as mcp_client
    from harness.mcp_client import LaunchSpec
    cache = probes.ProbeCache(tmp_path / "probes.json", engine="9.9.9")
    monkeypatch.setattr(probes, "default_cache", lambda environ=None: cache)
    monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda name: LaunchSpec(
        ("engine.exe", "--bundled-lane-mcp", name), inherit_env=False,
        allowed_tools=("gather.docs",)))
    monkeypatch.setattr(mcp_client, "MCPClient", _Client)
    _Client.error, _Client.result = None, {"ok": True, "text": "{}"}
    return cache


def _pin(lane):
    from harness.lanes_registry import LANES
    return LANES[lane].version


@pytest.mark.parametrize("kind, text, code, reason, status", [
    ("MCPError", "no response within 5s", "LANE_TIMEOUT", "no_response", 504),
    ("MCPError", "server closed the connection", "LANE_CANNOT_LAUNCH", "server_exited", 503),
    ("FileNotFoundError", "engine.exe", "LANE_CANNOT_LAUNCH", "runtime_executable_missing", 503),
    ("OSError", "denied", "LANE_CANNOT_LAUNCH", "launch_failed", 503),
    ("MCPError", "tools/call: {'code': -32000}", "LANE_TOOL_ERROR", "mcp_error", 502),
])
def test_caller_failures_become_fixed_codes(real_caller, kind, text, code, reason, status):
    from harness.mcp_client import MCPError
    _Client.error = {"MCPError": MCPError, "FileNotFoundError": FileNotFoundError,
                     "OSError": OSError}[kind](text)
    body, got = handle_lane_call("/api/lane/gather/gather.docs", {"timeout": 5})
    assert (got, body["code"], body["reason"]) == (status, code, reason)
    assert "engine.exe" not in str(body) and text not in str(body)
    if code == "LANE_TIMEOUT":
        assert body["timeout_s"] == 5
    record, _fresh = real_caller.lookup("gather", _pin("gather"))
    assert (record is not None and record["outcome"] == "cannot_launch") == (
        code == "LANE_CANNOT_LAUNCH")


def test_a_tool_error_from_the_real_caller_is_a_tool_error(real_caller):
    _Client.result = {"ok": False, "text": "unavailable: MCPError: looks like a marker"}
    body, status = handle_lane_call("/api/lane/gather/gather.docs", {})
    assert (status, body["code"], body["reason"]) == (
        502, "LANE_TOOL_ERROR", "tool_reported_error")


def test_not_admitted_carries_the_admitted_list(real_caller):
    body, status = handle_lane_call("/api/lane/gather/gather.context", {})
    assert (status, body["code"]) == (400, "CAPABILITY_NOT_ADMITTED")
    assert "gather.docs" in body["admitted"]


def test_not_in_build_keeps_its_reason_slug(real_caller):
    body, status = handle_lane_call("/api/lane/calibrate-pro/calibrate-pro.list-targets",
                                    {"governance_tier": "T2"})
    assert (status, body["code"], body["reason"]) == (
        400, "NOT_IN_BUILD", "numpy_not_in_build")


def test_a_setup_code_is_lane_setup_required_with_the_item(monkeypatch):
    from types import SimpleNamespace

    import harness.lanes as lanes
    from harness.lane_runtime import LaneRuntimeError

    def blocked(name):
        raise LaneRuntimeError(name, ("local_model_root_unset",))

    monkeypatch.setattr(lanes, "resolve_mcp_launch", blocked)
    monkeypatch.setattr(lanes, "resolve_lane_runtime", lambda name: SimpleNamespace(
        blocking_codes=("local_model_root_unset",)))
    body, status = handle_lane_call("/api/lane/local-model/local_agent_run",
                                    {"governance_tier": "T2"})
    assert (status, body["code"], body["setup"]) == (
        409, "LANE_SETUP_REQUIRED", ["project_folder"])


def test_an_unknown_lane_is_a_404_and_writes_no_record(real_caller):
    body, status = handle_lane_call("/api/lane/no-such-lane/x", {})
    assert (status, body["code"], body["reason"]) == (404, "LANE_CANNOT_LAUNCH", "unknown_lane")
    assert real_caller.lookup("no-such-lane", "") == (None, False)


def test_a_success_with_a_bound_key_records_the_name_as_validated(real_caller, monkeypatch):
    import harness.lane_caller as caller
    monkeypatch.setattr(caller, "call_lane_tool", lambda *a, **k: {"ok": True})

    class Bindings:
        def child_environment(self, base, *, platform):
            return {"FORUM_KEY": "sk-planted-fake"}

        def redact(self, text):
            return text.replace("sk-planted-fake", "[redacted]")

    # plan spends the key with FORUM_RUN_REAL; forum.route never uses it (C10)
    body, status = handle_lane_call("/api/lane/forum/plan", {}, Bindings())
    assert status == 200 and body == {"ok": True}
    assert real_caller.validated("forum") == {"FORUM_KEY"}
    assert "sk-planted-fake" not in real_caller.path.read_text(encoding="utf-8")


def _guarded_json(obj, status):
    """What a granted route's _json sends; a granted call sets _gateway_guarded."""
    import io

    from harness import gateway
    h = gateway._Handler.__new__(gateway._Handler)
    sent = {}
    h.send_response = lambda code: sent.update(status=code)
    h.send_header = h.end_headers = h._cors = lambda *a: None
    h.wfile = io.BytesIO()
    h._gateway_guarded = True
    h._json(obj, status)
    return sent["status"], h.wfile.getvalue().decode()


@pytest.mark.parametrize("code", ["NOT_IN_BUILD", "LANE_SETUP_REQUIRED",
                                  "LANE_CANNOT_LAUNCH", "LANE_TIMEOUT", "LANE_TOOL_ERROR",
                                  "CAPABILITY_NOT_ADMITTED", "SOMETHING_ELSE"])
def test_the_gateway_lets_only_lane_codes_past_its_failure_mask(code):
    """The guard replaces other errors with a fixed 502. The lane codes carry no
    free text, so they pass; an unlisted code is the falsifier and stays masked."""
    from harness.lane_call_route import LANE_ERROR_CODES
    status, text = _guarded_json({"code": code, "error": "fixed", "reason": "x"}, 503)
    if code in LANE_ERROR_CODES:
        assert (status, code in text) == (503, True)
    else:
        assert status == 502 and "EXTERNAL_ACTION_FAILED" in text
