"""Falsifier for the prompt forge (harness/prompt_forge.py).

The load-bearing property: every forged prompt carries a CHECKABLE success
criterion, and when the goal admits none the spec is HONESTLY flagged
not-well-posed with an auto-proposed criterion -- an unverifiable task is never
silently dressed as ready.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.prompt_forge import forge, forge_prompt, classify_task, PromptSpec


def test_classify_task():
    assert classify_task("implement a function that sorts a list") == "code"
    assert classify_task("analyze the tradeoffs of X vs Y") == "analysis"
    assert classify_task("write a 200-word blog post") == "writing"
    assert classify_task("extract all emails from this text") == "extraction"
    assert classify_task("convert this CSV to JSON") == "transform"
    assert classify_task("research the state of the art in X") == "research"
    assert classify_task("something entirely vague") == "general"


def test_every_prompt_has_a_criterion():
    for goal in ["write a poem", "do the thing", "make it better", ""]:
        spec = forge(goal)
        assert spec.success_criterion            # never empty


def test_explicit_criterion_is_derived_and_well_posed():
    spec = forge("implement sort(nums) that passes the provided tests")
    assert spec.criterion_source == "derived-from-goal"
    assert spec.well_posed is True


def test_vague_goal_is_flagged_not_well_posed():
    spec = forge("make my app good")
    assert spec.criterion_source == "auto-proposed"
    assert spec.well_posed is False               # honest: no checkable criterion
    assert "auto-proposed" in spec.render()       # the flag is visible in the prompt


def test_constraints_are_sniffed_from_goal():
    spec = forge("write a function in Python, under 50 lines, no dependencies")
    joined = " ".join(spec.constraints)
    assert "python" in joined.lower()
    assert "at most 50 lines" in joined
    assert "no external dependencies" in joined


def test_caller_overrides_win():
    spec = forge("do X", task_type="code", success_criterion="rc==0 on the smoke test",
                 context="legacy module", output_contract="a diff")
    assert spec.task_type == "code"
    assert spec.success_criterion == "rc==0 on the smoke test"
    assert spec.criterion_source == "derived-from-goal"
    assert spec.well_posed is True
    assert spec.context == "legacy module"


def test_render_has_all_sections():
    p = forge_prompt("implement a CSV parser in Python that passes the tests")
    for section in ("# Role", "# Task", "# Context", "# Constraints", "# Output",
                    "# Success criterion"):
        assert section in p


def test_to_dict_schema():
    d = forge("summarize this article under 100 words").to_dict()
    assert d["schema"] == "flywheel.prompt-spec/v1"
    assert d["task_type"] == "transform"
    assert "prompt" in d and d["success_criterion"]
