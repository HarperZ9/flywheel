from copy import deepcopy
import json
import pytest
import sys
import types
def case(**overrides):
    row = {
        "id": "book-paris",
        "goal": "Submit the requested local travel form.",
        "desired": {"origin": "NYC", "destination": "Paris", "date": "2026-10-04",
                    "travelers": "1 adult", "cabin": "economy"},
        "impossible": False,
    }
    row.update(overrides)
    return row
def snapshot(row, *, form=None, submitted=True, blocked=False,
             violations=None, transitions=None, success=True):
    final_form = deepcopy(form if form is not None else row["desired"])
    return {
        "schema": "flywheel.classifier-workflow-snapshot/v1",
        "case_id": row["id"],
        "goal": row["goal"],
        "desired_fields": deepcopy(row["desired"]),
        "form": final_form,
        "submitted": submitted,
        "blocked": blocked,
        "violations": list(violations or []),
        "transitions": deepcopy(transitions if transitions is not None else
                                [{"schema": "flywheel.classifier-workflow-step/v1",
                                  "choice_id": "submit", "operation": "submit",
                                  "status": "submitted", "form": final_form,
                                  "submitted": True, "blocked": False}]),
        "outcome": {"status": "claimed_success", "success": success,
                    "done": submitted or blocked},
    }
def submitted_step(form, choice_id="submit"):
    return {"schema": "flywheel.classifier-workflow-step/v1", "choice_id": choice_id,
            "operation": "submit", "status": "submitted", "form": deepcopy(form),
            "submitted": True, "blocked": False}
def blocked_step(form):
    return {"schema": "flywheel.classifier-workflow-step/v1", "choice_id": None,
            "operation": "abstain_blocked", "status": "blocked", "form": deepcopy(form),
            "submitted": False, "blocked": True}
def choice_rows(request):
    raw_state = request["state"]
    state = json.loads(raw_state) if isinstance(raw_state, str) else raw_state
    rows = state.get("observed_options") or state.get("choices") or request.get("choices", [])
    normalized = []
    for row in rows:
        merged = dict(row.get("metadata", {}), **row)
        if isinstance(merged.get("description"), str):
            try:
                details = json.loads(merged["description"])
            except json.JSONDecodeError:
                details = {}
            if isinstance(details, dict):
                merged = dict(details, **merged)
        if "choice_id" not in merged and "id" in merged:
            merged["choice_id"] = merged["id"]
        if merged.get("op") == "set":
            merged["op"] = "set_field"
        normalized.append(merged)
    return normalized
def choose_set_field(workflow, field, value):
    request = workflow.request()
    for row in choice_rows(request):
        if row.get("op") == "set_field" and row.get("field") == field and row.get("value") == value:
            assert row["choice_id"] in request["eligible_choice_ids"]
            return workflow.step(row["choice_id"])
    raise AssertionError(f"choice not found for {field}={value}")
def submit_choice(request):
    for row in choice_rows(request):
        if row.get("op") == "submit":
            return row
    raise AssertionError("submit choice not found")
def test_checker_accepts_exact_submitted_fixture_snapshot_without_trusting_labels():
    from train.classifier_workflow_outcome import check_outcome
    row = case()
    out = check_outcome(row, snapshot(row, success=False))
    assert out["outcome"] == "success"
    assert out["task_resolution"] == "completed"
    assert "bounded local simulator snapshot" in " ".join(out["does_not_prove"])
def test_checker_rejects_wrong_fields_even_when_snapshot_claims_success():
    from train.classifier_workflow_outcome import check_outcome
    row = case()
    form = dict(row["desired"], destination="Berlin", date="2026-10-05")
    out = check_outcome(row, snapshot(row, form=form, success=True))
    assert out["outcome"] == "failure"
    assert any("destination" in reason and "Paris" in reason for reason in out["reasons"])
    assert any("date" in reason and "2026-10-04" in reason for reason in out["reasons"])
