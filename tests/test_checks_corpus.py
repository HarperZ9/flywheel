"""The shared checks against the false-accept corpus and known-good controls.

Success criteria (bar from the synthesis, P4):
- the checks catch at least 30 of the 40 false accepts; the expected count is
  exactly 38, and the two misses are the items marked known_limit;
- zero false rejects on at least 200 known-good items: the 40 fixed twins, the
  120 reference solutions of the shipped hard sets (AST), search traces built
  from the G4 records (FSM), sentences quoted from a shipped doc (value on page),
  the G4 summaries recomputed from their rows, and every check receipt the run
  produced (schema);
- false-success control: an always-PASS checker catches 0 of 40;
- paired mutation per check: a weakened version of each check catches fewer of
  that kind's false accepts, so each kind's test has teeth;
- the corpus file is exactly what scripts/build_false_accept_corpus.py builds.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from harness import checks
from harness.checks import CHECKS, PASS, run
from harness.checks.evidence import recompute_check, value_on_page_check
from harness.checks.receipt import SCHEMA
from harness.checks.structural import ast_check, fsm_check, schema_check

ROOT = Path(__file__).resolve().parent.parent
CORPUS = json.loads((ROOT / "tests/fixtures/checks/false_accepts_v1.json").read_text("utf-8"))
ITEMS = CORPUS["items"]
G4 = ROOT / "project-docs/records/1.3.0/g4-heldout-rerun"


def caught(kind: str | None = None) -> int:
    return sum(run(it["kind"], it["subject"], it["spec"]).verdict != PASS
               for it in ITEMS if kind in (None, it["kind"]))


def test_corpus_shape_and_provenance():
    assert len(ITEMS) == 40
    assert {it["kind"] for it in ITEMS} == set(CHECKS)
    assert all(it["provenance"].split(":")[0] in ("observed", "pattern") for it in ITEMS)


def test_corpus_matches_its_builder():
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_false_accept_corpus import build
    assert build() == CORPUS


def test_bar_catches_38_of_40_and_misses_only_known_limits():
    missed = [it["id"] for it in ITEMS
              if run(it["kind"], it["subject"], it["spec"]).verdict == PASS]
    assert len(ITEMS) - len(missed) >= 30
    assert missed == [it["id"] for it in ITEMS if it["known_limit"]]
    assert caught() == 38


def _known_good() -> list[tuple[str, object, dict]]:
    out = [(it["kind"], it["fixed"], it.get("fixed_spec", it["spec"])) for it in ITEMS]
    from harness.tasks_hard import HARD_REGISTRY
    rows = [json.loads(x) for x in (ROOT / "tasks/curated/hard_v2.jsonl").read_text(
        "utf-8").splitlines() if x]
    out += [("ast", s, {}) for s in [t.solution for t in HARD_REGISTRY] + [r["solution"] for r in rows]]
    out += [("fsm", t, _search_machine()) for t in _g4_traces()]
    page = (ROOT / "docs/features/search-selection.md").read_text("utf-8")
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", page)) if len(s) > 30]
    out += [("value_on_page", s, {"page": page}) for s in sentences[:30]]
    out += _g4_recomputes()
    return out


def _search_machine() -> dict:
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_false_accept_corpus import SEARCH
    return SEARCH


def _g4_traces() -> list[list[str]]:
    traces = []
    for name in ("hard.json", "hard_v2.json"):
        for r in json.loads((G4 / name).read_text("utf-8"))["rows"]:
            decide = ["decide_pass" if r["search_held"] else "decide_fail"]
            if r["single_visible"] and r["self_scored_accept"]:
                traces.append(["draw", "visible_pass"] + decide)
            elif r["self_scored_accept"]:
                traces.append(["draw", "visible_fail", "draw", "visible_pass"] + decide)
            else:
                traces.append(["draw", "visible_fail"] * 4 + ["exhausted"])
    return traces


def _g4_recomputes() -> list[tuple[str, object, dict]]:
    out = []
    for name in ("hard.json", "hard_v2.json"):
        doc = json.loads((G4 / name).read_text("utf-8"))
        rows, s = doc["rows"], doc["summary"]
        single = [int(r["single_held"]) for r in rows]
        search = [int(r["search_held"]) for r in rows]
        fa = [int(r["self_scored_false_accept"]) for r in rows]
        out += [("recompute", s["n"], {"expr": "len(xs)", "inputs": {"xs": single}}),
                ("recompute", s["single_held_pass"][0], {"expr": "sum(xs)", "inputs": {"xs": single}}),
                ("recompute", s["search_held_pass"][0], {"expr": "sum(xs)", "inputs": {"xs": search}}),
                ("recompute", s["self_scored_false_accepts"], {"expr": "sum(xs)", "inputs": {"xs": fa}}),
                ("recompute", s["diff_search_minus_single"],
                 {"expr": "round((sum(a) - sum(b)) / len(a), 4)", "inputs": {"a": search, "b": single}})]
    return out


def test_zero_false_rejects_on_at_least_200_known_good():
    good = _known_good()
    receipts = [run(kind, subject, spec) for kind, subject, spec in good]
    receipt_schema = {"type": "object", "required": ["schema", "verdict", "subject_sha256"],
                      "properties": {"schema": {"const": SCHEMA},
                                     "verdict": {"enum": ["PASS", "FAIL", "UNVERIFIABLE"]},
                                     "subject_sha256": {"type": "string", "pattern": "[0-9a-f]{64}"}}}
    receipts += [run("schema", r.to_dict(), {"schema": receipt_schema}) for r in receipts[:40]]
    rejects = [(r.check, r.code, r.reason) for r in receipts if r.verdict != PASS]
    assert len(receipts) >= 200 and rejects == []


def test_false_success_control_always_pass_catches_nothing(monkeypatch):
    for kind in list(CHECKS):
        monkeypatch.setitem(CHECKS, kind, lambda subject, spec: (PASS, "ok", "ok"))
    assert caught() == 0


def _strip(schema, keys):
    if isinstance(schema, dict):
        return {k: _strip(v, keys) for k, v in schema.items() if k not in keys}
    return schema


MUTANTS = {
    "schema": lambda s, spec: schema_check(s, {"schema": _strip(spec["schema"],
                                                                 {"required", "additionalProperties"})}),
    "ast": lambda s, spec: ast_check(s, dict(spec, reward_hacking=False)),
    "fsm": lambda s, spec: fsm_check(s, dict(spec, accept=list(spec["transitions"]) + [
        n for t in spec["transitions"].values() for n in t.values()])),
    "value_on_page": lambda s, spec: value_on_page_check(str(s).split()[0], spec),
    "recompute": lambda s, spec: (PASS if s == checks.evidence.evaluate(spec["expr"], spec.get(
        "inputs")) else recompute_check(s, spec)[0], "mutant", "== comparison"),
}


@pytest.mark.parametrize("kind", sorted(MUTANTS))
def test_paired_mutation_weakened_check_catches_fewer(kind, monkeypatch):
    before = caught(kind)
    monkeypatch.setitem(CHECKS, kind, MUTANTS[kind])
    assert caught(kind) < before
