"""Shared editor contracts; model boundaries are scripted, never networked."""
import json
from types import SimpleNamespace

import pytest


def _info(backend="ollama", model="test-model", attempts=None):
    return SimpleNamespace(backend=backend, model=model, attempts=attempts or [])


def _script(monkeypatch, outputs):
    from articulate import backends
    sequence = iter(outputs)
    calls = []

    def complete(instructions, text, **kwargs):
        calls.append((instructions, text, kwargs))
        return next(sequence)

    monkeypatch.setattr(backends, "complete", complete)
    return calls


def _scores(value, **overrides):
    scores = dict.fromkeys(("concreteness", "commitment", "economy", "rhythm", "restatable"), value)
    scores.update(overrides)
    return json.dumps(scores)


@pytest.mark.parametrize("goal", ["fix", "polish", "judge"])
def test_no_backend_returns_local_result_with_receipt(monkeypatch, goal):
    from articulate import editing
    _script(monkeypatch, [("", _info("none", None))])
    result = editing.run_edit("We really ship software.", goal)
    assert result["backend"] == "none"
    assert result["receipt"]["backend"] == "none"
    assert result["findings_before"]
    assert result["goal"] == goal
    if goal == "judge":
        assert result["text"] == "We really ship software."


def test_host_returns_actionable_plan(monkeypatch):
    from articulate import editing
    _script(monkeypatch, [("", _info("host", None))])
    result = editing.run_edit("We really ship software.", context="mcp")
    assert result["backend"] == "host"
    assert result["plan_id"] and result["instructions"]
    assert "edit_submit" in result["next_step"]


@pytest.mark.parametrize("original,rewrite", [
    ("We shipped 14 items.", "We shipped 15 items."),
    ("Read https://example.org/guide.", "Read the guide."),
    ("The report cites [12].", "The report cites [13]."),
    ('The report says "keep this".', 'The report says "change this".'),
])
def test_model_rewrite_cannot_change_protected_content(monkeypatch, original, rewrite):
    from articulate import editing
    calls = _script(monkeypatch, [(rewrite, _info())])
    result = editing.run_edit(original, passes=1)
    assert result["text"] == original
    assert result["refused"]
    assert result["backend"] == result["receipt"]["backend"] == "ollama"
    assert result["model"] == result["receipt"]["model"] == "test-model"
    assert calls[0][0].endswith(editing.prompts.CONTENT_BOUNDARY)


def test_polish_preserves_best_when_one_quality_regresses(monkeypatch):
    from articulate import editing
    attempts = [{"backend": "claude-cli", "reason": "unavailable"}]
    _script(monkeypatch, [(_scores(2), _info(attempts=attempts)),
                         ("We ship software.", _info()),
                         (_scores(4), _info()),
                         ("We deliver software.", _info()),
                         (_scores(4, rhythm=3), _info())])
    result = editing.run_edit("We really ship software.", "polish", bar=5)
    assert result["text"] == "We ship software."
    assert result["scores"]["rhythm"] == 4
    assert result["attempts"] == result["receipt"]["attempts"] == attempts
    assert result["quality_met"] is False


def test_polish_does_not_claim_quality_when_scores_are_missing(monkeypatch):
    from articulate import editing
    _script(monkeypatch, [("not json", _info())])
    result = editing.run_edit("We ship software.", "polish")
    assert result["text"] == "We ship software."
    assert result["scores"] is None
    assert result["quality_met"] is False


def test_polish_advisory_rejection_keeps_scores_for_actual_returned_text(monkeypatch):
    from articulate import editing, profiles
    profile = profiles.load("flavored")
    profile["editor"] = {"require_fix": ["expletive-opener"]}
    _script(monkeypatch, [(_scores(2), _info()),
                         ("There is software to ship.", _info()),
                         (_scores(4), _info())])
    result = editing.run_edit("We ship software.", "polish", profile=profile, passes=1)
    assert result["text"] == "We ship software."
    assert result["quality_met"] is False
    assert result["scores"] is None or result["scores"]["concreteness"] == 2
    assert result["receipt"]["scores"] is None or result["receipt"]["scores"]["after"]["concreteness"] == 2


