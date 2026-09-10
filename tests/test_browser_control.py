"""Driving a screen: what is admitted, what is refused, what is recorded.

A tool that operates a browser is easy to build and hard to trust, so the
cases here are the ones a reader would ask about before letting it near a
logged-in machine. Can it reach an origin nobody allowed. Can a permissive
policy talk it into a password field. Does a refusal leave a trace, or does a
constrained run look afterwards like a run that simply did nothing.

The driver seam gets its own group. With nothing bound the engine still
decides and still records, and it must say `performed: false` rather than
imply a screen moved.
"""
import json

import pytest

from harness.browser_control import (MAX_ACTIONS, Refused, attempt,
                                     chain_intact, chain_path, clear_drivers,
                                     open_session, register_driver, session,
                                     sessions)

NOW = "2026-09-06T18:00:00Z"
OPEN_POLICY = {"origins": ["https://example.test"]}


@pytest.fixture(autouse=True)
def _no_driver():
    """Driver binding is process-wide, so no test may leak one to the next."""
    clear_drivers()
    yield
    clear_drivers()


def _started(tmp_path, policy=None, run_id="r1"):
    open_session(tmp_path, run_id=run_id, policy=policy or OPEN_POLICY, at=NOW)
    return tmp_path


def _navigated(tmp_path, url="https://example.test/page", run_id="r1"):
    _started(tmp_path, run_id=run_id)
    attempt(tmp_path, run_id=run_id, action={"kind": "navigate", "url": url},
            at=NOW)
    return tmp_path


def test_nothing_is_attempted_until_a_policy_is_written_down(tmp_path):
    """The rules exist before the acts they judge, or they are an excuse.

    A policy written after the fact can be shaped to fit whatever happened,
    which is why it is the chain's first record rather than a field on the
    request.
    """
    with pytest.raises(Refused, match="has no policy yet"):
        attempt(tmp_path, run_id="r1",
                action={"kind": "navigate", "url": "https://example.test/"},
                at=NOW)
    assert session(tmp_path, run_id="r1")["attempted"] == 0


def test_the_policy_is_fixed_once_and_cannot_be_written_again(tmp_path):
    _started(tmp_path)
    with pytest.raises(Refused, match="already has a policy"):
        open_session(tmp_path, run_id="r1",
                     policy={"origins": ["https://elsewhere.test"]}, at=NOW)


def test_a_policy_naming_no_origin_is_refused(tmp_path):
    for policy in ({}, {"origins": []}, {"origins": "https://example.test"}):
        with pytest.raises(Refused, match="at least one origin"):
            open_session(tmp_path, run_id="r1", policy=policy, at=NOW)


def test_an_origin_nobody_allowed_is_refused_and_the_refusal_is_kept(tmp_path):
    """The refused half is the half somebody argues about later.

    A gate that records only what it allowed cannot show that it turned
    anything down, so a tightly bounded run and an unbounded one read the
    same afterwards.
    """
    _started(tmp_path)
    record = attempt(tmp_path, run_id="r1",
                     action={"kind": "navigate",
                             "url": "https://elsewhere.test/x"}, at=NOW)
    assert record["admitted"] is False
    assert record["reason"] == "https://elsewhere.test is not an allowed origin"
    body = session(tmp_path, run_id="r1")
    assert body["refused"] == 1 and body["attempted"] == 1
    assert body["open_origin"] is None
    assert body["actions"][0]["action"]["url"] == "https://elsewhere.test/x"


def test_a_credential_field_is_refused_by_a_policy_that_allows_everything(
        tmp_path):
    """The standing rule sits in the gate so no policy can reach around it.

    This is the one refusal checked before the policy is consulted, which is
    the difference between a rule and a default.
    """
    _navigated(tmp_path)
    for field in ("password", "Password", "card-number", "api_key",
                  "user otp", "seed_phrase"):
        record = attempt(tmp_path, run_id="r1",
                         action={"kind": "type", "field": field,
                                 "selector": "#f"}, at=NOW)
        assert record["admitted"] is False
        assert record["reason"].startswith("typing into a credential field")
    assert session(tmp_path, run_id="r1")["refused"] == 6


