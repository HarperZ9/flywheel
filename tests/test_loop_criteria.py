"""test_loop_criteria.py -- budget exposure and criteria refuse-done wiring.

Falsifiers for Task 2 of the acceptance-criteria plan: the loop states its
remaining budget every turn, and it refuses to report "done" while any
acceptance criterion is still FAILING -- the model saying "done" never flips a
criterion, only apply_oracle_result (via a registered oracle) does. With
criteria=None the result is identical to today: no "criteria"/"accepted" keys
at all.
"""
import json

from harness import acceptance_criteria as AC
from harness.local_loop import run_agent
from harness.local_session import SessionLedger
from harness.local_tools import ToolExecutor, ToolGate


class FakeAgent:
    """A fake LocalAgent: returns queued replies, records what it was sent."""

    def __init__(self, replies):
        self.system = "base system"
        self._replies = list(replies)
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        text = self._replies.pop(0) if self._replies else "done"
        return {"content": [{"text": text}], "backend": "stub"}


SPECS = [
    {"id": "tests_green", "description": "the suite passes", "oracle": "test_cmd"},
    {"id": "docs_written", "description": "docs updated", "oracle": "human"},
]


def test_run_never_reports_accepted_while_a_criterion_fails(tmp_path):
    # the model claims "done" every turn; nothing ever supplies a registered
    # oracle result, so accepted must never read True and the run must spend
    # its whole budget honestly rather than take the model's word for it.
    agent = FakeAgent(["done", "done", "done", "done"])
    criteria = AC.new_criteria(SPECS)
    res = run_agent(agent, "ship it", ToolExecutor(root=str(tmp_path)),
                    SessionLedger(), max_steps=3, criteria=criteria)
    assert res["accepted"] is False
    assert res["criteria"]["all_pass"] is False
    assert res["steps"] == 3


def test_model_saying_done_does_not_flip_a_criterion(tmp_path):
    agent = FakeAgent(["done"])
    criteria = AC.new_criteria(SPECS)
    run_agent(agent, "x", ToolExecutor(root=str(tmp_path)), SessionLedger(),
             max_steps=1, criteria=criteria)
    assert [c["status"] for c in criteria] == [AC.FAILING, AC.FAILING]
    assert all(c["evidence"] is None for c in criteria)


def test_run_reports_accepted_once_every_criterion_actually_passes(tmp_path):
    agent = FakeAgent(["done"])
    criteria = AC.new_criteria(SPECS)
    AC.apply_oracle_result(criteria, "tests_green", "test_cmd", True, evidence="ok")
    AC.apply_oracle_result(criteria, "docs_written", "human", True, evidence="ok")
    res = run_agent(agent, "x", ToolExecutor(root=str(tmp_path)), SessionLedger(),
                    max_steps=3, criteria=criteria)
    assert res["accepted"] is True
    assert res["criteria"]["all_pass"] is True
    assert res["steps"] == 1


def test_test_cmd_outcome_flips_only_the_criterion_registered_to_it(tmp_path):
    agent = FakeAgent(["done"])
    criteria = AC.new_criteria(SPECS)
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_exec=True),
                      runner=lambda cmd, root: (True, "3 passed"))
    res = run_agent(agent, "x", ex, SessionLedger(), max_steps=3,
                    test_cmd="pytest -q", criteria=criteria)
    tests_green = next(c for c in criteria if c["id"] == "tests_green")
    docs = next(c for c in criteria if c["id"] == "docs_written")
    assert tests_green["status"] == AC.PASSING
    assert "passed" in tests_green["evidence"]
    assert docs["status"] == AC.FAILING           # a different oracle: untouched
    assert docs["evidence"] is None
    assert res["accepted"] is False                # docs_written still failing


def test_a_regressing_test_cmd_flips_the_criterion_back(tmp_path):
    agent = FakeAgent(["done"] * 5)
    criteria = AC.new_criteria(SPECS)
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_exec=True),
                      runner=lambda cmd, root: (False, "1 failed"))
    run_agent(agent, "x", ex, SessionLedger(), max_steps=2,
             test_cmd="pytest -q", criteria=criteria)
    tests_green = next(c for c in criteria if c["id"] == "tests_green")
    assert tests_green["status"] == AC.FAILING
    assert "failed" in tests_green["evidence"]


def test_failing_ids_are_fed_back_and_a_criteria_ledger_entry_is_appended(tmp_path):
    agent = FakeAgent(["done", "done"])
    criteria = AC.new_criteria(SPECS)
    led = SessionLedger()
    run_agent(agent, "x", ToolExecutor(root=str(tmp_path)), led, max_steps=2,
             criteria=criteria)
    assert "tests_green" in agent.sent[1] and "docs_written" in agent.sent[1]
    crit_entries = [e for e in led.entries if e.kind == "criteria"]
    assert len(crit_entries) >= 1
    payload = json.loads(crit_entries[0].content)
    assert set(payload["failing_ids"]) == {"tests_green", "docs_written"}


def test_budget_lines_appear_in_the_ledger_each_turn_and_name_the_remaining_count(tmp_path):
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    agent = FakeAgent(['TOOL read_file {"path": "a.txt"}', "done"])
    led = SessionLedger()
    run_agent(agent, "x", ToolExecutor(root=str(tmp_path)), led, max_steps=4,
             budget_note=True)
    budget_entries = [e for e in led.entries if e.kind == "budget"]
    assert len(budget_entries) == 2                    # one per turn taken
    assert budget_entries[0].meta == {"step": 1, "max_steps": 4, "remaining": 4}
    assert budget_entries[1].meta == {"step": 2, "max_steps": 4, "remaining": 3}
    assert budget_entries[0].content == "[budget] step 1 of 4, 4 remaining."
    assert budget_entries[1].content == "[budget] step 2 of 4, 3 remaining."