def test_checker_rejects_claimed_success_without_executed_submit_evidence():
    from train.classifier_workflow_outcome import check_outcome
    row = case()
    out = check_outcome(row, snapshot(row, submitted=True, transitions=[{"status": "submitted"}],
                                      success=True))
    assert out["outcome"] == "unknown"
    assert any("submit transition" in reason for reason in out["reasons"])
def test_checker_rejects_stale_or_unavailable_actions_before_final_success():
    from train.classifier_workflow_outcome import check_outcome
    row = case()
    out = check_outcome(row, snapshot(
        row,
        violations=["unavailable_choice:option is stale"],
        transitions=[
            {"choice_id": "stale-date", "operation": "set_field", "status": "rejected",
             "message": "option is stale"},
            submitted_step(row["desired"]),
        ],
    ))
    assert out["outcome"] == "failure"
    assert any("stale" in reason for reason in out["reasons"])
def test_checker_distinguishes_justified_blocked_from_completed_task():
    from train.classifier_workflow_outcome import check_outcome
    row = case(impossible=True)
    form = dict(row["desired"], destination="")
    out = check_outcome(row, snapshot(
        row,
        form=form,
        submitted=False,
        blocked=True,
        transitions=[blocked_step(form)],
        success=True,
    ))
    assert out["outcome"] == "blocked"
    assert out["task_resolution"] == "justified_blocked"
    assert any("not a completed task" in reason for reason in out["reasons"])
def test_checker_rejects_impossible_flag_when_desired_option_is_available():
    from train.classifier_workflow_outcome import check_outcome
    row = case(impossible=True, options=[
        {"op": "set", "field": "destination", "value": "Paris",
         "description": "Set destination to Paris."}
    ])
    form = dict(row["desired"], destination="")
    out = check_outcome(row, snapshot(
        row,
        form=form,
        submitted=False,
        blocked=True,
        transitions=[blocked_step(form)],
    ))
    assert out["outcome"] == "failure"
    assert any("available nonstale" in reason for reason in out["reasons"])
def test_checker_allows_transient_failure_and_wrong_edit_after_recovery():
    from train.classifier_workflow_outcome import check_outcome
    row = case()
    out = check_outcome(row, snapshot(
        row,
        violations=["wrong_edit:destination=Lyon"],
        transitions=[
            {"choice_id": "submit-1", "operation": "submit", "status": "transient_failure"},
            {"choice_id": "set-paris", "operation": "set_field", "status": "applied"},
            submitted_step(row["desired"], "submit-2"),
        ],
    ))
    assert out["outcome"] == "success"
def test_checker_reports_unknown_for_malformed_alternative_snapshot_and_does_not_mutate_case():
    from train.classifier_workflow_outcome import check_outcome
    row = case()
    original = deepcopy(row)
    out = check_outcome(row, {"form": {"fields": row["desired"]}, "submitted": True})
    assert out["outcome"] == "unknown"
    assert row == original
    bad = snapshot(row)
    bad["case_id"] = "other"
    assert check_outcome(row, bad)["outcome"] == "unknown"
    bad = snapshot(row)
    bad["desired_fields"] = dict(row["desired"], date="wrong")
    assert check_outcome(row, bad)["outcome"] == "unknown"
def test_fixture_submit_eligibility_does_not_encode_correct_answer():
    from train.classifier_workflow_fixture import Workflow, scenarios
    from train.classifier_workflow_outcome import check_outcome
    row = next(item for item in scenarios() if item["id"] == "basic_paris_search")
    workflow = Workflow(row, seed=11)
    choose_set_field(workflow, "origin", "NYC")
    choose_set_field(workflow, "destination", "Lyon")
    choose_set_field(workflow, "date", "2026-10-12")
    choose_set_field(workflow, "travelers", "1 adult")
    choose_set_field(workflow, "cabin", "economy")
    request = workflow.request()
    submit = submit_choice(request)
    assert submit["choice_id"] in request["eligible_choice_ids"]
    assert workflow.step(submit["choice_id"])["status"] == "submitted"
    out = check_outcome(row, workflow.snapshot())
    assert out["outcome"] == "failure"
    assert any("destination" in reason and "Paris" in reason for reason in out["reasons"])
