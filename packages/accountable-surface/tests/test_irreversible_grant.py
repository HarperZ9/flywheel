"""An approval cannot widen the grant (R7.grant).

The surface refuses an irreversible act unless the grant lists its action kind in
``scope.allowed_irreversible_actions``. The pipeline's approval is a second key,
never a replacement for the first. These tests hold that an irreversible step the
grant does not name is refused at the policy check, before any person is asked
to approve it, and that a recorded approval does not lift the refusal.
"""

from __future__ import annotations

import pytest
from actuation_site import Site
from actuation_world import World, grant, rules

from accountable_surface import plan, policy
from accountable_surface.detectors import secrets
from accountable_surface.page_evidence import parse_page

ORIGIN = "http://127.0.0.1:8765"
NOW = "2026-09-27T12:00:00+00:00"


@pytest.fixture
def site():
    s = Site().start()
    yield s
    s.stop()


def _unlisted(origin):
    g = grant(origin)
    g["scope"].pop("allowed_irreversible_actions")
    return g


def test_a_submit_the_grant_does_not_name_is_refused_and_no_approval_is_asked(tmp_path, site):
    w = World(tmp_path, site, the_grant=_unlisted(site.origin))
    w.nav("/order")
    result = w.submit_order()
    assert (result.status, result.verdict) == ("refused", "not-acted")
    assert {"R7.irreversible", "R7.grant"} <= rules(result)
    assert not result.approval_id and w.store.pending() == []
    assert site.orders == []


def test_the_same_submit_is_held_for_a_person_when_the_grant_names_it(tmp_path, site):
    w = World(tmp_path, site)
    w.nav("/order")
    held = w.submit_order()
    assert held.status == "needs-human" and held.approval_id
    assert "R7.grant" not in rules(held)
    assert site.orders == []


@pytest.mark.parametrize("listed", [None, [], "browser.click", ["*"], ["web.submit"], True])
def test_only_an_exact_kind_in_a_list_counts(listed):
    page = parse_page(ORIGIN + "/notes", "<title>Notes</title><button type='button'>Send</button>",
                      redactor=secrets.redact)
    step = plan.step_from_dict({"step_id": "s1", "action_kind": "browser.click",
                                "target": {"origin": ORIGIN, "path": "/notes", "control": {"name": "Send"}},
                                "args": {}, "post_condition": {"kind": "text_present", "value": "Sent"}})
    scope = {"allowed_actions": ["browser.click"], "target_tiers": [{"origin": ORIGIN, "tier": "full"}]}
    if listed is not None:
        scope["allowed_irreversible_actions"] = listed
    approval = {"approval_id": "ap_1", "status": "approved", "step_digest": plan.step_digest(step),
                "before_digest": page.digest, "expires_at": "2026-09-27T12:10:00+00:00",
                "record": "sha256:r", "channel": "cli-tty", "approver": "operator"}
    for offered in (None, approval):
        decision = policy.decide(step, page, grant={"scope": scope}, approval=offered,
                                 paused=frozenset(), now=NOW)
        assert decision.outcome == "refuse", (listed, offered)
        assert {"R7.irreversible", "R7.grant"} <= {h["rule"] for h in decision.rule_hits}
        assert decision.approval is None


def test_a_reversible_step_is_not_touched_by_the_rule(tmp_path, site):
    w = World(tmp_path, site, the_grant=_unlisted(site.origin))
    result = w.nav("/notes")
    assert (result.status, result.verdict) == ("acted", "verified")
    assert "R7.grant" not in rules(result)
