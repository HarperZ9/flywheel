"""7.8 stage A: gateway traces become bench tasks in private custody. A run
with a gate command and a failing verdict becomes a task; a run without a
gate is skipped and counted; a non-git workspace, tracked changes or
untracked files at start give UNREPRODUCIBLE, ignored files do not; tasks
are encrypted and carry lineage and content_trust; a deletion plan for the
trace lists its tasks."""
import pytest

from bench_fixtures import git_repo, plant_run
from delete_fixtures import OWNER
from harness.trace_bench_tasks import BenchTasks, build_tasks
from harness.trace_delete_apply import apply_plan
from harness.trace_delete_plan import make_plan
from harness.trace_presence import confirm
from harness.trace_witness import MemorySink
from trace_enc_fakes import StreamTestProvider, using


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(tmp_path / "run"))
    with using(StreamTestProvider()):
        yield home, git_repo(tmp_path)


def _op(n: int) -> str:
    return f"op_{n:032x}"


def test_a_failing_run_with_a_gate_becomes_a_reproducible_task(world):
    home, repo = world
    (repo / ".venv").mkdir()
    (repo / ".venv" / "cache.bin").write_bytes(b"ignored")
    trace = plant_run(home, repo, operation=_op(1))
    report = build_tasks(home, OWNER)
    assert report["tasks"] == 1 and report["classes"] == {"REPRODUCIBLE": 1}
    store = BenchTasks(home, OWNER)
    (row,) = store.index()
    task = store.read(row["task_ref"])
    assert task["schema"] == "flywheel.trace-task/v2" and task["trace_ref"] == trace
    assert task["prior_verdict"] == "FAIL" and task["class"] == "REPRODUCIBLE"
    assert task["goal"] == "make add work" and task["endpoint"] == "ep-one"
    assert task["content_trust"] == "owner"
    stored = b"".join(p.read_bytes() for p in (home / "state" / "trace-bench").rglob("*")
                      if p.is_file())
    assert b"make add work" not in stored
    assert build_tasks(home, OWNER)["tasks"] == 0, "one task per trace"


def test_no_gate_is_skipped_and_counted(world):
    home, repo = world
    plant_run(home, repo, operation=_op(2), test_cmd=None)
    report = build_tasks(home, OWNER)
    assert report["tasks"] == 0 and report["skipped"] == {"NO_GATE": 1}


def test_unreproducible_classes_have_reasons(world, tmp_path):
    home, repo = world
    plant_run(home, repo, operation=_op(3), identity=False)
    (repo / "scratch.txt").write_text("untracked at start\n")
    plant_run(home, repo, operation=_op(4))
    (repo / "scratch.txt").unlink()
    (repo / "calc.py").write_text("def add(a, b):\n    return 0\n")
    plant_run(home, repo, operation=_op(5))
    build_tasks(home, OWNER)
    reasons = sorted(r["reason"] for r in BenchTasks(home, OWNER).index())
    assert reasons == ["DIRTY_AT_START", "DIRTY_AT_START", "NOT_A_GIT_TREE"]
    assert all(r["class"] == "UNREPRODUCIBLE" for r in BenchTasks(home, OWNER).index())


def test_a_goal_built_from_fetched_content_is_untrusted(world):
    home, repo = world
    from harness.evidence_json import canonical_sha256
    from harness.source_context_worker import WORKER_SCHEMA
    unsigned = {"schema": WORKER_SCHEMA, "contexts": []}
    context = {**unsigned, "source_payload_sha256": canonical_sha256(unsigned)}
    plant_run(home, repo, operation=_op(6), source_context=context)
    build_tasks(home, OWNER)
    store = BenchTasks(home, OWNER)
    assert store.read(store.index()[0]["task_ref"])["content_trust"] == "untrusted"


def test_deleting_the_trace_deletes_its_tasks(world):
    home, repo = world
    trace = plant_run(home, repo, operation=_op(7))
    build_tasks(home, OWNER)
    task_ref = BenchTasks(home, OWNER).index()[0]["task_ref"]
    plan = make_plan(home, OWNER, {"trace_refs": [trace]})
    assert ("BT", task_ref) in {(e["store"], e["item"]) for e in plan["entries"]}
    ref = confirm(home / "state", OWNER, "delete_apply", plan["plan_digest"], "delete")
    report = apply_plan(home, OWNER, plan["plan_digest"], ref, sink=MemorySink())
    assert report["state"] == "DELETED", report
    assert BenchTasks(home, OWNER).index() == []
    assert not list((home / "state" / "trace-bench").rglob("*.enc"))
