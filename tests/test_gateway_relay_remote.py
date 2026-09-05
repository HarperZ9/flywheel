"""test_gateway_relay_remote.py -- the remote half of the relay lane.

GET /api/relay/remote answers whether a phone could reach this workstation.
relay owns that answer because the phone-facing surface is a separate process
from the lane the gateway spawns; these tests cover the projection, which has
one job beyond forwarding: keeping three outcomes apart that would otherwise
collapse into "off". A lane that did not answer, a relay build that does not
report this, and a surface that is genuinely off are different facts, and an
operator told the wrong one goes looking in the wrong place.
"""
from __future__ import annotations

from harness import gateway


def _handler():
    h = gateway._Handler.__new__(gateway._Handler)
    seen = {}
    h._json = lambda body, code=200: seen.update(body=body, code=code)
    return h, seen

def test_relay_remote_route_projects_the_doctor_block(monkeypatch):
    # The card renders this. What matters is that the block arrives whole and
    # that the gateway adds nothing of its own to it.
    block = {"configured": True, "oauth_configured": False,
             "oauth_missing": ["RELAY_AUTHORIZE_PASSWORD"],
             "keys_present": {"RELAY_REMOTE_TOKEN": True}}
    calls = []
    monkeypatch.setattr(gateway, "_relay_mcp_call",
                        lambda tool, args: (calls.append(tool) or
                                            {"ok": True, "remote": dict(block)}))
    h, seen = _handler()
    h.path = "/api/relay/remote"
    h._get()

    assert calls[-1] == "relay.doctor"
    assert seen["body"] == {"reported": True, **block}


def test_an_unreachable_lane_is_not_a_configured_off_surface(monkeypatch):
    # The distinction the whole readout rests on. Rendering an unreachable
    # lane as "off" tells an operator their working setup is off.
    monkeypatch.setattr(gateway, "_relay_mcp_call",
                        lambda tool, args: {"error": "relay lane unavailable: [WinError 2]"})
    state = gateway._relay_remote_state()
    assert state["reported"] is False
    assert "configured" not in state
    assert "unavailable" in state["reason"]


def test_a_relay_that_does_not_report_says_so(monkeypatch):
    # An older relay answers relay.doctor without the block. Silence about
    # the remote surface is not the same fact as the surface being off.
    for answer in ({"ok": True}, {"ok": True, "remote": None},
                   {"ok": True, "remote": "configured"}):
        monkeypatch.setattr(gateway, "_relay_mcp_call", lambda t, a, r=answer: dict(r))
        state = gateway._relay_remote_state()
        assert state["reported"] is False, answer
        assert "does not report" in state["reason"], answer
