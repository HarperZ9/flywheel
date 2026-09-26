"""7.8 stage B2, I16, I17: a bulk replay names its endpoints and has the
owner's presence. No endpoints gives ENDPOINTS_REQUIRED; a planted
credential in a goal is refused before any transport call; a replay without
presence is refused; the presence summary lists each goal and endpoint;
each task keeps the capabilities its original run had."""
import pytest

from bench_fixtures import git_repo, plant_run
from delete_fixtures import OWNER
from harness import trace_bench_replay
from harness.trace_bench_grant import handle, plan_grant
from harness.trace_presence import confirm
from trace_enc_fakes import StreamTestProvider, using
from trace_redact_fakes import credential_fakes

TOKEN = credential_fakes()["github_token"]


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(tmp_path / "run"))
    calls = []
    monkeypatch.setattr(trace_bench_replay, "replay_one",
                        lambda home, owner, task, endpoint, proposer=None: calls.append(
                            (task["task_ref"], endpoint, task["capabilities"])) or
                        trace_bench_replay._result(task, endpoint, "PASS"))
    with using(StreamTestProvider()):
        yield home, git_repo(tmp_path), calls


def test_no_endpoints_is_refused_with_the_statement(world):
    home, repo, calls = world
    plant_run(home, repo, operation="op_" + "1" * 32)
    for body in ({}, {"endpoints": []}):
        doc, status = handle(home, OWNER, body)
        assert status == 422 and doc["code"] == "ENDPOINTS_REQUIRED"
        assert "goal text" in doc["statement"]
    assert calls == []


def test_a_credential_in_a_goal_is_refused_before_any_transport(world):
    home, repo, calls = world
    # The trace guard refuses a credential at write time, so a goal holds one
    # only when the catalog learned a rule after the task was built. Model
    # that by sealing such a task directly.
    from harness.trace_bench_tasks import BenchTasks, build_tasks
    plant_run(home, repo, operation="op_" + "2" * 32)
    build_tasks(home, OWNER)
    store = BenchTasks(home, OWNER)
    task = store.read(store.index()[0]["task_ref"])
    store.add({**task, "task_ref": "tsk_" + "9" * 32, "trace_ref": "agt_" + "9" * 32,
               "goal": "use " + TOKEN + " to fix add"})
    doc, status = handle(home, OWNER, {"endpoints": ["ep-one"]})
    assert status == 422 and doc["code"] == "CREDENTIAL_IN_GOAL"
    assert TOKEN not in str(doc)
    assert calls == []


def test_a_replay_without_presence_is_refused(world):
    home, repo, calls = world
    plant_run(home, repo, operation="op_" + "3" * 32)
    plan, status = handle(home, OWNER, {"endpoints": ["ep-one"]})
    assert status == 202
    body = {"endpoints": ["ep-one"], "grant_digest": plan["grant_digest"],
            "presence_ref": "prs_" + "0" * 32}
    doc, status = handle(home, OWNER, body)
    assert status == 403 and calls == []
    other = confirm(home / "state", OWNER, "bench_replay", "e" * 64, "other")
    doc, status = handle(home, OWNER, {**body, "presence_ref": other})
    assert status == 403 and calls == []


def test_the_summary_lists_each_goal_and_endpoint_then_replays(world):
    home, repo, calls = world
    plant_run(home, repo, operation="op_" + "4" * 32, goal="fix add please")
    grant = plan_grant(home, OWNER, ["ep-one", "ep-two"])
    assert "fix add please" in grant["summary_text"]
    assert "ep-one" in grant["summary_text"] and "ep-two" in grant["summary_text"]
    ref = confirm(home / "state", OWNER, "bench_replay", grant["grant_digest"],
                  grant["summary_text"])
    doc, status = handle(home, OWNER, {"endpoints": ["ep-one", "ep-two"],
                                       "grant_digest": grant["grant_digest"],
                                       "presence_ref": ref})
    assert status == 200 and len(doc["results"]) == 2
    assert {c[1] for c in calls} == {"ep-one", "ep-two"}
    assert all(c[2] == {"allow_write": True, "allow_exec": True} for c in calls)


def test_a_grant_whose_tasks_changed_is_refused(world):
    home, repo, calls = world
    plant_run(home, repo, operation="op_" + "5" * 32)
    grant = plan_grant(home, OWNER, ["ep-one"])
    plant_run(home, repo, operation="op_" + "6" * 32, goal="a second goal")
    ref = confirm(home / "state", OWNER, "bench_replay", grant["grant_digest"], "x")
    doc, status = handle(home, OWNER, {"endpoints": ["ep-one"],
                                       "grant_digest": grant["grant_digest"],
                                       "presence_ref": ref})
    assert status == 409 and doc["code"] == "GRANT_DRIFTED" and calls == []


def test_the_route_needs_the_token_and_takes_no_path(tmp_path, monkeypatch):
    from capture_channel_fixture import running_gateway
    from test_trace_delete_route import _post
    home = tmp_path / "gw"
    home.mkdir()
    (home / "owner.ref").write_text(OWNER)
    with using(StreamTestProvider()), running_gateway(home, monkeypatch) as server:
        port = server.server_address[1]
        token = (home / "gateway.token").read_text().strip()
        assert _post(port, "/api/traces/bench", {"endpoints": ["ep-one"]})[0] == 401
        status, doc = _post(port, "/api/traces/bench", {}, token)
        assert status == 422 and doc["code"] == "ENDPOINTS_REQUIRED"
        status, _ = _post(port, "/api/traces/bench", {"endpoints": ["ep-one"],
                                                      "workspace": "C:/x"}, token)
        assert status == 422
