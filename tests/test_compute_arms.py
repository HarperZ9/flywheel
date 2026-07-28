"""The arms driver: its refusals, its bound accept, and its kept refusal.

Three things are worth testing here and one of them is easy to miss.

  * The run_end guard must produce a clean refusal and exit 3, not a traceback.
    It did produce a traceback at first, because the module was importlib-loaded
    twice and the two EndpointGate classes were not the same class.
  * Every accept function must be BOUND to the instance, or an arm scores a
    certificate for an easier problem as a pass.
  * The self-scored comparison must still be REFUSED in the output. Deleting the
    call would hide the enforcement rather than demonstrate it.
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


ca = _mod("compute_arms")

from harness.pool import fill                                       # noqa: E402
from harness.verdict import Verdict                                 # noqa: E402

FAMILY = "zarankiewicz"
RUNGS = ["fake-a", "fake-b"]


def _valid_for(instance) -> str:
    """A certificate that answers the instance it was given, with no edges. An
    empty edge set is K_{2,2}-free, so this is valid and uninteresting, which is
    all the driver needs."""
    return json.dumps({"m": instance["m"], "n": instance["n"],
                       "s": instance["s"], "t": instance["t"],
                       "edges": [], "edge_count": 0})


def _instances():
    fill_mod = ca._load_compute_endpoint()._load("run_demo_pool")
    return {fill_mod.task_id_for(FAMILY, i): i
            for i in fill_mod.build_instances(FAMILY)}


class _Proposer:
    def __init__(self, text):
        self.text = text

    def generate(self, prompt, *, seed, temperature, max_new_tokens):
        class R:
            text = self.text
        return R()


def _pool_dir(root: Path, rung: str, task_ids, instances) -> Path:
    d = root / FAMILY / rung
    fp = dict(model_ref="t", model_digest=None, engine="t", engine_version="0",
              quantization="none", k=2, seeds=[0, 1], temperatures=[0.0, 0.5],
              max_new_tokens=32, prompt_template_sha256=None)
    tasks = [{"task_id": t, "prompt": t} for t in task_ids]
    fill(tasks, _Proposer(_valid_for(instances[task_ids[0]])), fp, d)
    return d


def _fixture(tmp_path, with_run_end=True):
    instances = _instances()
    task_ids = sorted(instances)[:1]
    pool = tmp_path / "pool"
    for rung in RUNGS:
        _pool_dir(pool, rung, task_ids, instances)
    journal = pool / "confirmatory-journal.jsonl"
    rows = [{"event": "run_start", "pairs": 2}]
    if with_run_end:
        rows.append({"event": "run_end", "pairs_failed": 0})
    journal.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return pool, journal, task_ids, instances


# --- the refusals -----------------------------------------------------------

def test_it_refuses_while_the_pass_is_still_running(tmp_path):
    pool, journal, _, _ = _fixture(tmp_path, with_run_end=False)
    ce = ca._load_compute_endpoint()
    with pytest.raises(ce.EndpointGate):
        ca.compute(pool, journal, [FAMILY], RUNGS)


def test_the_cli_refuses_cleanly_rather_than_raising(tmp_path):
    """The bug this catches: compute_arms and its caller each importlib-loaded
    compute_endpoint, so `except EndpointGate` named a different class than the
    one raised and a clean refusal came out as a traceback with exit 1."""
    pool, journal, _, _ = _fixture(tmp_path, with_run_end=False)
    assert ca.main(["--pool-root", str(pool), "--journal", str(journal),
                    "--out", str(tmp_path / "out")]) == 3
    assert not (tmp_path / "out").exists()


def test_the_gate_class_is_one_class(tmp_path):
    """Directly, so the fix cannot silently regress into two module objects."""
    assert ca._load_compute_endpoint() is ca._load_compute_endpoint()


# --- the accept is bound ----------------------------------------------------

def test_the_accept_is_bound_to_the_instance(tmp_path):
    from harness.certificates.zarankiewicz import ZarankiewiczOracle
    instances = _instances()
    task_id = sorted(instances)[0]
    accept = ca.make_accept(ZarankiewiczOracle(), instances)
    assert accept(_valid_for(instances[task_id]), task_id) is True
    # Valid for a 2x2 problem, and not for the one this task asked about.
    easier = json.dumps({"m": 2, "n": 2, "s": 2, "t": 2,
                         "edges": [[0, 0], [1, 1]], "edge_count": 2})
    assert accept(easier, task_id) is False


def test_the_placebo_rate_is_measured_not_assumed(tmp_path):
    from harness.certificates.zarankiewicz import ZarankiewiczOracle
    from harness.pool import Pool
    pool, _, task_ids, instances = _fixture(tmp_path)
    p = Pool(pool / FAMILY / RUNGS[0])
    accept = ca.make_accept(ZarankiewiczOracle(), instances)
    assert ca.observed_accept_rate(p, accept) == 1.0
    reject = lambda text, task_id: False
    assert ca.observed_accept_rate(p, reject) == 0.0


# --- the whole thing --------------------------------------------------------

def test_a_complete_pass_yields_every_arm_and_keeps_the_refusal(tmp_path):
    pool, journal, _, _ = _fixture(tmp_path)
    report = ca.compute(pool, journal, [FAMILY], RUNGS)
    block = report["families"][FAMILY]
    assert block["primary_checker"] != block["held_out_checker"]
    row = block["per_rung"][RUNGS[0]]
    assert set(row["arms"]) == {"single", "best_of_k_self_scored",
                                "best_of_k_held_out", "random_of_k",
                                "placebo_of_k", "pass_at_k"}
    # The self-scored comparison is kept AND refused: that is the evidence the
    # rule is enforced in code rather than described in a document.
    self_scored = row["comparisons"]["random_vs_best_self_scored"]
    assert self_scored["p_exact"] is None
    assert "SELF_SCORED_ARM" in self_scored["refused"]
    # The held-out comparison is allowed to carry a statistic.
    held = row["comparisons"]["random_vs_best_held_out"]
    assert "refused" not in held
    assert held["p_exact"] is not None
    assert row["selection_seed"] == ca.SELECTION_SEED
    # The MEASURED rate must reach the report, not a stand-in: every
    # candidate in this fixture answers its instance, so it is exactly 1.0.
    assert row["observed_accept_rate"] == 1.0


def test_every_comparison_carries_a_declared_mde(tmp_path):
    """Section 6: the MDE travels next to every result, including every null.
    Attached by the driver rather than by whoever writes the report, so a
    comparison cannot reach a reader without it."""
    pool, journal, _, _ = _fixture(tmp_path)
    report = ca.compute(pool, journal, [FAMILY], RUNGS)
    for rung, row in report["families"][FAMILY]["per_rung"].items():
        for name, comp in row["comparisons"].items():
            assert "mde" in comp, f"{rung}/{name} has no declared MDE"
            mde = comp["mde"]
            assert mde["n_pairs"] == comp["n_paired"]
            assert mde["n_discordant"] == comp["discordant"]
            assert "NOT_PROVES_AN_EFFECT_IS_ABSENT" in " ".join(
                mde["does_not_prove"])


def test_a_null_with_too_few_discordant_pairs_says_it_is_underpowered(tmp_path):
    """The distinction the MDE exists to draw. Every candidate in this fixture
    is valid, so no arm disagrees with another and the discordant count is zero:
    the design could not have called ANY effect, and the record says so instead
    of reporting a clean null."""
    pool, journal, _, _ = _fixture(tmp_path)
    report = ca.compute(pool, journal, [FAMILY], RUNGS)
    comp = report["families"][FAMILY]["per_rung"][RUNGS[0]][
        "comparisons"]["random_vs_best_held_out"]
    assert comp["discordant"] == 0
    assert comp["mde"]["detectable"] is None
    assert "carries no information" in comp["mde"]["note"]
