"""Known-answer and planted-failure tests for Wave 36A AgentWorkspace, Delegation, and Valves."""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

import pytest

from accountable_surface import interop_mcp as mcp
from accountable_surface.agent_workspace import (
    AgentWorkspace,
    CallableEffectorAdapter,
    WorkspaceStep,
    verify_workspace_session_receipt,
)
from accountable_surface.approval_valve import (
    CheckpointTamperError,
    load_valve_checkpoint,
    resolve_valve_checkpoint,
    save_valve_checkpoint,
)
from accountable_surface.delegation import (
    MandateEnforcer,
    MandateScopeError,
    issue_mandate,
    sub_delegate_mandate,
)
from accountable_surface.keystore import MemoryKeystore
from accountable_surface.native_win32_backend import NativeWin32Backend
from accountable_surface.oauth_broker import OAuthTokenBroker
from accountable_surface.operator_policy import AuthorityGrant, sha256_prefixed
from accountable_surface.request_signer import AccountableRequestSigner

PKG_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PKG_ROOT / "src" / "accountable_surface"
NATIVE_DIR = PKG_ROOT / "native"
SIGNING_KEY = "owner-mandate-signing-key-wave36a!"


def _load_verify_journal_fn():
    spec = importlib.util.spec_from_file_location("verify_journal_w36a", PKG_ROOT / "verify_journal.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.verify_journal


def test_wave36a_module_size_function_budgets_and_hygiene():
    for name in ("delegation.py", "approval_valve.py", "agent_workspace.py"):
        text = (SRC_DIR / name).read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 280, f"{name} exceeded 280 LOC ({len(text.splitlines())})"
        assert "\u2014" not in text, f"em dash found in {name}"
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                span = (node.end_lineno or node.lineno) - node.lineno + 1
                assert span <= 50, f"{name}:{node.name} exceeded 50 lines ({span})"
    bld = (NATIVE_DIR / "agent_workspace.bld").read_text(encoding="utf-8")
    assert len(bld.splitlines()) <= 280 and "\u2014" not in bld


def test_multistep_delegated_workspace_end_to_end_and_receipt_verification(tmp_path):
    ws_root = tmp_path / "ws"
    mandate = issue_mandate(
        mandate_id="mnd-001", principal_id="owner-1", agent_id="agent-alpha",
        signing_key=SIGNING_KEY, allowed_roots=(str(ws_root),),
        allowed_hosts=("api.example.org",), allowed_apps=("workspace-editor",),
        allowed_actions=("fs.write", "win32.observe", "oauth.use_token", "oauth.sign_request", "api.post"),
        max_actions=10, max_mutations=6, max_budget_units=40, issued_at=1000.0, ttl_seconds=3600.0,
    )
    enforcer = MandateEnforcer(signing_key=SIGNING_KEY)
    ws = AgentWorkspace(workspace_id="ws-e2e", root_dir=ws_root, mandate=mandate, enforcer=enforcer)

    ks = MemoryKeystore(namespace="ws")
    ks.put("sign_key", "super-secret-signing-key-36a")
    broker = OAuthTokenBroker(ks, allowed_hosts=("api.example.org",), allowed_scopes=("deploy.read",))
    broker.store_token_record("oauth_tok", access_token="tok-live-36a", expires_at=5000.0, scopes=("deploy.read",))
    signer = AccountableRequestSigner(keystore=ks, allowed_hosts=("api.example.org",), allowed_methods=("POST",))
    win32 = NativeWin32Backend(ws_root, AuthorityGrant(allowed_roots=(str(ws_root),)), dll_path=tmp_path / "none.dll")

    ws.register_effector("win32", CallableEffectorAdapter(exec_fn=lambda _s: {"ok": True, **win32.observe_native_desktop()}))
    ws.register_effector("oauth", CallableEffectorAdapter(exec_fn=lambda s: {"ok": bool(broker.get_valid_access_token("oauth_tok", host=s.host, required_scopes=("deploy.read",), now=1200.0))}))
    ws.register_effector("signer", CallableEffectorAdapter(exec_fn=lambda s: {"ok": True, "sig_digest": signer.sign_rfc9421(method="POST", url=s.target, body=b"ok", key_id="k1", key_handle="sign_key", created=1200)["signature_digest"]}))

    draft = ws_root / "scratch" / "plan.json"
    draft_bytes = b'{"status":"ready"}\n'
    steps = [
        WorkspaceStep("s3", "signer", "oauth.sign_request", "https://api.example.org/v1/notify", depends_on=("s2",), host="api.example.org"),
        WorkspaceStep("s1", "filesystem", "fs.write", str(draft), params={"content": draft_bytes}, mutates=True, expected_digest=sha256_prefixed(draft_bytes)),
        WorkspaceStep("s2", "oauth", "oauth.use_token", "oauth_tok", depends_on=("s1",), host="api.example.org"),
        WorkspaceStep("s0", "win32", "win32.observe", "desktop", app="workspace-editor"),
    ]
    res = ws.run_plan(steps, now=1200.0)
    assert res["status"] == "COMPLETED" and not res["rolled_back"]
    ids = [st["step_id"] for st in res["receipt"]["steps"]]
    assert set(ids) == {"s0", "s1", "s2", "s3"}
    assert ids.index("s1") < ids.index("s2") < ids.index("s3")

    ok, errs = verify_workspace_session_receipt(res["receipt"], journal_path=ws.journal_path)
    assert ok and not errs
    verify_journal = _load_verify_journal_fn()
    label, detail = verify_journal(ws.journal_path.read_text(encoding="utf-8"))
    assert label == "MATCH", detail

    # 1-byte tamper on receipt trips offline verification
    tampered = dict(res["receipt"])
    tampered["detail"] = "tampered"
    t_ok, t_errs = verify_workspace_session_receipt(tampered, journal_path=ws.journal_path)
    assert not t_ok and t_errs

    # MCP read-only protocol tools round-trip cleanly
    r_stat = mcp.handle_request({"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {"name": "accountable-surface.workspace_status", "arguments": {"workspace_dir": str(ws_root)}}})
    stat_body = json.loads(r_stat["result"]["content"][0]["text"])
    assert stat_body["has_journal"] and stat_body["has_receipt"]
    r_ver = mcp.handle_request({"jsonrpc": "2.0", "id": 12, "method": "tools/call", "params": {"name": "accountable-surface.workspace_verify_session", "arguments": {"receipt_path": str(ws.receipt_path), "journal_path": str(ws.journal_path)}}})
    ver_body = json.loads(r_ver["result"]["content"][0]["text"])
    assert ver_body["ok"] and ver_body["verdict"] == "MATCH"


def test_planted_scope_widening_budget_exhaustion_and_revocation_refused(tmp_path):
    root = tmp_path / "ws"
    parent = issue_mandate(
        mandate_id="mnd-parent", principal_id="owner-1", agent_id="agent-parent",
        signing_key=SIGNING_KEY, allowed_roots=(str(root),),
        allowed_hosts=("api.example.org",), allowed_apps=("editor",),
        allowed_actions=("fs.read", "fs.write"), max_actions=3, max_mutations=2, max_budget_units=10,
        issued_at=1000.0, ttl_seconds=600.0,
    )
    child = sub_delegate_mandate(
        parent, mandate_id="mnd-child", child_agent_id="agent-child", signing_key=SIGNING_KEY,
        allowed_roots=(str(root / "sub"),), allowed_actions=("fs.read",), max_actions=2, max_mutations=1, max_budget_units=5,
        expires_at=1400.0, issued_at=1000.0,
    )
    assert child.verify_signature(SIGNING_KEY) and child.parent_mandate_id == "mnd-parent"

    # Planted widening attempts MUST all fail closed
    with pytest.raises(MandateScopeError):
        sub_delegate_mandate(parent, mandate_id="w1", child_agent_id="c", signing_key=SIGNING_KEY, allowed_actions=("fs.read", "api.post"))
    with pytest.raises(MandateScopeError):
        sub_delegate_mandate(parent, mandate_id="w2", child_agent_id="c", signing_key=SIGNING_KEY, allowed_hosts=("evil.example.net",))
    with pytest.raises(MandateScopeError):
        sub_delegate_mandate(parent, mandate_id="w3", child_agent_id="c", signing_key=SIGNING_KEY, allowed_roots=(str(tmp_path),))
    with pytest.raises(MandateScopeError):
        sub_delegate_mandate(parent, mandate_id="w4", child_agent_id="c", signing_key=SIGNING_KEY, max_budget_units=99)
    with pytest.raises(MandateScopeError):
        sub_delegate_mandate(parent, mandate_id="w5", child_agent_id="c", signing_key=SIGNING_KEY, expires_at=9999.0)

    # Budget exhaustion + expiry + cascading parent revocation
    enforcer = MandateEnforcer(signing_key=SIGNING_KEY)
    assert enforcer.authorize_and_consume(child, action_kind="fs.read", target=str(root / "sub" / "a.txt"), cost=3, now=1100.0)[0]
    ok_over, _ = enforcer.authorize_and_consume(child, action_kind="fs.read", target=str(root / "sub" / "a.txt"), cost=3, now=1100.0)
    assert not ok_over
    ok_exp, _ = enforcer.authorize_and_consume(child, action_kind="fs.read", target=str(root / "sub" / "a.txt"), cost=1, now=1500.0)
    assert not ok_exp
    enforcer.revoke("mnd-parent", reason="emergency stop")
    ok_rev, reason = enforcer.authorize_and_consume(child, action_kind="fs.read", target=str(root / "sub" / "a.txt"), cost=1, now=1100.0)
    assert not ok_rev and "revoked" in reason


def test_planted_mid_plan_verification_drift_triggers_reverse_order_rollback(tmp_path):
    ws_root = tmp_path / "ws_rb"
    f1, f2 = ws_root / "scratch" / "one.txt", ws_root / "scratch" / "two.txt"
    f1.parent.mkdir(parents=True, exist_ok=True)
    f1.write_bytes(b"original-one")
    rollback_order: list[str] = []

    mandate = issue_mandate(
        mandate_id="mnd-rb", principal_id="owner-1", agent_id="agent-rb",
        signing_key=SIGNING_KEY, allowed_roots=(str(ws_root),),
        allowed_actions=("fs.write", "api.stage"), max_actions=10, max_mutations=10, issued_at=1000.0,
    )
    ws = AgentWorkspace(workspace_id="ws-rb", root_dir=ws_root, mandate=mandate, enforcer=MandateEnforcer(signing_key=SIGNING_KEY))
    ws.register_effector(
        "api",
        CallableEffectorAdapter(
            exec_fn=lambda _s: {"ok": True},
            perceive_fn=lambda _t: {"digest": "sha256:drifted-actual"},
            rollback_fn=lambda s, _snap: rollback_order.append(s.step_id) or True,
        ),
    )
    steps = [
        WorkspaceStep("step_1", "filesystem", "fs.write", str(f1), params={"content": b"mutated-one"}, mutates=True),
        WorkspaceStep("step_2", "filesystem", "fs.write", str(f2), params={"content": b"new-two"}, depends_on=("step_1",), mutates=True),
        WorkspaceStep("step_3_drift", "api", "api.stage", "staging", depends_on=("step_2",), mutates=True, expected_digest="sha256:expected-clean"),
    ]
    res = ws.run_plan(steps, now=1100.0)
    assert res["status"] == "ROLLED_BACK"
    assert res["rolled_back"] == ["step_3_drift", "step_2", "step_1"]
    assert rollback_order == ["step_3_drift"]
    assert f1.read_bytes() == b"original-one" and not f2.exists()
    ok, errs = verify_workspace_session_receipt(res["receipt"], journal_path=ws.journal_path)
    assert ok and not errs


def test_planted_approval_valve_checkpoint_suspend_resume_deny_and_hard_exclusions(tmp_path):
    ws_root = tmp_path / "ws_valve"
    mandate = issue_mandate(
        mandate_id="mnd-valve", principal_id="owner-1", agent_id="agent-v",
        signing_key=SIGNING_KEY, allowed_roots=(str(ws_root),),
        allowed_actions=("fs.write", "api.send_external"), max_actions=10, max_mutations=10, issued_at=1000.0,
    )
    sent: list[str] = []
    ws = AgentWorkspace(workspace_id="ws-valve", root_dir=ws_root, mandate=mandate, enforcer=MandateEnforcer(signing_key=SIGNING_KEY))
    ws.register_effector("api", CallableEffectorAdapter(exec_fn=lambda s: sent.append(s.target) or {"ok": True}))

    draft = ws_root / "scratch" / "draft.txt"
    steps = [
        WorkspaceStep("prep", "filesystem", "fs.write", str(draft), params={"content": b"draft-v1"}, mutates=True),
        WorkspaceStep("send", "api", "api.send_external", "partner@example.org", depends_on=("prep",), mutates=True, reversible=False, requires_approval=True),
    ]
    paused = ws.run_plan(steps, now=1100.0)
    assert paused["status"] == "SUSPENDED_NEEDS_HUMAN" and not sent
    cp_path = Path(paused["checkpoint_path"])
    assert cp_path.stat().st_size < 2048

    # Tampered checkpoint rejected fail-closed
    bad_cp = tmp_path / "bad_cp.json"
    bad_cp.write_text(cp_path.read_text(encoding="utf-8").replace("partner@example.org", "attacker@example.net"), encoding="utf-8")
    with pytest.raises(CheckpointTamperError):
        load_valve_checkpoint(bad_cp)

    # Owner approval resumes deterministically from exact step
    approved_cp = resolve_valve_checkpoint(load_valve_checkpoint(cp_path), approved=True, owner_decision_id="owner-ok-1", note="verified")
    save_valve_checkpoint(approved_cp, cp_path)
    resumed = ws.resume_from_checkpoint(load_valve_checkpoint(cp_path), steps, now=1150.0)
    assert resumed["status"] == "COMPLETED" and sent == ["partner@example.org"]

    # Owner denial rolls back prior reversible steps
    ws_deny = AgentWorkspace(workspace_id="ws-deny", root_dir=tmp_path / "ws_deny", mandate=issue_mandate(
        mandate_id="mnd-deny", principal_id="owner-1", agent_id="agent-d", signing_key=SIGNING_KEY,
        allowed_roots=(str(tmp_path / "ws_deny"),), allowed_actions=("fs.write", "api.send_external"), issued_at=1000.0,
    ), enforcer=MandateEnforcer(signing_key=SIGNING_KEY))
    ws_deny.register_effector("api", CallableEffectorAdapter(exec_fn=lambda _s: {"ok": True}))
    d_file = tmp_path / "ws_deny" / "scratch" / "temp.txt"
    d_steps = [
        WorkspaceStep("prep", "filesystem", "fs.write", str(d_file), params={"content": b"temp"}, mutates=True),
        WorkspaceStep("send", "api", "api.send_external", "x@example.org", depends_on=("prep",), mutates=True, requires_approval=True),
    ]
    p2 = ws_deny.run_plan(d_steps, now=1100.0)
    denied_cp = resolve_valve_checkpoint(p2["checkpoint"], approved=False, owner_decision_id="owner-no-1", note="abort")
    r_deny = ws_deny.resume_from_checkpoint(denied_cp, d_steps, now=1120.0)
    assert r_deny["status"] == "DENIED_ROLLED_BACK" and r_deny["rolled_back"] == ["prep"] and not d_file.exists()

    # Hard exclusions refused at issuance, execution, AND MCP workspace_plan
    for bad_act in ("browser.solve_captcha", "oauth.bypass_oauth", "mail.mass_outreach", "browser.anti_bot_stealth"):
        with pytest.raises(MandateScopeError):
            issue_mandate(mandate_id="m-bad", principal_id="o", agent_id="a", signing_key=SIGNING_KEY, allowed_actions=(bad_act,))
    bad_exec = ws.run_plan([WorkspaceStep("bad", "api", "browser.solve_captcha", "portal")], now=1160.0)
    assert bad_exec["status"] == "REFUSED_EXCLUDED"

    r_plan = mcp.handle_request({"jsonrpc": "2.0", "id": 13, "method": "tools/call", "params": {"name": "accountable-surface.workspace_plan", "arguments": {"steps": [{"step_id": "x", "action_kind": "browser.solve_captcha", "target": "form"}]}}})
    plan_body = json.loads(r_plan["result"]["content"][0]["text"])
    assert not plan_body["ok"] and plan_body["decision"] == "DENY"
