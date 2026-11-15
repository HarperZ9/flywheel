"""The routes that were outside the gateway ledger are in it: a start before contact, one end.

Sixth review round of 2.0.0, finding S1 of the fourth independent review.
Seven routes reached a provider and left no gateway-ledger entry:
/api/eval/run, /api/audit/run, /api/bench/run, /api/workflow, /api/plan/run,
/api/capability and the legacy /api/subagents/spawn body. The reviewer's probe
(r4probes/test_p1_unledgered_routes.py) is kept here with its expectation
turned round: each route's handler function is called as `gateway.py` calls
it, `ollama` (or an OpenAI-compatible backend) pointed at a loopback stub, the
home's on-disk ledger open, the process marked as a gateway the way
`gateway.main` marks it.

For each route:
  - every request the stub received has a started entry and exactly one end
    entry in the ledger files, in that order;
  - with the ledger unavailable the route sends nothing;
  - a route process that is killed while the provider answers leaves the
    started entry, and `flywheel gateway-ledger verify` exits 3.

/api/plan/run and the v1 /api/subagents/spawn body both run
`workflows.run_workflow` and `router_agent.run_router_agent`; those two
functions are exercised here, and the spawn body through its handler.
tests/test_gateway_route_reach.py exercises every route over HTTP.
"""
import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from harness import gateway, gateway_ledger, gateway_ledger_cli, gateway_ledger_gate, providers
from tests import gateway_messages_support as support
from tests.gateway_keys_support import turn2

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release
ROSTER = {"endpoints": [{"name": "ollama", "credential": "local-none"}],
          "usable_names": ["ollama"]}


def _release() -> None:
    reach = sys.modules.get("harness.gateway_reach")
    if reach is not None:
        reach.release()


