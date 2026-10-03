"""The held-out rerun script: split, sanity, and arm bookkeeping (no model).

Success criteria:
- split_tests keeps the import header and every test function;
- with a proposer that returns the reference solution, both arms pass the
  held-out suite and nothing is a false accept;
- false-success control: a proposer that returns a program passing only the
  visible half is accepted by the self-scored path and rejected by the held-out
  decider, so the false-accept column can be non-zero;
- the summary counts and the paired interval come from the rows.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from harness.proposer import ProposerOutput, prompt_hash
from harness.tasks_hard import HARD_REGISTRY

SPEC = importlib.util.spec_from_file_location(
    "run_heldout_rerun", Path(__file__).parent.parent / "scripts" / "run_heldout_rerun.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
ROMAN = vars(next(t for t in HARD_REGISTRY if t.task_id == "roman_to_int"))
# Visible tests are III, IX, MCMXCIV; held-out are IV and LVIII.
CHEAT = ("def roman_to_int(s):\n"
         "    return {'III': 3, 'IX': 9, 'MCMXCIV': 1994}.get(s, 0)\n")


class Fixed:
    model_ref = "fixed"

    def __init__(self, text):
        self.text = text

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        return ProposerOutput(text=self.text, model_ref="fixed", seed=seed,
                              prompt_hash=prompt_hash(prompt), cache="stub")


def test_split_keeps_header_and_all_tests():
    head, tests = mod.split_tests(ROMAN["hidden_tests"])
    assert head.startswith("from solution import")
    assert len(tests) == 5 and all(t.startswith("def test_") for t in tests)


def test_reference_passes_both_arms(tmp_path):
    row = mod.run_task(ROMAN, Fixed(ROMAN["solution"]), tmp_path)
    assert row["single_held"] and row["search_held"]
    assert not row["self_scored_false_accept"]
    assert row["selection"] == "visible-selects-held-out-decides"


def test_control_visible_only_program_is_a_false_accept(tmp_path):
    row = mod.run_task(ROMAN, Fixed(CHEAT), tmp_path)
    assert row["single_visible"] and not row["single_held"]
    assert row["self_scored_accept"] and not row["search_held"]
    assert row["self_scored_false_accept"]


def test_summary():
    rows = [{"task_id": "a", "single_held": False, "search_held": True,
             "self_scored_accept": True, "self_scored_false_accept": False},
            {"task_id": "b", "single_held": True, "search_held": True,
             "self_scored_accept": True, "self_scored_false_accept": False},
            {"task_id": "c", "excluded": "x"}]
    s = mod.summarize(rows)
    assert s["n"] == 2 and s["excluded"] == 1
    assert s["diff_search_minus_single"] == 0.5
