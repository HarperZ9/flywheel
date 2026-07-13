"""The duel must measure, never manufacture: injected proposers mark every
row synthetic and the comparison loader refuses them; live-shaped rows flow
through to a real Flywheel-vs-Codex verdict; unverifiable tasks leave the
denominator visibly."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from harness.quality_duel import SCHEMA, run_quality_duel
from run_harness_comparison_report import (build_comparisons,
                                           metric_rows_from_artifact)


class _Out:
    def __init__(self, text):
        self.text = text


class _Stub:
    def __init__(self, answer):
        self.answer = answer

    def generate(self, prompt, *, seed, temperature, max_new_tokens):
        return _Out(self.answer)


def _tasks_file(tmp_path, n=4):
    p = tmp_path / "tasks.jsonl"
    p.write_text("\n".join(
        json.dumps({"task_id": f"t{i}", "prompt": f"solve {i}",
                    "max_new_tokens": 64}) for i in range(n)),
        encoding="utf-8")
    return p


def test_injected_proposers_are_synthetic_and_refused_by_comparison(tmp_path):
    tasks = _tasks_file(tmp_path)
    doc = run_quality_duel(
        tasks, ["serve", "codex"],
        oracle=lambda cand, task: cand == "good",
        proposers={"serve": _Stub("good"), "codex": _Stub("bad")},
        out_path=tmp_path / "duel.json")
    assert doc["schema"] == SCHEMA
    assert all(r["evidence"] == "synthetic" for r in doc["rows"])
    assert metric_rows_from_artifact(doc, "duel.json") == []


def test_live_rows_produce_a_dual_evidence_verdict(tmp_path):
    # Live-shaped artifact (what a real, operator-authorized run writes).
    doc = {"schema": SCHEMA, "comparison_key": "quality_duel:hard_v2",
           "rows": [
               {"provider": "serve", "provider_role": "flywheel",
                "evidence": "live", "graded": 10, "unverifiable": 0,
                "pass_rate": 0.6, "quality_score": 0.6, "latency_ms": 100,
                "failure_class": ""},
               {"provider": "codex", "provider_role": "codex",
                "evidence": "live", "graded": 10, "unverifiable": 0,
                "pass_rate": 0.4, "quality_score": 0.4, "latency_ms": 90,
                "failure_class": ""}]}
    rows = metric_rows_from_artifact(doc, "duel.json")
    assert {r["provider_role"] for r in rows} == {"flywheel", "codex"}
    comparisons = build_comparisons(rows, flywheel_role="flywheel",
                                    codex_role="codex")
    assert len(comparisons) == 1
    assert comparisons[0]["comparison_key"] == "quality_duel:hard_v2"


def test_scoring_and_unverifiable_exclusion(tmp_path):
    tasks = _tasks_file(tmp_path, n=4)
    # Oracle: t0 pass, t1 fail, t2/t3 unverifiable.
    def oracle(cand, task):
        i = int(task["task_id"][1])
        return True if i == 0 else False if i == 1 else None
    doc = run_quality_duel(tasks, ["serve"], oracle=oracle,
                           proposers={"serve": _Stub("x")})
    row = doc["rows"][0]
    assert row["graded"] == 2
    assert row["unverifiable"] == 2
    assert row["pass_rate"] == 0.5


def test_empty_tasks_is_a_named_error(tmp_path):
    empty = tmp_path / "none.jsonl"
    empty.write_text("", encoding="utf-8")
    assert "error" in run_quality_duel(empty, ["serve"], oracle=lambda c, t: None,
                                       proposers={"serve": _Stub("x")})