def test_final_policy_rejection_cannot_reuse_candidate_quality_scores(monkeypatch):
    from articulate import editing, host_edit
    original = "We really ship software."
    _script(monkeypatch, [(_scores(2), _info()),
                         ("We ship software.", _info()),
                         (_scores(4), _info())])
    submit = host_edit.edit_submit
    count = 0

    def final_policy(text, rewrite, plan_id, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            # A final policy may retain the original after candidate scoring.
            return submit(text, text, plan_id, model=kwargs.get("model"))
        return submit(text, rewrite, plan_id, **kwargs)

    monkeypatch.setattr(host_edit, "edit_submit", final_policy)
    result = editing.run_edit(original, "polish", passes=1)
    assert result["text"] == original
    assert result["scores"] is None
    assert result["receipt"]["scores"] is None
    assert result["quality_status"] == result["receipt"]["quality_status"] == "unassessed_after_guard"
    assert result["quality_met"] is False


def test_polish_keeps_best_when_backend_disappears(monkeypatch):
    from articulate import editing
    failure = [{"backend": "ollama", "reason": "unavailable"}]
    _script(monkeypatch, [(_scores(2), _info()),
                         ("We ship software.", _info()),
                         (_scores(4), _info()),
                         ("", _info("none", None, failure))])
    result = editing.run_edit("We really ship software.", "polish", bar=5)
    assert result["text"] == "We ship software."
    assert result["backend"] == "ollama"
    assert result["attempts"] == result["receipt"]["attempts"] == failure


def test_profile_name_and_html_masks_survive_final_submission(monkeypatch):
    from articulate import backends, editing

    def complete(instructions, text, **kwargs):
        assert "<p>" not in text
        return text.replace("really ", ""), _info()

    monkeypatch.setattr(backends, "complete", complete)
    result = editing.run_edit("<p>We really ship 14 items.</p>", profile="flavored", is_html=True)
    assert result["text"] == "<p>We ship 14 items.</p>"
    assert not result["refused"]


def test_judge_retains_original_and_reports_assessment(monkeypatch):
    from articulate import editing
    calls = _script(monkeypatch, [("Name the actor.", _info())])
    result = editing.run_edit("It was really built.", goal="judge")
    assert result["text"] == "It was really built."
    assert result["assessment"] == "Name the actor."
    assert result["findings_before"]
    assert result["backend"] == "ollama"
    assert calls[0][0].count("TRUST BOUNDARY (") == 1


def test_polish_authorial_mode_does_not_call_model(monkeypatch):
    from articulate import backends, editing

    def forbidden(*a, **k):
        raise AssertionError("authorial mode must not call a model")

    monkeypatch.setattr(backends, "complete", forbidden)
    result = editing.run_edit("The room was quiet.", "polish", mode="narrative/narrate")
    assert result["text"] == "The room was quiet."
    assert result["quality_met"] is False


def test_legacy_fix_delegates_backend_and_writes_result(monkeypatch, tmp_path):
    from articulate import editing, editor
    source = tmp_path / "text.md"
    target = tmp_path / "fixed.md"
    source.write_text("We  ship software.", encoding="utf-8")
    calls = _script(monkeypatch, [("", _info("none", None))])
    assert editor.fix(str(source), str(target), 1, backend="none") == 0
    assert target.read_text(encoding="utf-8").strip() == "We ship software."
    assert calls[0][2]["backend"] == "none"


BLOCKED = "It is crucial to note that this is not a bug — it is a feature. The team really leverages it."


def test_judge_that_calls_a_blocked_passage_clean_is_unreliable(monkeypatch):
    from articulate import editing
    calls = _script(monkeypatch, [("The prose is strong and clear. No significant quality failures.", _info())])
    result = editing.run_edit(BLOCKED, goal="judge")
    assert result["gate_before"] == "blocked"
    assert result["quality_status"] == "unreliable"
    assert result["receipt"]["quality_status"] == "unreliable"
    assert "named none of the" in result["quality_note"]
    # The prompt hands the judge the blocking findings and the rule for them.
    assert "BLOCKING FINDINGS" in calls[0][0] and "em-dash" in calls[0][0]


def test_judge_that_names_a_blocking_finding_keeps_its_status(monkeypatch):
    from articulate import editing
    _script(monkeypatch, [("HIGH: the em-dash and the filler intensifier 'really' weaken line 1.", _info())])
    result = editing.run_edit(BLOCKED, goal="judge")
    assert result["quality_status"] != "unreliable"
    assert "quality_note" not in result


def test_judge_floor_ignores_a_passage_the_gate_allows(monkeypatch):
    from articulate import editing
    _script(monkeypatch, [("The prose is strong.", _info())])
    result = editing.run_edit("The parser reads one line at a time.", goal="judge")
    assert result["gate_before"] == "ok"
    assert result["quality_status"] != "unreliable"


def test_host_judge_submit_applies_the_same_floor():
    from articulate import host_edit
    plan = host_edit.edit_plan(BLOCKED, goal="judge")
    assert "BLOCKING FINDINGS" in plan["instructions"]
    clean = host_edit.edit_submit(BLOCKED, "The prose is strong.", plan["plan_id"])
    assert clean["quality_status"] == "unreliable"
    named = host_edit.edit_submit(BLOCKED, "Cut the corporate verb 'leverages'.", plan["plan_id"])
    assert named["quality_status"] != "unreliable"


def test_cli_judge_says_when_the_assessment_is_unreliable(monkeypatch, tmp_path, capsys):
    from articulate import editor
    _script(monkeypatch, [("No significant quality failures.", _info())])
    path = tmp_path / "blocked.md"
    path.write_text(BLOCKED, encoding="utf-8")
    editor.judge(str(path))
    assert "unreliable" in capsys.readouterr().out


def test_articulate_judge_command_reports_unreliable(monkeypatch, tmp_path, capsys):
    from articulate import cli
    _script(monkeypatch, [("No significant quality failures.", _info())])
    path = tmp_path / "blocked.md"
    path.write_text(BLOCKED, encoding="utf-8")
    cli.main(["judge", str(path), "--backend", "ollama"])
    out = json.loads(capsys.readouterr().out)
    assert out["quality_status"] == "unreliable"
    assert out["quality_note"].startswith("The judge named none")
