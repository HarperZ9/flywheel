"""policy:self cannot become policy:machine from the agent's side.

The agent writes the receipt and can reseal it, so it can claim any basis.
Every route it controls is tried here: a bare relabel, a statement signed with
its own key, a genuine statement for a different call, a genuine statement
with the decision flipped, and a genuine statement from a signer that shares
its identity. Success criterion: each is re-derived as policy:self, carries an
AUTHORITY_DOWNGRADED finding, and verify_action never returns MATCH. One
control shows a genuine statement from a separate-identity signer does pass.
"""
from __future__ import annotations

import pytest

from harness import action_authority as au
from harness.action_authority_verify import verify_action
from tests.test_action_authority import ISO_SAME, _machine, _receipt, _signer

ARGS = {"cmd": "ls"}


def _claimed_machine(element):
    return {"basis": au.MACHINE, "decision": element["decision"], "verdict": au.PASS,
            "elements": [element]}


def _assert_downgraded(receipt, root):
    out = verify_action(receipt, root)
    assert out["verdict"] != "MATCH", out
    auth = out["authority"]
    assert auth["basis"] == au.SELF and auth["verdict"] == au.UNENFORCED
    assert any(f["cause"] == "AUTHORITY_DOWNGRADED" for f in auth["findings"])
    return auth


def test_control_a_separate_signers_statement_passes(tmp_path):
    signer = _signer(tmp_path)
    receipt = _receipt(args=ARGS, block=au.resolve([_machine(signer, ARGS)]))
    assert verify_action(receipt, signer.public.hex())["verdict"] == "MATCH"


def test_a_bare_relabel_is_downgraded(tmp_path):
    signer = _signer(tmp_path)
    element = dict(au.policy_self("only run read commands", au.ALLOW), basis=au.MACHINE)
    _assert_downgraded(_receipt(args=ARGS, block=_claimed_machine(element)),
                       signer.public.hex())


def test_a_statement_under_the_agents_own_key_is_downgraded(tmp_path):
    signer = _signer(tmp_path)
    agent = _signer(tmp_path / "agent")
    element = _machine(agent, ARGS)
    auth = _assert_downgraded(_receipt(args=ARGS, block=_claimed_machine(element)),
                              signer.public.hex())
    assert "does not verify" in auth["findings"][0]["detail"]


def test_a_statement_for_another_call_is_downgraded(tmp_path):
    signer = _signer(tmp_path)
    element = _machine(signer, {"cmd": "pwd"})
    auth = _assert_downgraded(_receipt(args=ARGS, block=_claimed_machine(element)),
                              signer.public.hex())
    assert "other arguments" in auth["findings"][0]["detail"]


def test_a_flipped_decision_is_downgraded(tmp_path):
    signer = _signer(tmp_path)
    element = _machine(signer, {"cmd": "git push --force"})
    assert element["decision"] == au.DENY
    flipped = dict(element, decision=au.ALLOW)
    _assert_downgraded(_receipt(args={"cmd": "git push --force"},
                                block=_claimed_machine(flipped)), signer.public.hex())


def test_a_same_identity_signer_is_not_machine_policy(tmp_path):
    signer = _signer(tmp_path)
    element = _machine(signer, ARGS, iso=ISO_SAME)
    auth = _assert_downgraded(_receipt(args=ARGS, block=_claimed_machine(element)),
                              signer.public.hex())
    assert "same-identity" in auth["findings"][0]["detail"]


def test_without_a_pinned_root_nothing_is_machine_policy(tmp_path):
    signer = _signer(tmp_path)
    receipt = _receipt(args=ARGS, block=au.resolve([_machine(signer, ARGS)]))
    _assert_downgraded(receipt, "")


def test_the_signer_uses_the_operators_context_not_the_callers(tmp_path):
    import hashlib
    import json
    signer = _signer(tmp_path, context={"workspace": "/srv/repo",
                                        "allow_hosts": ["example.org"]})
    reply = signer.handle({"op": "check_policy", "tool": "run", "args": ARGS,
                           "context": {"allow_hosts": ["evil.example"]}}, {"mode": "x"})
    from harness.signer.policy import load_context
    want = hashlib.sha256(json.dumps(load_context(tmp_path / "signer"),
                                     sort_keys=True).encode()).hexdigest()
    assert reply["policy"]["context_sha256"] == want


@pytest.mark.parametrize("req", [{"op": "check_policy", "tool": "", "args": {}},
                                 {"op": "check_policy", "tool": "run", "args": "ls"}])
def test_a_malformed_policy_request_is_refused(tmp_path, req):
    reply = _signer(tmp_path).handle(req, {"mode": "x"})
    assert reply == {"ok": False, "error": "bad_request", "detail": reply["detail"]}
