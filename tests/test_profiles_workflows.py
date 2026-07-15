"""Profiles and workflows must be honest by construction: profile gates are
requests not grants, every profile's workflow exists, a workflow's chain hash
moves when a step's output moves, a verify step without an exec grant reports
UNVERIFIABLE, and a step failure fails the run instead of hiding."""

import json

from harness import workflows
from harness.profiles import PROFILES, get_profile, profile_roster


class _StubOut:
    def __init__(self, text):
        self.text = text
        self.model_ref = "stub"


class _StubProposer:
    """Returns canned final answers (no TOOL lines), one per call."""

    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        self.calls += 1
        text = self.texts.pop(0) if self.texts else "done"
        return _StubOut(text)


def test_profile_roster_shape_and_workflow_bindings():
    doc = profile_roster()
    assert doc["schema"] == "flywheel.profiles/v2"
    names = {p["name"] for p in doc["profiles"]}
    # Deepened set now includes the academy and the training harness.
    assert {"code", "design", "work", "cowork", "learn", "train", "chat"} <= names
    for p in doc["profiles"]:
        wf = p["workflow"]
        assert wf is None or wf in workflows.WORKFLOWS
        assert set(p["gates"]) == {"allow_write", "allow_exec", "allow_mcp"}


def test_profiles_are_deep_not_just_named():
    """Every profile carries real, differentiated capability: a tool set, a
    planning template, an index scope, and a surface -- not just a prompt."""
    doc = profile_roster()
    for p in doc["profiles"]:
        for field in ("tools", "planning", "surface", "index_scope"):
            assert field in p, f"{p['name']} missing {field}"
    by_name = {p["name"]: p for p in doc["profiles"]}
    # Differentiation: code plans a change, learn plans mastery, work plans
    # research -- their planning templates are genuinely distinct.
    assert by_name["code"]["planning"] != by_name["learn"]["planning"]
    assert "mastery verdict" in by_name["learn"]["planning"]
    assert "duel" in by_name["train"]["planning"]
    # Only code requests write+exec; the rest are read-first.
    assert by_name["code"]["gates"]["allow_write"] is True
    assert by_name["design"]["gates"]["allow_write"] is False


def test_only_code_profile_requests_write_and_exec():
    for name, p in PROFILES.items():
        if name == "code":
            assert p["gates"]["allow_write"] and p["gates"]["allow_exec"]
        else:
            assert not p["gates"]["allow_write"]
            assert not p["gates"]["allow_exec"]
    assert get_profile("nonexistent") is None


def test_workflow_runs_steps_in_order_and_chains_receipt(tmp_path):
    stub = _StubProposer(["the plan", "critique of the plan"])
    doc = workflows.run_workflow("research-brief", "test goal", "stub-endpoint",
                                 root=str(tmp_path), run_root=tmp_path,
                                 proposer=stub)
    assert doc["status"] == "COMPLETED"
    assert [s["name"] for s in doc["steps"]] == ["draft", "critique"]
    assert doc["steps"][0]["excerpt"] == "the plan"
    # {prev} substitution: the critique step saw the draft (2 calls total).
    assert stub.calls == 2
    # The run persisted a receipt under the run root.
    runs = list((tmp_path / "workflow_runs").glob("*.json"))
    assert len(runs) == 1
    persisted = json.loads(runs[0].read_text(encoding="utf-8"))
    assert persisted["chain_hash"] == doc["chain_hash"]


def test_chain_hash_moves_when_step_output_moves(tmp_path):
    a = workflows.run_workflow("research-brief", "goal", "e", root=str(tmp_path),
                               proposer=_StubProposer(["draft A", "review"]))
    b = workflows.run_workflow("research-brief", "goal", "e", root=str(tmp_path),
                               proposer=_StubProposer(["draft B", "review"]))
    assert a["chain_hash"] != b["chain_hash"]


def test_verify_without_exec_grant_is_unverifiable(tmp_path):
    stub = _StubProposer(["plan", "applied"])
    doc = workflows.run_workflow("code-change", "fix it", "e", root=str(tmp_path),
                                 allow_write=False, allow_exec=False,
                                 proposer=stub)
    verify = doc["steps"][-1]
    assert verify["status"] == "UNVERIFIABLE"
    assert "nothing was executed" in verify["note"]
    assert doc["status"] == "UNVERIFIED"


def test_unknown_workflow_is_named_not_guessed(tmp_path):
    doc = workflows.run_workflow("no-such-flow", "goal", "e", root=str(tmp_path))
    assert doc["status"] == "UNKNOWN_WORKFLOW"
    assert "research-brief" in doc["known"]