@pytest.fixture
def stubbed(monkeypatch, tmp_path):
    """(upstream, home, tmp): a gateway process with `ollama` at a counting stub."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setattr(gateway, "_ROUTER_LEDGER", None)
    monkeypatch.setattr(gateway, "_unified_roster", lambda: ROSTER)
    upstream = support.Upstream(turn2(40)).__enter__()
    monkeypatch.setitem(providers.REGISTRY, "ollama", replace(
        providers.REGISTRY["ollama"], base_url=f"{upstream.url}/v1"))
    assert gateway_ledger_gate.startup(gateway._router_ledger, out=lambda *_: None)
    yield upstream, home, tmp_path
    _release()
    upstream.__exit__(None, None, None)
    gateway_ledger.close_all()


def entries(home) -> list:
    return [entry for segment in gateway_ledger.check(home) for entry in segment["rows"]]


def paired(upstream, home) -> list:
    """The end entries, after checking one start and one end for each request sent."""
    found = entries(home)
    ends = support.recorded(found)      # each end has its start before it, one end per start
    assert len(upstream.requests) >= 1, "the route did not reach the provider stub"
    assert len(ends) == len(upstream.requests), (
        f"{len(upstream.requests)} request(s) reached the provider and the ledger holds "
        f"{len(ends)} call(s)")
    return ends


def audit(tmp):
    from harness.audit_run_route import handle_audit_run
    body, status = handle_audit_run({"work_receipt": {"x": 1}, "artifact": "done",
                                     "endpoint": "ollama", "model": "stub-model"}, tmp / "run")
    return status


def evaluate(tmp, monkeypatch):
    from harness import eval_run_route
    monkeypatch.setattr(eval_run_route, "unified_roster", lambda: ROSTER, raising=False)
    _body, status = eval_run_route.handle_eval_run(
        {"endpoint": "ollama", "model": "stub-model", "n": 1}, tmp / "run")
    return status


def bench(tmp, upstream):
    from harness import verified_bench_route
    from harness.endpoints import OpenAICompatBackend

    def build_endpoints(providers=None, modes=None):
        return [OpenAICompatBackend(name="openai", base_url=f"{upstream.url}/v1",
                                    model="gpt-5.3-codex-spark", api_key="test-key")]
    (tmp / "run").mkdir(exist_ok=True)
    return verified_bench_route.handle_bench_run(
        {"tasks": [{"task_id": "t1", "prompt": "say hi", "gate_cmd": "python -c pass"}],
         "endpoints": ["openai"], "timeout_s": 20},
        run_root=tmp / "run", build_endpoints=build_endpoints)


def workflow(tmp):
    from harness.workflows import WORKFLOWS, run_workflow
    (tmp / "ws").mkdir(exist_ok=True)
    (tmp / "run").mkdir(exist_ok=True)
    return run_workflow(sorted(WORKFLOWS)[0], "say hi", "ollama", root=str(tmp / "ws"),
                        run_root=tmp / "run", authorized=True)


def router_agent(tmp):
    from harness.router_agent import run_router_agent
    (tmp / "ws").mkdir(exist_ok=True)
    return run_router_agent("say hi", "ollama", root=str(tmp / "ws"), max_steps=1)


def capability(tmp):
    from harness.frontier import capability_probe
    return capability_probe("ollama:stub-model")


def test_control_api_route_is_recorded(stubbed):
    upstream, home, _tmp = stubbed
    _body, status = gateway.route_request("Hi.", "ollama", "stub-model")
    assert status == 200
    end, = paired(upstream, home)
    assert end.kind == "endpoint_call" and end.meta["endpoint"] == "ollama"


def test_audit_run_records_its_narrator_call(stubbed):
    upstream, home, tmp = stubbed
    assert audit(tmp) == 200
    end, = paired(upstream, home)
    assert end.kind == "endpoint_call"


def test_eval_run_records_every_model_call(stubbed, monkeypatch):
    upstream, home, tmp = stubbed
    evaluate(tmp, monkeypatch)
    assert all(end.kind == "endpoint_call" for end in paired(upstream, home))


def test_bench_run_records_every_model_call(stubbed):
    upstream, home, tmp = stubbed
    bench(tmp, upstream)
    end, = paired(upstream, home)
    assert end.kind == "endpoint_call" and end.meta["endpoint"] == "openai"


def test_workflow_records_every_model_call(stubbed):
    upstream, home, tmp = stubbed
    workflow(tmp)
    assert len(paired(upstream, home)) >= 2


def test_the_router_agent_behind_plan_run_and_spawn_records_its_calls(stubbed):
    upstream, home, tmp = stubbed
    router_agent(tmp)
    assert paired(upstream, home)


def test_capability_probe_records_its_call(stubbed):
    upstream, home, tmp = stubbed
    doc = capability(tmp)
    assert "error" not in doc
    end, = paired(upstream, home)
    assert end.kind == "endpoint_call"


def test_the_legacy_spawn_body_records_the_calls_its_worker_process_makes(stubbed, monkeypatch):
    """The v1 spawn body runs each child as `python -m harness.subagent_worker`. The worker
    cannot write the gateway's ledger, so it sends each entry to the gateway, which appends
    and commits it before the worker's request leaves (gateway_ledger_relay)."""
    upstream, home, tmp = stubbed
    from harness.subagents_route import handle_subagents_get, handle_subagents_post
    monkeypatch.setenv("OPENAI_BASE_URL", f"{upstream.url}/v1")     # the worker inherits these
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-real-credential")
    (tmp / "run").mkdir(exist_ok=True)
    ack, status = handle_subagents_post(
        "/api/subagents/spawn", {"goal": "say hi", "endpoint": "openai-compatible",
                                 "model": "stub-model", "children": [{"role": "explore"}],
                                 "max_steps": 1, "timeout_s": 60}, run_root=tmp / "run")
    assert status == 200, ack
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        body, _code = handle_subagents_get("/api/subagents/swarm", "id=" + ack["swarm_id"],
                                           run_root=tmp / "run")
        if isinstance(body, dict) and body.get("status") == "sealed":
            break
        time.sleep(0.1)
    else:
        raise AssertionError(f"the swarm did not finish: {body}")
    ends = paired(upstream, home)
    assert all(end.meta["via"] == "subagent_worker" and end.meta["endpoint"] ==
               "openai-compatible" for end in ends)


