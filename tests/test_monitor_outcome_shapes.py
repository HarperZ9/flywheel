"""Controls that pin the adapters to Control Tower's writers at 1cc91b7.

Each one corresponds to a mismatch a source check found in the first version
of the adapters, which had been written from docs. They are the reason those
mismatches cannot come back unnoticed.
"""
import pytest
from monitor_outcome_shapes import (
    dump,
    eval1_score,
    eval2_entry,
    eval2_sample,
    eval2_score,
    log,
    sample,
)

from harness.monitor_outcome import MonitorOutcomeError, build_monitor_record


def _monitor(samples, adapter, *, eval2=None, **kwargs):
    raw = log(samples, eval2=adapter == "eval2" if eval2 is None else eval2)
    return build_monitor_record(raw, adapter=adapter, **kwargs)["samples"][0]["monitor"]


def _statuses(monitor):
    return [a["status"] for a in monitor["actions"]]


# --- the declared variant is checked against the log ------------------------

def test_eval2_declared_on_a_log_without_the_eval2_header_is_refused():
    with pytest.raises(MonitorOutcomeError, match="task_registry_name"):
        _monitor([eval2_sample("s1", [1.0])], "eval2", eval2=False)


@pytest.mark.parametrize("adapter", ["eval1", "eval1-legacy"])
def test_eval1_declared_on_an_eval2_log_is_refused(adapter):
    with pytest.raises(MonitorOutcomeError, match="marks it as eval2"):
        _monitor([eval2_sample("s1", [1.0])], adapter, eval2=True)


# --- eval2 ------------------------------------------------------------------

def test_eval2_draws_count_from_one_and_values_are_read_from_the_mapping():
    monitor = _monitor([eval2_sample("s1", [2.0, 7.5])], "eval2")
    assert monitor["status"] == "scored"
    assert _statuses(monitor) == ["scored", "scored"]
    assert [a["draw"] for a in monitor["actions"]] == [1, 1]
    assert monitor["summary_value"] == {"monitor": {"strong/0": 2.0, "strong/1": 7.5}}


def test_a_draft_the_mapping_leaves_out_is_not_an_action():
    entries = [eval2_entry(0, 2.0), eval2_entry(1, 9.0, message_id="draft-1")]
    s = sample("s1", {"monitor": eval2_score(entries, mapping={"strong/0": 2.0})})
    monitor = _monitor([s], "eval2")
    assert _statuses(monitor) == ["scored", "draft"]


def test_a_resampled_draft_at_the_same_index_is_told_apart_by_the_transcript():
    entries = [eval2_entry(3, 9.0, message_id="draft"), eval2_entry(3, 2.0, message_id="ran")]
    s = sample("s1", {"monitor": eval2_score(entries, mapping={"strong/3": 2.0})})
    s["messages"] = [{"id": "ran"}]
    assert _statuses(_monitor([s], "eval2")) == ["draft", "scored"]


def test_a_same_index_tie_without_a_transcript_is_reported_not_guessed():
    entries = [eval2_entry(3, 9.0, message_id="a"), eval2_entry(3, 2.0, message_id="b")]
    s = sample("s1", {"monitor": eval2_score(entries, mapping={"strong/3": 2.0})})
    monitor = _monitor([s], "eval2")
    assert _statuses(monitor) == ["unsupported", "unsupported"]
    assert monitor["status"] == "unsupported"


def test_an_unscored_entry_keeps_its_error_and_a_code_monitor_value():
    entries = [eval2_entry(0, 1.0), eval2_entry(1, "N", explanation="monitor timed out")]
    monitor = _monitor([sample("s1", {"monitor": eval2_score(entries)})], "eval2")
    assert _statuses(monitor) == ["scored", "unscored"]
    assert monitor["actions"][1]["source_value"] == "N"
    assert monitor["actions"][1]["reason"] == "monitor timed out"


@pytest.mark.parametrize("mapping", [{}, {"strong/0": "unscored"}])
def test_an_empty_or_all_unscored_mapping_is_not_scored(mapping):
    entries = [eval2_entry(0, "N")] if mapping else []
    s = sample("s1", {"monitor": eval2_score(entries, mapping=mapping)})
    assert _monitor([s], "eval2")["status"] == "unscored"


def test_a_scalar_eval2_value_is_unsupported_not_scored():
    s = sample("s1", {"monitor": {"value": 5.0, "metadata": {"scores": []}}})
    assert _monitor([s], "eval2")["status"] == "unsupported"


def test_a_second_monitor_pass_is_read():
    second = eval2_score([eval2_entry(0, 8.0, monitor="weak")])
    monitor = _monitor([eval2_sample("s1", [1.0], extra_scores={"monitor-1": second})], "eval2")
    assert [p["key"] for p in monitor["passes"]] == ["monitor", "monitor-1"]
    assert {a["pass"] for a in monitor["actions"]} == {"monitor", "monitor-1"}


