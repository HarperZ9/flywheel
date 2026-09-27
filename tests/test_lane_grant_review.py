"""The owner sees what a lane.call approval authorizes (POLICY-DECISION C-13).

The approval summary used to show the arguments only as a sha256 and never the
tier. A ``lane.call`` proposal now carries a ``lane_policy`` block: the tier the
tool needs and the tier requested, its effect and reason, the arguments the
engine forces or drops, and the arguments the child will receive, in plain form.
"""
from __future__ import annotations

from harness.gateway_grant_summary import proposal_response
from harness.gateway_operation import AuthorizedOperation

_RECORD = {"action": "lane.call", "journey_ref": "jrn_" + "a" * 32,
           "expected_event_head": "a" * 64, "expires_at": "2026-09-26T12:00:00Z",
           "proposal_ref": "prp_" + "a" * 32, "planned_grant_ref": "gnt_" + "a" * 32,
           "client_request_id": "req-1"}


def _summary(operation: dict) -> dict:
    op = AuthorizedOperation.for_test(action="lane.call", operation={
        "data_refs": [], "credential_refs": [], **operation},
        scopes=("exec", "network", "plugin"))
    return proposal_response(dict(_RECORD), op)["summary"]


def test_a_t2_call_shows_its_tier_effect_and_plain_arguments():
    review = _summary({"name": "gather", "tool": "gather.run", "governance_tier": "T2",
                       "args": {"config_path": "C:/work/run.json"}})["lane_policy"]
    assert review["required_tier"] == "T2" and review["requested_tier"] == "T2"
    assert review["t2"] is True
    assert review["effect"] == "outside_write" and review["reason"]
    assert review["arguments"] == {"config_path": "C:/work/run.json"}


def test_the_relay_run_shows_what_the_engine_forces_and_drops():
    review = _summary({"name": "relay", "tool": "local_agent_run",
                       "args": {"goal": "g", "check": "whoami", "allow_exec": True}}
                      )["lane_policy"]
    assert review["required_tier"] == "T1" and review["requested_tier"] == "T1"
    assert review["t2"] is False
    assert review["forced_arguments"] == {"allow_write": False, "allow_exec": False,
                                          "online": False}
    assert review["dropped_arguments"] == ["check"]
    assert review["arguments"] == {"goal": "g", "allow_write": False, "allow_exec": False,
                                   "online": False}
    assert review["requested_arguments"] == {"goal": "g", "check": "whoami",
                                             "allow_exec": True}


def test_a_call_that_binds_a_key_is_shown_as_t2():
    op = {"name": "mneme", "tool": "mneme.remember", "args": {},
          "credential_refs": ["cred_" + "a" * 32]}
    review = _summary(op)["lane_policy"]
    assert review["required_tier"] == "T2" and review["binds_key"] is True


def test_an_unlisted_tool_is_shown_as_unlisted():
    review = _summary({"name": "gather", "tool": "gather.new", "args": {}})["lane_policy"]
    assert review["listed"] is False and review["effect"] == "not reviewed: effect unknown"
