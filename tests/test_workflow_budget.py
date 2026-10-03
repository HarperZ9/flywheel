"""Workflow and plan runs carry the run budget and settle it like agent.run.

workflow.run, the /api/workflow route and plan.run all go through
run_workflow, which drives the router agent once per stage. One budget covers
the whole workflow run: every stage's model calls and tool actions are charged
to it, each stage is settled when it returns, and a stop is recorded in the
chained receipt instead of being lost in an error.
"""
from harness import workflows
from harness.run_budget import DEFAULTS


class _Out:
    def __init__(self, text, usage=None):
        self.text, self.usage, self.model_ref = text, usage, "stub"


class _Proposer:
    """Canned answers, each reporting `tokens` of usage the way direct API
    proposers normalize it."""

    def __init__(self, texts, tokens=0):
        self.texts, self.tokens, self.calls = list(texts), tokens, 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        self.calls += 1
        text = self.texts.pop(0) if self.texts else "done"
        return _Out(text, {"prompt": self.tokens, "completion": 0, "total": self.tokens})


class _LimitedProvider:
    """A provider that answers 2xx with a rate-limit error body."""

    def generate(self, prompt, **kwargs):
        error = RuntimeError("stub returned 200: rate limited")
        error.status, error.body = 200, {"error": {"type": "rate_limit_error"}}
        raise error


def _stages(doc):
    return {step["name"]: step for step in doc["steps"]}


def test_every_stage_is_charged_to_one_budget_and_carries_its_record(tmp_path):
    stub = _Proposer(["the draft", "the critique"], tokens=1_000)
    doc = workflows.run_workflow("research-brief", "goal", "stub", root=str(tmp_path),
                                 proposer=stub)
    assert doc["status"] == "COMPLETED"
    report = doc["steps"][-1]["run_budget"]
    assert report["used"]["model_calls"] == stub.calls == 2
    assert report["used"]["usage_tokens"] == 2_000
    assert report["limits"]["model_calls"] == 6 + 3
    assert report["limits"]["usage_tokens"] == DEFAULTS["max_usage_tokens"]
    assert workflows.recompute_chain(doc) == doc["chain_hash"]


def test_a_stage_past_the_token_limit_stops_the_workflow_and_says_why(tmp_path):
    # authorized=True is how the /api/workflow route and plan.run call it.
    for authorized in (False, True):
        doc = workflows.run_workflow("research-brief", "goal", "stub", root=str(tmp_path),
                                     proposer=_Proposer(["a", "b"], tokens=150_000),
                                     authorized=authorized)
        assert doc["status"] == "FAILED"
        stopped = _stages(doc)["critique"]
        assert stopped["status"] == "STOPPED"
        assert stopped["note"] == "AGENT_RUN_BUDGET_EXHAUSTED: usage_tokens"
        assert stopped["run_budget"]["tripped"] == "usage_tokens"
        assert workflows.recompute_chain(doc) == doc["chain_hash"]


def test_a_limit_error_in_a_2xx_response_is_recorded_as_a_false_success(tmp_path):
    doc = workflows.run_workflow("research-brief", "goal", "stub", root=str(tmp_path),
                                 proposer=_LimitedProvider())
    assert doc["status"] == "FAILED"
    report = doc["steps"][0]["run_budget"]
    assert report["false_success_count"] == 1
    assert report["limit_signal_steps"][0]["match"] == "rate_limit_error"


def test_a_verify_stage_with_no_test_command_still_carries_the_budget_record(tmp_path):
    for allow_exec, test_cmd in ((False, None), (True, None), (False, "pytest -q")):
        doc = workflows.run_workflow("code-change", "goal", "stub", root=str(tmp_path),
                                     proposer=_Proposer(["plan", "applied"]),
                                     allow_exec=allow_exec, test_cmd=test_cmd)
        assert doc["status"] == "UNVERIFIED"
        verify = _stages(doc)["verify"]
        assert verify["status"] == "UNVERIFIABLE"
        assert [("run_budget" in step) for step in doc["steps"]] == [True] * 3
        assert verify["run_budget"]["used"]["model_calls"] == 2