def test_budget_line_is_prefixed_onto_the_message_the_model_sees(tmp_path):
    agent = FakeAgent(["done"])
    run_agent(agent, "the actual goal", ToolExecutor(root=str(tmp_path)),
             SessionLedger(), max_steps=5, budget_note=True)
    assert agent.sent[0].startswith("[budget] step 1 of 5, 5 remaining.")
    assert "the actual goal" in agent.sent[0]


def test_budget_note_defaults_off_so_an_unset_caller_is_unchanged(tmp_path):
    # DEVIATION from the plan's stated default (budget_note: bool = True):
    # a criteria=None caller must see byte-identical behavior, and that
    # includes the ledger shape, not only the result dict. With budget_note
    # left at True by default, test_local_agentic.py::
    # test_loop_executes_tools_and_witnesses_the_full_trajectory (an existing,
    # unrelated test asserting the exact ledger kind sequence) broke, because
    # a "budget" entry landed ahead of every "assistant" entry. Defaulting
    # budget_note to False keeps every existing caller's ledger and prompts
    # untouched; budget exposure is opt-in via budget_note=True.
    agent = FakeAgent(["done"])
    led = SessionLedger()
    run_agent(agent, "the actual goal", ToolExecutor(root=str(tmp_path)), led,
             max_steps=5)
    assert agent.sent[0] == "the actual goal"
    assert [e for e in led.entries if e.kind == "budget"] == []


def test_budget_note_can_be_turned_off_explicitly(tmp_path):
    agent = FakeAgent(["done"])
    led = SessionLedger()
    run_agent(agent, "the actual goal", ToolExecutor(root=str(tmp_path)), led,
             max_steps=5, budget_note=False)
    assert agent.sent[0] == "the actual goal"
    assert [e for e in led.entries if e.kind == "budget"] == []


def test_criteria_none_result_has_no_criteria_or_accepted_keys(tmp_path):
    agent = FakeAgent(["done"])
    res = run_agent(agent, "x", ToolExecutor(root=str(tmp_path)), SessionLedger(),
                    max_steps=2)
    assert "criteria" not in res
    assert "accepted" not in res


def test_accepted_trusted_is_false_when_the_grading_file_is_tampered_with(tmp_path):
    """The criterion's oracle is real: test_cmd genuinely ran and genuinely
    passed, so `accepted` (== all_pass(criteria)) legitimately reads True.
    But the trajectory that got there first wrote to tests/test_foo.py -- a
    path DEFAULT_PROTECTED matches -- which is exactly the "edit the file
    that grades you" reward-hack trajectory_integrity exists to catch. That
    trips integrity["clean"] to False, so accepted_trusted (accepted AND
    integrity clean) must read False even though accepted itself is True:
    the two keys are not allowed to collapse into one fact.
    """
    specs = [{"id": "tests_green", "description": "the suite passes",
              "oracle": "test_cmd"}]
    criteria = AC.new_criteria(specs)
    agent = FakeAgent([
        'TOOL write_file {"path": "tests/test_foo.py", '
        '"content": "def test_x():\\n    assert True\\n"}',
        "done",
    ])
    ex = ToolExecutor(root=str(tmp_path),
                      gate=ToolGate(allow_write=True, allow_exec=True),
                      runner=lambda cmd, root: (True, "1 passed"))
    res = run_agent(agent, "x", ex, SessionLedger(), max_steps=3,
                    test_cmd="pytest -q", criteria=criteria)
    assert res["integrity"]["clean"] is False
    assert any(f["kind"] == "edited_protected_file" for f in res["integrity"]["flags"])
    assert res["accepted"] is True
    assert res["accepted_trusted"] is False


def test_tests_pass_reflects_the_last_real_test_outcome_at_max_steps(tmp_path):
    """A run can legitimately continue past a GREEN test_cmd because a second
    criterion (a different, never-firing oracle) is still failing, then
    exhaust max_steps. The old max_steps exit hardcoded tests_pass=False,
    which contradicted the criteria summary sitting right next to it showing
    the test_cmd criterion PASSING with green evidence. tests_pass must track
    the last real test_cmd outcome instead of assuming failure.
    """
    specs = [
        {"id": "tests_green", "description": "the suite passes", "oracle": "test_cmd"},
        {"id": "docs_written", "description": "docs updated", "oracle": "human"},
    ]
    criteria = AC.new_criteria(specs)
    agent = FakeAgent(["done", "done", "done"])
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_exec=True),
                      runner=lambda cmd, root: (True, "3 passed"))
    res = run_agent(agent, "x", ex, SessionLedger(), max_steps=2,
                    test_cmd="pytest -q", criteria=criteria)
    assert res["steps"] == 2
    assert res["tests_pass"] is True                 # not the old hardcoded False
    tests_green = next(c for c in criteria if c["id"] == "tests_green")
    docs = next(c for c in criteria if c["id"] == "docs_written")
    assert tests_green["status"] == AC.PASSING
    assert "passed" in tests_green["evidence"]
    assert docs["status"] == AC.FAILING
    assert res["criteria"]["failing_ids"] == ["docs_written"]
    assert res["accepted"] is False                  # docs_written still failing
