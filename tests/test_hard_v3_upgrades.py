"""hard_v3: the audit's real gaps, closed in a version bump. The two
strengthened oracles must (a) still admit their references through every
curator gate and (b) now REFUSE the exact mutants that passed hard_v2.
The other 108 records are byte-identical to v2: comparability is the
point of versioning, so the diff is exactly the fix."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from harness.task_curator import _run_with, screen
from oracle_strength_audit import _mutant
from run_uplift_live import load_specs

ROOT = Path(__file__).resolve().parents[1]
UPGRADED = ("json_string_escape", "days_in_month")


def _specs(lane):
    return {s.task_id: s for s in load_specs(str(ROOT / "tasks" / "curated"
                                                 / lane))}


def test_v3_upgraded_references_clear_every_gate(tmp_path):
    v3 = _specs("hard_v3.jsonl")
    for tid in UPGRADED:
        r = screen(v3[tid], tmp_path)
        assert r["admitted"], (tid, r["gates"])


@pytest.mark.parametrize("tid", UPGRADED)
def test_v3_refuses_the_mutant_that_passed_v2(tmp_path, tid):
    v3 = _specs("hard_v3.jsonl")
    mut = _mutant(v3[tid].solution)
    assert mut is not None
    assert _run_with(v3[tid], tmp_path, mut, "mutant") is False, \
        f"{tid}: the audit mutant still passes; the strengthening is fake"


def test_v3_differs_from_v2_only_in_the_two_fixes():
    v2 = {json.loads(l)["task_id"]: l.strip() for l in
          open(ROOT / "tasks" / "curated" / "hard_v2.jsonl",
               encoding="utf-8") if l.strip()}
    v3 = {json.loads(l)["task_id"]: l.strip() for l in
          open(ROOT / "tasks" / "curated" / "hard_v3.jsonl",
               encoding="utf-8") if l.strip()}
    assert set(v2) == set(v3) and len(v3) == 110
    changed = {t for t in v3 if v2[t] != v3[t]}
    assert changed == set(UPGRADED), changed
