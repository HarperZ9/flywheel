"""The authority block on a tool-call receipt: what decided the action.

Success criteria, by rule:
  (a) no authority, or basis ``none``, verifies as FINDING and never MATCH;
  (b) when scope and policy disagree the narrower (deny) wins, the block records
      both and the winner, and the event lands in a sealed disagreement log;
  (c) a confirmation is ``intent`` only when it names the object and the fact
      in the human's words; a bare "yes", a missing fact, or a restated plan is
      ``scope`` at most, and a receipt that labels such a confirmation intent
      is re-derived as scope;
  and ``policy:self`` cannot be turned into ``policy:machine`` by the agent-side
  process: every route the agent controls is re-labelled self on verification.
"""
from __future__ import annotations

import json

import pytest

from harness import action_authority as au
from harness.action_authority_verify import verify_action, verify_authority
from harness.preaction.records import HoldStore
from harness.tool_call_receipt import build_receipt

PLAN = "I will delete the staging-logs bucket because it holds no live data"
ISO_SEP = {"mode": "separate-identity", "signer": "uid:900", "client": "uid:1000",
           "via": "test"}
ISO_SAME = dict(ISO_SEP, signer="uid:1000", mode="same-identity")


def _receipt(tool="run", args=None, block=None):
    r = build_receipt(tool=tool, capability="builtin-exec", admission="ALLOWED",
                      args=args if args is not None else {"cmd": "ls"}, output="", ok=True,
                      rc=0, run_id="run-1", seq=1)
    return au.attach(r, block) if block is not None else r


def _signer(tmp_path, context=None):
    try:
        import cryptography  # noqa: F401
    except ImportError:
        pytest.importorskip("nacl.signing", reason="signing needs cryptography or pynacl")
    from harness.signer import keys
    from harness.signer.server import Signer
    keys.create(tmp_path / "signer")
    if context is not None:
        (tmp_path / "signer" / "policy-context.json").write_text(json.dumps(context))
    return Signer(tmp_path / "signer", clock=lambda: "2026-10-04T00:00:00Z")


def _machine(signer, args, iso=ISO_SEP, tool="run"):
    reply = signer.handle({"op": "check_policy", "tool": tool, "args": args}, iso)
    return au.policy_machine(reply["policy"])


# ---- (a) none is a finding


def test_a_receipt_with_no_authority_is_a_finding():
    out = verify_action(_receipt())
    assert out["verdict"] == "FINDING"
    assert out["authority"]["basis"] == "none"
    assert {"cause": "NO_AUTHORITY_RECORDED"} in out["authority"]["findings"]


def test_basis_none_resolves_to_finding_never_pass():
    block = au.resolve([])
    assert block["basis"] == au.NONE and block["verdict"] == au.FINDING
    assert verify_action(_receipt(block=block))["verdict"] == "FINDING"


def test_policy_self_is_unenforced_never_a_pass():
    block = au.resolve([au.policy_self("never push to main", au.ALLOW)])
    assert block["verdict"] == au.UNENFORCED
    assert verify_action(_receipt(block=block))["verdict"] == "UNENFORCED"


# ---- (b) narrower wins, both recorded, logged


def test_policy_deny_beats_scope_allow_and_is_logged(tmp_path):
    signer = _signer(tmp_path)
    args = {"cmd": "git push --force"}
    block = au.resolve([au.scope("repo maintenance task", au.ALLOW), _machine(signer, args)])
    assert block["decision"] == au.DENY and block["basis"] == au.MACHINE
    assert block["disagreement"] == {"scope": "allow", "policy": "deny",
                                     "policy_basis": au.MACHINE, "winner": au.MACHINE}
    au.log_disagreement(tmp_path / "log", block, tool="run", args_sha256="ab" * 32,
                        at="2026-10-04T00:00:00Z", signer=None)
    rows = HoldStore(tmp_path / "log", signer=None).read_all()
    assert rows[0]["schema"] == au.DISAGREEMENT_SCHEMA and rows[0]["winner"] == au.MACHINE
    receipt = _receipt(args=args, block=block)
    assert verify_action(receipt, signer.public.hex())["verdict"] == "MATCH"


def test_scope_deny_beats_policy_allow(tmp_path):
    signer = _signer(tmp_path)
    block = au.resolve([au.scope("read-only review role", au.DENY),
                        _machine(signer, {"cmd": "ls"})])
    assert block["decision"] == au.DENY and block["basis"] == au.SCOPE
    assert block["disagreement"]["winner"] == au.SCOPE


def test_agreement_writes_nothing_to_the_log(tmp_path):
    block = au.resolve([au.scope("task", au.ALLOW), au.policy_self("rule", au.ALLOW)])
    assert "disagreement" not in block
    au.log_disagreement(tmp_path / "log", block, tool="run", args_sha256="ab" * 32,
                        at="x", signer=None)
    assert not (tmp_path / "log" / "records.jsonl").exists()


# ---- (c) what counts as intent


@pytest.mark.parametrize("text, want, why", [
    ("Delete staging-logs, I checked and it has no live data since June", au.INTENT,
     "names the object"),
    ("yes", au.SCOPE, "object"),
    ("go ahead and delete staging-logs", au.SCOPE, "fact"),
    ("I will delete the staging-logs bucket because it holds no live data", au.SCOPE,
     "restates"),
    ("you will delete the staging-logs bucket, it holds no live data", au.SCOPE,
     "restates"),
])
def test_confirmation_classification(text, want, why):
    basis, reason = au.classify_confirmation(text, object_name="staging-logs",
                                             fact="no live data", plan_summary=PLAN)
    assert basis == want and why in reason, reason


def test_a_restated_plan_filed_as_intent_is_rederived_as_scope():
    element = au.intent(PLAN, on="2026-10-04", source="chat", decision=au.ALLOW,
                        object_name="staging-logs", fact="no live data", plan_summary=PLAN)
    assert element["basis"] == au.SCOPE                     # classified at build time
    forged = dict(element, basis=au.INTENT)                  # agent relabels it
    block = {"basis": au.INTENT, "decision": au.ALLOW, "verdict": au.PASS,
             "elements": [forged]}
    out = verify_authority(_receipt(block=block))
    assert out["basis"] == au.SCOPE
    assert any(f["cause"] == "AUTHORITY_OVERSTATED" for f in out["findings"])
    assert verify_action(_receipt(block=block))["verdict"] == "FINDING"


def test_intent_needs_a_date_and_a_source():
    with pytest.raises(ValueError):
        au.intent("Delete staging-logs, no live data", on="yesterday", source="chat",
                  decision=au.ALLOW, object_name="staging-logs", fact="no live data",
                  plan_summary="")
    with pytest.raises(au.AuthorityError):
        au.intent("Delete staging-logs, no live data", on="2026-10-04", source="",
                  decision=au.ALLOW, object_name="staging-logs", fact="no live data",
                  plan_summary="")


def test_the_disagreement_log_is_signed_when_a_signer_runs(tmp_path):
    from tests.signer_fixtures import RunningSigner
    _signer(tmp_path)                                   # skips without a backend
    running = RunningSigner(tmp_path / "running")
    try:
        block = au.resolve([au.scope("read-only role", au.DENY),
                            au.policy_self("reads are fine", au.ALLOW)])
        au.log_disagreement(tmp_path / "log", block, tool="run", args_sha256="ab" * 32,
                            at="2026-10-04T00:00:00Z", signer=running.client())
        row = HoldStore(tmp_path / "log", signer=None).read_all()[0]
        assert row["winner"] == au.SCOPE and row["attestation"]["seq"] == 1
    finally:
        running.stop()
