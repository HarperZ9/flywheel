"""The grant sheet can ask for every action the engine can canonicalize.

The prepare route once carried its own allowlist, written by hand beside the
engine's field table. The two drifted: seven actions the engine could
canonicalize and dispatch answered 404 at the sheet, so a surface could be
built, opened, and never granted. The allowlist is now derived from the field
table, and these tests hold the two together in both directions."""
import json

from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_operation import GRANTABLE_ACTIONS
from harness.journey_store import JourneyStore, MutationCommand

NOW = "2026-08-15T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
JOURNEY = "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _journey(state):
    return JourneyStore(state).create(MutationCommand(
        OWNER, JOURNEY, None, "create-1", "intake",
        {"legacy_label": None, "goal": "Bound action", "intake": {},
         "occurred_at": NOW}))


def test_every_canonicalizable_action_can_be_prepared(tmp_path):
    """The prepare route once restated its own action list, so seven actions
    the engine could canonicalize and dispatch had no way to reach a grant:
    their surfaces got 404 at the sheet. The allowlist is now the engine's
    own field table, and this holds the two together."""
    _journey(tmp_path)
    reached = set()
    for action in sorted(GRANTABLE_ACTIONS):
        body, status = gateway_grant_post(
            f"/api/gateway-grants/prepare/{action}",
            json.dumps({"schema": "flywheel.gateway-operation/v1",
                        "journey_ref": JOURNEY,
                        "expected_event_head": "a" * 64,
                        "client_request_id": "probe-1",
                        "operation": {}}).encode(),
            owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
        # An empty operation is refused on its fields, not on the route. What
        # this asserts is that the action was recognized at all: 404 would
        # mean the sheet cannot ask for it.
        assert status != 404, f"{action} cannot be prepared"
        assert body["error"]["code"] != "NOT_FOUND"
        reached.add(action)
    assert reached == set(GRANTABLE_ACTIONS)


def test_an_action_the_engine_cannot_canonicalize_is_not_found(tmp_path):
    body, status = gateway_grant_post(
        "/api/gateway-grants/prepare/rm.rf",
        json.dumps({"schema": "flywheel.gateway-operation/v1",
                    "journey_ref": JOURNEY,
                    "expected_event_head": "a" * 64,
                    "client_request_id": "probe-1",
                    "operation": {}}).encode(),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert status == 404 and body["error"]["code"] == "NOT_FOUND"