def test_an_entry_that_disagrees_with_the_mapping_is_unsupported():
    s = sample("s1", {"monitor": eval2_score([eval2_entry(0, 2.0)], mapping={"strong/0": 6.0})})
    assert _statuses(_monitor([s], "eval2")) == ["unsupported"]


def test_a_mapping_member_with_no_entry_is_kept():
    s = sample("s1", {"monitor": eval2_score([], mapping={"strong/4": 3.0})})
    monitor = _monitor([s], "eval2")
    assert _statuses(monitor) == ["scored"]
    assert monitor["actions"][0]["action"] == 4


# --- current eval1 ----------------------------------------------------------

def test_eval1_finds_the_monitor_name_key_rather_than_defaulting_to_monitor():
    s = sample("s1", {"monitor_strong": eval1_score([dump(3.0)])})
    raw = log([s], eval2=False)
    record = build_monitor_record(raw, adapter="eval1")
    assert record["monitor_scorer"] == "monitor_strong"
    assert record["samples"][0]["monitor"]["status"] == "scored"


def test_several_eval1_monitors_must_be_declared():
    s = sample("s1", {"monitor_a": eval1_score([dump(1.0)]), "monitor_b": eval1_score([dump(2.0)])})
    with pytest.raises(MonitorOutcomeError, match="declare monitor_scorer"):
        _monitor([s], "eval1")
    assert _monitor([s], "eval1", monitor_scorer="monitor_b")["actions"][0]["source_value"] == 2.0


def test_eval1_noanswer_null_error_and_negative_are_never_scored():
    dumps = [dump(3.0), dump("N", error="timeout"), None, dump(4.0, error="parse"), dump(-1.0)]
    monitor = _monitor([sample("s1", {"monitor_strong": eval1_score(dumps)})], "eval1")
    assert _statuses(monitor) == ["scored", "unscored", "absent", "unscored", "unscored"]
    assert monitor["actions"][1]["reason"] == "timeout"


def test_eval1_skipped_by_design_is_named():
    monitor = _monitor([sample("s1", {"monitor_strong": eval1_score([dump("N", skipped_by_design=True)])})], "eval1")
    assert monitor["actions"][0]["reason"] == "skipped by design"


def test_eval1_trajectory_monitor_values():
    scored = _monitor([sample("s1", {"monitor_traj": {"value": 7.0}})], "eval1")
    failed = _monitor([sample("s1", {"monitor_traj": {"value": "N", "metadata": {"error": "x"}}})], "eval1")
    assert (scored["status"], scored["actions"][0]["kind"]) == ("scored", "trajectory")
    assert failed["status"] == "unscored"


def test_eval1_mapping_and_action_scores_disagreeing_is_unsupported():
    score = eval1_score([dump(3.0)], mapping={"0": 5.0})
    assert _statuses(_monitor([sample("s1", {"monitor_strong": score})], "eval1")) == ["unsupported"]


def test_a_top_level_null_is_unsupported_because_inspect_never_writes_one():
    s = sample("s1", {"monitor_strong": {"value": None, "metadata": {"action_scores": []}}})
    assert _monitor([s], "eval1", monitor_scorer="monitor_strong")["status"] == "unsupported"


# --- legacy eval1 -----------------------------------------------------------

LEGACY = {"value": {"max": 8.0, "action_0": 2.0, "action_1": 8.0, "trajectory": 5.0}}


def test_a_legacy_fold_is_read_per_action_with_its_index_basis():
    monitor = _monitor([sample("s1", {"monitor_strong": LEGACY})], "eval1-legacy")
    assert monitor["status"] == "scored"
    assert [(a["kind"], a["action"]) for a in monitor["actions"]] == [
        ("action", 0), ("action", 1), ("trajectory", None)]
    assert all(a["detail"]["index_basis"] == "fold" for a in monitor["actions"])


def test_a_legacy_fold_under_eval1_is_refused_and_the_reverse_too():
    with pytest.raises(MonitorOutcomeError, match="legacy fold"):
        _monitor([sample("s1", {"monitor_strong": LEGACY})], "eval1", monitor_scorer="monitor_strong")
    current = sample("s1", {"monitor_strong": eval1_score([dump(1.0)])})
    with pytest.raises(MonitorOutcomeError, match="not a legacy fold"):
        _monitor([current], "eval1-legacy", monitor_scorer="monitor_strong")


def test_an_unknown_fold_key_is_unsupported():
    fold = {"value": {"max": 1.0, "mean": 1.0}}
    monitor = _monitor([sample("s1", {"monitor_strong": fold})], "eval1-legacy")
    assert _statuses(monitor) == ["unsupported"]