def test_step_error_fails_the_run(tmp_path):
    class _Boom:
        def generate(self, prompt, *, seed, temperature, max_new_tokens,
                     system=""):
            raise RuntimeError("provider down")

    doc = workflows.run_workflow("research-brief", "goal", "e",
                                 root=str(tmp_path), proposer=_Boom())
    assert doc["status"] == "FAILED"
    assert doc["steps"][0]["status"] == "ERROR"
    assert "provider down" in doc["steps"][0]["note"]


def _fake_agent_results(results):
    """A run_router_agent stand-in returning canned per-call result dicts, so
    the workflow's cross-stage gating can be exercised without a live agent."""
    seq = list(results)
    def fake(goal, endpoint, **kw):
        return seq.pop(0)
    return fake


def test_dirty_integrity_stage_is_not_recorded_done(tmp_path, monkeypatch):
    # An apply stage whose trajectory integrity is dirty (the agent edited the
    # file that grades it) must fail the run, not be stamped DONE and laundered
    # to VERIFIED by a later clean verify stage.
    from harness import workflows
    monkeypatch.setattr(workflows, "run_router_agent", _fake_agent_results([
        {"final": "planned", "verified": True,
         "integrity": {"clean": True}, "checkpoint": "c0"},
        {"final": "applied", "verified": True,
         "integrity": {"clean": False}, "checkpoint": "c1"},  # dirty!
        {"final": "ran tests", "verified": True,
         "integrity": {"clean": True}, "tests_pass_trusted": True,
         "checkpoint": "c2"},
    ]))
    doc = workflows.run_workflow("code-change", "fix it", "e",
                                 root=str(tmp_path), allow_write=True,
                                 allow_exec=True, test_cmd="pytest",
                                 proposer=_StubProposer([]))
    assert doc["status"] == "FAILED"
    apply_step = next(s for s in doc["steps"] if s["name"] == "apply")
    assert apply_step["status"] == "FAILED"
    assert doc["status"] != "VERIFIED"


def test_unverified_ledger_stage_is_not_recorded_done(tmp_path, monkeypatch):
    from harness import workflows
    monkeypatch.setattr(workflows, "run_router_agent", _fake_agent_results([
        {"final": "planned", "verified": False,  # ledger did not verify
         "integrity": {"clean": True}, "checkpoint": "c0"},
    ]))
    doc = workflows.run_workflow("code-change", "fix it", "e",
                                 root=str(tmp_path), allow_write=True,
                                 allow_exec=True, test_cmd="pytest",
                                 proposer=_StubProposer([]))
    assert doc["status"] == "FAILED"
    assert doc["steps"][0]["status"] == "FAILED"


def test_failed_run_receipt_cannot_be_relabeled_without_breaking_the_chain(
        tmp_path):
    # Take a FAILED run, delete the trailing ERROR step and flip status to
    # COMPLETED: recomputing the chain must NOT reproduce the stored hash.
    class _Boom:
        def generate(self, prompt, *, seed, temperature, max_new_tokens,
                     system=""):
            raise RuntimeError("provider down")
    doc = workflows.run_workflow("research-brief", "goal", "e",
                                 root=str(tmp_path), proposer=_Boom())
    assert doc["status"] == "FAILED"
    recomputed = workflows.recompute_chain(doc)
    assert recomputed == doc["chain_hash"]        # the honest receipt re-derives
    tampered = dict(doc, status="COMPLETED",
                    steps=[s for s in doc["steps"] if s["status"] != "ERROR"])
    assert workflows.recompute_chain(tampered) != doc["chain_hash"]


def test_status_and_header_are_bound_into_the_chain(tmp_path):
    doc = workflows.run_workflow("research-brief", "goal", "e",
                                 root=str(tmp_path),
                                 proposer=_StubProposer(["draft", "review"]))
    assert workflows.recompute_chain(doc) == doc["chain_hash"]
    # flipping the final status alone breaks the chain
    assert workflows.recompute_chain(dict(doc, status="FAILED")) != doc["chain_hash"]
    # rewriting the endpoint alone breaks the chain
    assert workflows.recompute_chain(dict(doc, endpoint="other")) != doc["chain_hash"]


def test_roster_flags_a_hand_flipped_run_as_tampered(tmp_path):
    import json as _j
    doc = workflows.run_workflow("research-brief", "goal", "e",
                                 root=str(tmp_path),
                                 proposer=_StubProposer(["draft", "review"]),
                                 run_root=str(tmp_path))
    runs_dir = tmp_path / "workflow_runs"
    receipt = next(runs_dir.glob("*.json"))
    d = _j.loads(receipt.read_text(encoding="utf-8"))
    d["status"] = "VERIFIED"                       # hand-flip
    receipt.write_text(_j.dumps(d), encoding="utf-8")
    roster = workflows.workflow_roster(run_root=str(tmp_path))
    row = roster["runs"][0]
    assert row["chain_ok"] is False
    assert row["status"] == "TAMPERED"