ROUTES = {"audit": lambda tmp, up, mp: audit(tmp), "eval": lambda tmp, up, mp: evaluate(tmp, mp),
          "bench": lambda tmp, up, mp: bench(tmp, up), "workflow": lambda tmp, up, mp: workflow(tmp),
          "router agent": lambda tmp, up, mp: router_agent(tmp),
          "capability": lambda tmp, up, mp: capability(tmp)}


@pytest.mark.parametrize("name", sorted(ROUTES))
def test_with_the_ledger_unavailable_the_route_sends_nothing(stubbed, monkeypatch, name):
    upstream, home, tmp = stubbed
    from harness import gateway_reach
    gateway_reach.enforce(lambda: None)     # the state a second gateway on this home is in
    try:
        ROUTES[name](tmp, upstream, monkeypatch)
    except Exception:    # noqa: BLE001 - a refusal may be raised or answered; nothing was sent
        pass
    assert upstream.requests == [], f"{name} reached the provider with no ledger"
    assert entries(home) == []


@pytest.mark.parametrize("name", ["audit", "capability"])
def test_a_route_killed_while_the_provider_answers_leaves_an_unsettled_call(tmp_path, capsys,
                                                                            monkeypatch, name):
    home = tmp_path / "home"
    home.mkdir()
    done = subprocess.run([sys.executable, "-m", "tests.gateway_route_kill_child", name,
                           str(home), str(tmp_path)],
                          capture_output=True, text=True, timeout=120,
                          cwd=str(Path(__file__).resolve().parents[1]))
    assert done.returncode == 86, done.stdout + done.stderr     # the child's kill
    assert "requests 1" in done.stdout
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    entry, = entries(home)
    assert entry.kind == "endpoint_call_started" and entry.meta["endpoint"] == "ollama"
    capsys.readouterr()
    assert gateway_ledger_cli.main(["verify"]) == 3
    assert f"UNSETTLED call {entry.content}" in capsys.readouterr().out


def test_a_backend_reached_outside_an_account_is_refused_and_sends_nothing(stubbed):
    """The rule itself: in a gateway process a bare backend call does not leave."""
    upstream, home, _tmp = stubbed
    from harness import gateway_reach
    from harness.endpoints import OpenAICompatBackend
    backend = OpenAICompatBackend(name="openai", base_url=f"{upstream.url}/v1",
                                  model="gpt-5.3-codex-spark", api_key="test-key")
    with pytest.raises(gateway_reach.Unaccounted):
        backend.chat([{"role": "user", "content": "hi"}], system="", max_tokens=8,
                     temperature=0, seed=0)
    assert upstream.requests == [] and entries(home) == []


def test_control_outside_a_gateway_process_a_backend_call_is_sent(stubbed):
    upstream, home, _tmp = stubbed
    from harness.endpoints import OpenAICompatBackend
    _release()
    backend = OpenAICompatBackend(name="openai", base_url=f"{upstream.url}/v1",
                                  model="gpt-5.3-codex-spark", api_key="test-key")
    out = backend.chat([{"role": "user", "content": "hi"}], system="", max_tokens=8,
                       temperature=0, seed=0)
    assert out["text"] and len(upstream.requests) == 1 and entries(home) == []


def test_the_optional_judge_model_is_recorded_when_a_gateway_runs_it(stubbed):
    """The pre-action monitor's judge is a model call too. In a gateway process (a workflow
    run, for one) it leaves inside a ledger call; anywhere else it is sent as it is."""
    upstream, home, _tmp = stubbed
    from harness.preaction.judge import HttpJudge, JudgeConfig
    judge = HttpJudge(JudgeConfig(endpoint=f"{upstream.url}/v1", model="stub-model"))
    assert judge._post(b'{"model": "stub-model", "messages": []}')
    end, = paired(upstream, home)
    assert end.kind == "endpoint_call" and end.meta["endpoint"] == "preaction-judge"
    _release()
    assert judge._post(b'{"model": "stub-model", "messages": []}')
    assert len(upstream.requests) == 2 and len(entries(home)) == 2     # sent, not recorded