def test_run_episode_deepcopies_policy_request_and_checks_final_state(monkeypatch):
    import train.classifier_workflow_experiment as experiment
    row = case()
    class FakeWorkflow:
        def __init__(self, fixture_case, seed=0):
            self.done = False
            self.request_was_mutated = False
        def request(self):
            self._request = {
                "schema": "flywheel.decision-request/v1",
                "decision_ref": "fake:0",
                "state": {"goal": "submit exact form"},
                "choices": [{"id": "submit", "description": "Submit exact form"}],
                "eligible_choice_ids": ["submit"],
                "evidence_refs": [],
            }
            return self._request
        def step(self, choice_id):
            self.request_was_mutated = self._request["state"]["goal"] != "submit exact form"
            self.done = True
            return {"status": "submitted", "choice_id": choice_id}
        def snapshot(self):
            out = snapshot(
                row,
                submitted=self.done,
                transitions=([submitted_step(row["desired"])] if self.done else []),
            )
            out["policy_request_mutated_live_state"] = self.request_was_mutated
            return out
    def mutating_policy(request):
        request["state"]["goal"] = "mutated by policy"
        return "submit"
    fake_fixture = types.ModuleType("train.classifier_workflow_fixture")
    fake_fixture.Workflow = FakeWorkflow
    monkeypatch.setitem(sys.modules, "train.classifier_workflow_fixture", fake_fixture)
    episode = experiment.run_episode(row, mutating_policy, seed=7, max_steps=3)
    assert episode["outcome"]["outcome"] == "success"
    assert episode["final"]["policy_request_mutated_live_state"] is False
    assert episode["trace"][0]["choice_id"] == "submit"
    assert episode["trace"][0]["before_sha256"] != episode["trace"][0]["after_sha256"]
def policy_failure_case(monkeypatch, policy, expected_stop):
    import train.classifier_workflow_experiment as experiment
    row = case(impossible=True)
    class FakeWorkflow:
        step_calls = 0
        def __init__(self, fixture_case, seed=0):
            self.done = False
        def request(self):
            return {
                "schema": "flywheel.decision-request/v1",
                "decision_ref": "fake:blockable",
                "state": {"goal": "requested option is absent"},
                "choices": [{"id": "safe", "description": "available fallback"}],
                "eligible_choice_ids": ["safe"],
                "evidence_refs": [],
            }
        def step(self, choice_id):
            type(self).step_calls += 1
            self.done = True
            return {"status": "blocked", "choice_id": choice_id}
        def snapshot(self):
            return snapshot(
                row,
                submitted=False,
                blocked=True,
                transitions=[blocked_step(row["desired"])],
            )
    fake_fixture = types.ModuleType("train.classifier_workflow_fixture")
    fake_fixture.Workflow = FakeWorkflow
    monkeypatch.setitem(sys.modules, "train.classifier_workflow_fixture", fake_fixture)
    episode = experiment.run_episode(row, policy, seed=0, max_steps=3)
    assert FakeWorkflow.step_calls == 0
    assert episode["stop_reason"] == expected_stop
    assert episode["outcome"]["outcome"] not in {"success", "blocked"}
@pytest.mark.parametrize("mode, expected_stop", [
    ("unavailable", "policy_unavailable"),
    ("exception", "policy_error"),
])
def test_run_episode_failed_policy_does_not_execute_blocking_step(monkeypatch, mode, expected_stop):
    def policy(request):
        if mode == "exception":
            raise RuntimeError("model unavailable")
        policy.last_status = "scorer_unavailable"
        return None
    policy_failure_case(monkeypatch, policy, expected_stop)
