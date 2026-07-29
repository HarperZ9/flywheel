"""The renderer: a formatter that computes nothing, tested end to end.

The fixture runs the REAL drivers over a tiny pool and renders their actual
artifacts, so a driver whose output shape drifts breaks this suite instead of
breaking the renderer silently at run_end. Handcrafted report dicts would have
tested the renderer against a shape nobody produces.

The assertions are the prereg's own rendering rules: rung-id order, confounds
inline with every table, the MDE next to every comparison including the null,
the self-scored refusal printed rather than dropped, and the optimality
qualifier surviving into the record.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def _mod(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


rr = _mod("render_report")
ca = _mod("compute_arms")
ce = ca._load_compute_endpoint()

from harness.pool import fill                                       # noqa: E402

FAMILY = "zarankiewicz"
RUNGS = ["fake-a", "fake-b"]


class _Proposer:
    def __init__(self, text):
        self.text = text

    def generate(self, prompt, *, seed, temperature, max_new_tokens):
        class R:
            text = self.text
        return R()


def _valid_for(instance) -> str:
    return json.dumps({"m": instance["m"], "n": instance["n"],
                       "s": instance["s"], "t": instance["t"],
                       "edges": [], "edge_count": 0})


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    """One real pool -> both real drivers -> the rendered record."""
    tmp = tmp_path_factory.mktemp("render")
    fill_mod = ce._load("run_demo_pool")
    instances = {fill_mod.task_id_for(FAMILY, i): i
                 for i in fill_mod.build_instances(FAMILY)}
    task_ids = sorted(instances)[:1]
    pool = tmp / "pool"
    fp = dict(model_ref="t", model_digest=None, engine="t", engine_version="0",
              quantization="none", k=2, seeds=[0, 1], temperatures=[0.0, 0.5],
              max_new_tokens=32, prompt_template_sha256=None)
    for rung in RUNGS:
        fill([{"task_id": t, "prompt": t} for t in task_ids],
             _Proposer(_valid_for(instances[task_ids[0]])), fp,
             pool / FAMILY / rung)
    journal = pool / "confirmatory-journal.jsonl"
    journal.write_text(json.dumps({"event": "run_end", "pairs_failed": 0}),
                       encoding="utf-8")
    ledger = tmp / "ledger.jsonl"
    ledger.write_text(json.dumps({
        "kind": "prereg-freeze", "seq": 0,
        "criterion_sha256": {"zarankiewicz.z_2_2.v1": "a" * 64,
                             "rectilinear_crossing.count.v1": "b" * 64}}),
        encoding="utf-8")

    reports = tmp / "reports"
    reports.mkdir()
    ep = ce.compute(pool, journal, [FAMILY], RUNGS, ledger)
    ar = ca.compute(pool, journal, [FAMILY], RUNGS)
    (reports / "endpoint-report.json").write_text(
        json.dumps(ep, indent=1, sort_keys=True), encoding="utf-8")
    (reports / "arms-report.json").write_text(
        json.dumps(ar, indent=1, sort_keys=True), encoding="utf-8")
    code = rr.main(["--reports", str(reports)])
    assert code == 0
    return (reports / "confirmatory-report.md").read_text(encoding="utf-8")


# --- refusals ---------------------------------------------------------------

def test_it_refuses_when_a_driver_artifact_is_missing(tmp_path):
    assert rr.main(["--reports", str(tmp_path)]) == 3
    assert not (tmp_path / "confirmatory-report.md").exists()


def test_it_refuses_a_schema_it_does_not_know(tmp_path):
    (tmp_path / "endpoint-report.json").write_text(
        json.dumps({"schema": "something/else"}), encoding="utf-8")
    (tmp_path / "arms-report.json").write_text(
        json.dumps({"schema": "flywheel.pool-arm/v1"}), encoding="utf-8")
    assert rr.main(["--reports", str(tmp_path)]) == 3


# --- the prereg's rendering rules -------------------------------------------

def test_the_primary_endpoint_text_is_quoted_verbatim(rendered):
    assert "N distinct certificate bodies" in rendered
    assert "endpoint met: True" in rendered


def test_the_four_way_denominator_keeps_its_zeros(rendered):
    """Header names alone would survive a renderer that drops zero cells, so
    this counts cells: every data row of the secondary table must carry one
    cell per header column, zeros included, or a reader cannot tell an absent
    category from one that was never possible."""
    for v in ("PASS", "FAIL", "UNDECIDED", "UNVERIFIABLE"):
        assert v in rendered
    lines = rendered.splitlines()
    header_i = next(i for i, l in enumerate(lines)
                    if l.startswith("| rung |"))
    n_cols = lines[header_i].count("|") - 1
    for row in lines[header_i + 2:]:
        if not row.startswith("|"):
            break
        assert row.count("|") - 1 == n_cols, f"short row: {row}"
    # And the fixture really does exercise a zero: every candidate is valid,
    # so FAIL, UNDECIDED and UNVERIFIABLE are all zero in the data rows.
    first_row = lines[header_i + 2]
    assert first_row.count(" 0 ") >= 3, first_row


def test_rungs_appear_in_rung_id_order(rendered):
    assert rendered.index("fake-a") < rendered.index("fake-b")


def test_confounds_print_inline_with_every_table(rendered):
    # Once under the secondary table, once per arms rung table: >= 3 here.
    assert rendered.count("Confounds, inline with this table by design:") >= 3
    assert "token asymmetry" in rendered


def test_the_mde_prints_next_to_every_comparison_including_the_null(rendered):
    # Every candidate in the fixture is valid, so the discordant count is zero
    # and the MDE must say the null carries no information.
    assert rendered.count("- MDE:") >= 2
    assert "carries no information" in rendered


def test_the_self_scored_refusal_is_printed_not_dropped(rendered):
    assert "REFUSED: SELF_SCORED_ARM" in rendered


def test_the_optimality_qualifier_survives_into_the_record(rendered):
    assert "NOT_PROVES_OPTIMALITY" in rendered


def test_the_record_names_its_inputs_by_hash(rendered):
    assert "endpoint-report.json" in rendered and "sha256" in rendered


def test_no_em_dash_reaches_the_record(rendered):
    assert chr(8212) not in rendered
