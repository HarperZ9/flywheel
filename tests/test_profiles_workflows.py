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
    assert doc["schema"] == "flywheel.profiles/v1"
    names = {p["name"] for p in doc["profiles"]}
    assert {"code", "design", "work", "cowork", "chat"} <= names
    for p in doc["profiles"]:
        wf = p["workflow"]
        assert wf is None or wf in workflows.WORKFLOWS
        assert set(p["gates"]) == {"allow_write", "allow_exec", "allow_mcp"}


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