def test_ordinary_typing_still_works_so_the_rule_is_a_rule_not_a_ban(tmp_path):
    _navigated(tmp_path)
    record = attempt(tmp_path, run_id="r1",
                     action={"kind": "type", "field": "search",
                             "selector": "#q"}, at=NOW)
    assert record["admitted"] is True and record["reason"] == ""


def test_a_url_that_is_not_http_never_resolves(tmp_path):
    """Otherwise this is a local-disk read primitive wearing a browser's name."""
    _started(tmp_path)
    for url in ("file:///c/secrets.txt", "data:text/html,<b>x", "javascript:1",
                "https://"):
        with pytest.raises(Refused, match="not an http or https URL"):
            attempt(tmp_path, run_id="r1",
                    action={"kind": "navigate", "url": url}, at=NOW)


def test_acting_before_a_page_is_open_is_refused(tmp_path):
    _started(tmp_path)
    record = attempt(tmp_path, run_id="r1",
                     action={"kind": "click", "selector": "#go"}, at=NOW)
    assert record["admitted"] is False
    assert record["reason"] == "no page is open, so there is nothing to act on"


def test_an_act_inherits_the_origin_of_the_page_that_is_open(tmp_path):
    _navigated(tmp_path)
    record = attempt(tmp_path, run_id="r1",
                     action={"kind": "screenshot"}, at=NOW)
    assert record["admitted"] is True
    assert record["origin"] == "https://example.test"


def test_a_policy_may_refuse_a_whole_kind_of_act(tmp_path):
    _navigated(tmp_path, run_id="r2")
    body = _started(tmp_path, policy=dict(OPEN_POLICY,
                                          refuse_kinds=["download"]),
                    run_id="r3")
    record = attempt(body, run_id="r3",
                     action={"kind": "download",
                             "url": "https://example.test/f.zip"}, at=NOW)
    assert record["reason"] == "the policy refuses download"


def test_a_policy_naming_an_act_that_does_not_exist_is_refused(tmp_path):
    with pytest.raises(Refused, match="no such action: exfiltrate"):
        open_session(tmp_path, run_id="r1",
                     policy=dict(OPEN_POLICY, refuse_kinds=["exfiltrate"]),
                     at=NOW)


def test_the_session_cap_turns_a_runaway_loop_into_a_reason(tmp_path):
    """A cap is a bill and a browser history that never happened."""
    _started(tmp_path, policy=dict(OPEN_POLICY, max_actions=2))
    attempt(tmp_path, run_id="r1",
            action={"kind": "navigate", "url": "https://example.test/"},
            at=NOW)
    attempt(tmp_path, run_id="r1", action={"kind": "screenshot"}, at=NOW)
    record = attempt(tmp_path, run_id="r1", action={"kind": "screenshot"},
                     at=NOW)
    assert record["reason"] == "the session cap of 2 is spent"


def test_a_cap_outside_the_bounds_is_refused(tmp_path):
    for cap in (0, MAX_ACTIONS + 1, "many"):
        with pytest.raises(Refused, match="max_actions"):
            open_session(tmp_path, run_id="r1",
                         policy=dict(OPEN_POLICY, max_actions=cap), at=NOW)


def test_with_nothing_bound_the_engine_decides_and_performs_nothing(tmp_path):
    """An honest null rather than a pretend success.

    Shipping the gate without actuation is a supported way to run, so the
    answer has to distinguish an admitted act from an act that happened.
    """
    _started(tmp_path)
    record = attempt(tmp_path, run_id="r1",
                     action={"kind": "navigate", "url": "https://example.test/"},
                     at=NOW)
    assert record["admitted"] is True
    assert record["performed"] is False and record["result_sha256"] == ""
    body = session(tmp_path, run_id="r1")
    assert body["driver"] is None and body["performed"] == 0
    assert body["admitted"] == 1


