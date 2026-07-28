"""The endpoint driver, and above all its two refusals.

The interesting tests here are the ones that assert the tool CANNOT do
something. Section 7 forbids interim analysis, so a driver that merely declines
to look early by convention is worth nothing; it has to be unable to. These
fixtures satisfy the guards honestly, by building a pool whose journal really
does carry run_end, rather than by switching a guard off. There is no flag to
switch off, which is the point.

Loaded the importlib way, since scripts/ is not a package.
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

_spec = importlib.util.spec_from_file_location(
    "compute_endpoint", ROOT / "scripts" / "compute_endpoint.py")
ce = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ce)

from harness.endpoint import body_digest                            # noqa: E402

FAMILY = "zarankiewicz"
CRITERION = "zarankiewicz.z_2_2.v1"
RUNGS = ["fake-a", "fake-b"]
# Neither body needs to be a VALID certificate. The endpoint asserts that one
# body yields one verdict wherever it is submitted, which is a question about
# consistency, not about correctness.
BODIES = ["this is not a certificate at all",
          json.dumps({"m": 3, "n": 3, "s": 2, "t": 2, "edges": [[0, 0]]})]


def _write_pool(root: Path, family: str, rung: str, task_ids, bodies):
    d = root / family / rung.replace(":", "_")
    (d / "candidates").mkdir(parents=True, exist_ok=True)
    entries = []
    for i, task_id in enumerate(task_ids):
        slots = []
        for j, body in enumerate(bodies):
            sha = body_digest(body)
            (d / "candidates" / (sha.split(":", 1)[-1] + ".txt")).write_text(
                body, encoding="utf-8")
            slots.append({"slot": j, "seed": j, "temperature": 0,
                          "candidate_sha256": sha, "error": None})
        entries.append({"task_id": task_id, "prompt_sha256": f"sha256:{i:064d}",
                        "slots": slots})
    (d / "pool_index.json").write_text(json.dumps(
        {"schema": "flywheel.candidate-pool/v1", "n_tasks": len(entries),
         "entries": entries}), encoding="utf-8")
    return d


def _journal(root: Path, with_run_end: bool) -> Path:
    p = root / "confirmatory-journal.jsonl"
    lines = [{"event": "run_start", "pairs": 2},
             {"event": "pair_done", "family": FAMILY, "rung": RUNGS[0],
              "exit_code": 0, "wall_seconds": 1.0}]
    if with_run_end:
        lines.append({"event": "run_end", "pairs_failed": 0})
    p.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    return p


def _ledger(root: Path) -> Path:
    p = root / "ledger.jsonl"
    p.write_text(json.dumps({
        "kind": "prereg-freeze", "seq": 0,
        "criterion_sha256": {CRITERION: "a" * 64,
                             "rectilinear_crossing.count.v1": "b" * 64},
    }), encoding="utf-8")
    return p


def _task_ids(n=2):
    fill = ce._load("run_demo_pool")
    return [fill.task_id_for(FAMILY, inst)
            for inst in fill.build_instances(FAMILY)[:n]]


def _complete(tmp_path, with_run_end=True, rungs=RUNGS):
    pool = tmp_path / "pool"
    ids = _task_ids()
    for rung in rungs:
        _write_pool(pool, FAMILY, rung, ids, BODIES)
    return pool, _journal(pool, with_run_end), _ledger(tmp_path)


# --- the refusals -----------------------------------------------------------

def test_it_refuses_while_the_pass_is_still_running(tmp_path):
    pool, journal, ledger = _complete(tmp_path, with_run_end=False)
    with pytest.raises(ce.EndpointGate) as e:
        ce.compute(pool, journal, [FAMILY], RUNGS, ledger)
    assert "run_end" in str(e.value)


def test_it_refuses_when_there_is_no_journal_at_all(tmp_path):
    pool, _, ledger = _complete(tmp_path)
    with pytest.raises(ce.EndpointGate):
        ce.compute(pool, tmp_path / "nope.jsonl", [FAMILY], RUNGS, ledger)


def test_it_refuses_a_pass_with_a_pair_missing(tmp_path):
    """The primary endpoint is the union over ALL rungs. Computing it over the
    rungs that happen to be present answers a different question."""
    pool, journal, ledger = _complete(tmp_path, rungs=[RUNGS[0]])
    with pytest.raises(ce.EndpointGate) as e:
        ce.compute(pool, journal, [FAMILY], RUNGS, ledger)
    assert RUNGS[1] in str(e.value)


def test_it_refuses_an_index_naming_a_candidate_that_is_not_there(tmp_path):
    pool, journal, ledger = _complete(tmp_path)
    victim = next((pool / FAMILY / RUNGS[0] / "candidates").glob("*.txt"))
    victim.unlink()
    with pytest.raises(ce.EndpointGate) as e:
        ce.compute(pool, journal, [FAMILY], RUNGS, ledger)
    assert "missing" in str(e.value).lower()


def test_it_refuses_a_criterion_that_was_never_pinned(tmp_path):
    pool, journal, ledger = _complete(tmp_path)
    ledger.write_text(json.dumps({"kind": "prereg-freeze", "seq": 0,
                                  "criterion_sha256": {"something.else": "c" * 64}}),
                      encoding="utf-8")
    with pytest.raises(ce.EndpointGate) as e:
        ce.compute(pool, journal, [FAMILY], RUNGS, ledger)
    assert "pinned" in str(e.value)


def test_the_cli_exits_three_rather_than_crashing(tmp_path):
    pool, journal, ledger = _complete(tmp_path, with_run_end=False)
    code = ce.main(["--pool-root", str(pool), "--journal", str(journal),
                    "--ledger", str(ledger), "--out", str(tmp_path / "out")])
    assert code == 3
    assert not (tmp_path / "out").exists(), "a refused run wrote a report anyway"


# --- the happy path ---------------------------------------------------------

def test_a_complete_pass_yields_the_primary_and_secondary_endpoints(tmp_path):
    pool, journal, ledger = _complete(tmp_path)
    report = ce.compute(pool, journal, [FAMILY], RUNGS, ledger)
    block = report["families"][FAMILY]
    primary = block["primary"]
    assert primary["n_bodies"] == len(BODIES)
    assert primary["n_disagreements"] == 0
    assert primary["met"] is True
    assert primary["rung_contexts"] == sorted(RUNGS)
    assert block["criterion_id"] == CRITERION
    assert report["pinned_criterion_sha256"][CRITERION] == "a" * 64
    for rung in RUNGS:
        row = block["secondary"]["per_rung"][rung]
        assert row["graded_slots"] == len(BODIES) * 2      # two tasks
        assert sum(row["verdicts"].values()) == row["graded_slots"]


def test_the_unparseable_body_is_counted_as_not_well_formed(tmp_path):
    pool, journal, ledger = _complete(tmp_path)
    report = ce.compute(pool, journal, [FAMILY], RUNGS, ledger)
    row = report["families"][FAMILY]["secondary"]["per_rung"][RUNGS[0]]
    # One of the two bodies is prose, the other is JSON: exactly half parse.
    assert row["well_formed"] == row["graded_slots"] // 2


def test_the_pinned_digest_actually_reaches_the_subject(tmp_path):
    """A digest recomputed from present-day code would paper over exactly the
    drift the pin exists to catch. Asserting the report merely ECHOES the pin
    would not show it was used, so this checks the subject digest itself moves
    when the pin moves, and that nothing else does."""
    fill = ce._load("run_demo_pool")
    instances = {fill.task_id_for(FAMILY, i): i
                 for i in fill.build_instances(FAMILY)}
    task_id = _task_ids(1)[0]
    args = (FAMILY, CRITERION)
    rest = (instances, {task_id: "sha256:" + "0" * 64}, "sha256:" + "e" * 64)
    a = ce.make_submit(*args, "a" * 64, *rest)(BODIES[1], task_id, RUNGS[0])
    b = ce.make_submit(*args, "d" * 64, *rest)(BODIES[1], task_id, RUNGS[0])
    assert a["subject_digest"] != b["subject_digest"]
    # The verdict is a property of the certificate, so it must NOT move.
    assert a["verdict_digest"] == b["verdict_digest"]
    assert a["verdict"] == b["verdict"]


def test_compute_hands_the_pinned_digest_to_the_submit_it_builds(tmp_path,
                                                                 monkeypatch):
    """The wiring, not the parts. Checking make_submit in isolation proves the
    function uses what it is given; this proves compute() gives it the PIN and
    not something it recomputed. Without this the pinned value could be replaced
    by a constant and every other test here would stay green."""
    seen = {}
    real = ce.make_submit

    def spy(family, criterion_id, criterion_sha256, *a, **kw):
        seen["criterion_sha256"] = criterion_sha256
        return real(family, criterion_id, criterion_sha256, *a, **kw)

    monkeypatch.setattr(ce, "make_submit", spy)
    pool, journal, ledger = _complete(tmp_path)
    ce.compute(pool, journal, [FAMILY], RUNGS, ledger)
    assert seen["criterion_sha256"] == "a" * 64


def test_the_rung_changes_neither_digest(tmp_path):
    """The endpoint's whole premise. If a rung could move either digest, the
    accept path would not be a function of the certificate and the measurement
    would be reporting the harness rather than the candidate."""
    fill = ce._load("run_demo_pool")
    instances = {fill.task_id_for(FAMILY, i): i
                 for i in fill.build_instances(FAMILY)}
    task_id = _task_ids(1)[0]
    submit = ce.make_submit(FAMILY, CRITERION, "a" * 64, instances,
                            {task_id: "sha256:" + "0" * 64},
                            "sha256:" + "e" * 64)
    first = submit(BODIES[1], task_id, "rung-one")
    second = submit(BODIES[1], task_id, "rung-two-entirely-different")
    assert first == second


def test_the_family_qualifier_travels_into_the_endpoint(tmp_path):
    """Section 8 mechanism 1: NOT_PROVES_OPTIMALITY travels with every result.
    The prereg names this the single most likely thing to be lost when a result
    is retold, so an endpoint that reported only its own limits would drop
    exactly the clause that matters most."""
    pool, journal, ledger = _complete(tmp_path)
    report = ce.compute(pool, journal, [FAMILY], RUNGS, ledger)
    joined = " ".join(report["families"][FAMILY]["primary"]["does_not_prove"])
    assert "NOT_PROVES_OPTIMALITY" in joined
    assert "NOT_PROVES_CORRECTNESS" in joined      # and its own limits survive


def test_the_submit_result_carries_the_checkers_qualifiers(tmp_path):
    fill = ce._load("run_demo_pool")
    instances = {fill.task_id_for(FAMILY, i): i
                 for i in fill.build_instances(FAMILY)}
    task_id = _task_ids(1)[0]
    submit = ce.make_submit(FAMILY, CRITERION, "a" * 64, instances,
                            {task_id: "sha256:" + "0" * 64}, "sha256:" + "e" * 64)
    out = submit(BODIES[1], task_id, RUNGS[0])
    assert any("NOT_PROVES_OPTIMALITY" in d for d in out["does_not_prove"])