def test_a_bound_driver_sees_admitted_acts_and_never_a_refused_one(tmp_path):
    seen = []
    register_driver("recorder", lambda act: seen.append(act) or {"ok": True, "performed": True})
    _started(tmp_path)
    attempt(tmp_path, run_id="r1",
            action={"kind": "navigate", "url": "https://example.test/"}, at=NOW, request_id="allowed")
    attempt(tmp_path, run_id="r1",
            action={"kind": "navigate", "url": "https://elsewhere.test/"},
            at=NOW, request_id="refused")
    assert [a["url"] for a in seen] == ["https://example.test/"]
    body = session(tmp_path, run_id="r1")
    assert body["driver"] == "recorder" and body["performed"] == 1
    assert body["actions"][0]["result_sha256"]
    assert body["actions"][1]["performed"] is False


def test_two_bound_drivers_are_ambiguous_so_neither_is_used(tmp_path):
    register_driver("one", lambda act: {"ok": True})
    register_driver("two", lambda act: {"ok": True})
    _started(tmp_path)
    record = attempt(tmp_path, run_id="r1",
                     action={"kind": "navigate", "url": "https://example.test/"},
                     at=NOW)
    assert record["performed"] is False and record["driver"] is None


def test_a_driver_that_cannot_be_called_is_refused_at_binding(tmp_path):
    with pytest.raises(Refused, match="must be callable"):
        register_driver("broken", "notafunction")


def test_every_verdict_cites_the_one_before_it(tmp_path):
    _navigated(tmp_path)
    records = json.loads(chain_path(tmp_path, "r1").read_text(encoding="utf-8"))
    assert [r["kind"] for r in records] == ["policy", "action"]
    assert records[0]["prev_sha256"] == ""
    assert records[1]["prev_sha256"] == records[0]["action_sha256"]
    assert records[1]["seq"] == 1
    assert chain_intact(records) is True


def test_loosening_the_policy_afterwards_stops_the_session(tmp_path):
    """The edit somebody would make: widening the rules to fit the afternoon.

    Nothing stops a file being edited. What breaks is the citation on every
    verdict the old policy produced, so the next attempt is refused rather
    than judged by rules that were written last.
    """
    _navigated(tmp_path)
    path = chain_path(tmp_path, "r1")
    records = json.loads(path.read_text(encoding="utf-8"))
    records[0]["policy"]["origins"].append("https://elsewhere.test")
    path.write_text(json.dumps(records), encoding="utf-8")
    with pytest.raises(Refused, match="chain for this session is broken"):
        attempt(tmp_path, run_id="r1",
                action={"kind": "navigate", "url": "https://elsewhere.test/"},
                at=NOW)
    body = session(tmp_path, run_id="r1")
    assert body["chain_intact"] is False and body["actions"] == []


def test_a_run_id_is_checked_rather_than_repaired(tmp_path):
    """Stripping the bad characters would map two names onto one history."""
    for name in ("../../etc", "a/b", "one two"):
        with pytest.raises(Refused, match="run_id must hold"):
            chain_path(tmp_path, name)
    for name in ("", "..", "x" * 65):
        with pytest.raises(Refused, match="run_id must"):
            chain_path(tmp_path, name)
    assert chain_path(tmp_path, "run-1.a").parent.name == "run-1.a"


def test_an_action_the_grammar_does_not_name_is_refused(tmp_path):
    _started(tmp_path)
    with pytest.raises(Refused, match="unknown action kind"):
        attempt(tmp_path, run_id="r1", action={"kind": "eval"}, at=NOW)


def test_sessions_are_listed_and_kept_apart(tmp_path):
    _navigated(tmp_path, run_id="alpha")
    _started(tmp_path, run_id="beta")
    assert sessions(tmp_path) == ["alpha", "beta"]
    assert session(tmp_path, run_id="alpha")["attempted"] == 1
    assert session(tmp_path, run_id="beta")["attempted"] == 0
    assert sessions(tmp_path / "empty") == []
