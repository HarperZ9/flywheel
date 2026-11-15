"""Every gateway route is exercised over HTTP: no model request leaves without its account.

Sixth review round of 2.0.0, finding S1 of the fourth independent review.
Two rounds were built around "no contact without accounting" and seven
routes still reached a provider with no ledger entry. The check that stood in
for "every route" read the source for the names of network calls
(tests/test_gateway_provider_reach_inventory.py). It could say which modules
open a connection. It could not say which route reaches which module, and it
left 24 of its 32 rows "not examined".

This file checks by behaviour. The route list is the gateway's own
(`harness.route_inventory.gateway_routes`, the list `/openapi.json` is built
from). Every route is on INVENTORY below with what it does about a model, and
every method of every route is sent over HTTP to a real gateway
(tests/gateway_route_sweep_support.py) whose roster endpoints all point at a
stub that counts requests, with the reach rule on as `gateway.main` turns it
on. After each request the test reads the stub's count, the ledger files, the
refusals of the reach rule and the outside addresses tried.

It fails when
  - a route exists that is not on INVENTORY (a new route has to be written
    down here with its class);
  - any route sends a model request and the ledger did not gain a started
    entry for it first, or a call it started has no end entry;
  - any route tries to send a model request with no account (the reach rule
    refused it: harness.gateway_reach);
  - a route marked as running no model at a provider reaches the provider
    stub, or a route marked MODEL does not;
  - any route but the ones marked for it tries an address outside this
    machine.

What a sweep can and cannot show. A route does what its request body lets it
do. The routes that are known to run a model get a body that makes them run
it, and the test asserts they did. Every other route gets one broad body
(SINK). A route that would reach a provider only for a body this file does
not send is not shown here to do so. For that case the rule does not rest on
this file: the transports themselves refuse a model request that has no
account (tests/test_gateway_route_accounting.py), so such a route answers an
error and sends nothing. The two planted controls at the end add a route that
calls a provider directly and show both halves: with the reach rule on the
request is refused and the sweep reports it; with it off the request arrives
and the sweep reports a model request with no entry.

Not in the release gate: it starts child processes and takes minutes.
"""
import json
import os
import time

import pytest

from harness.route_inventory import gateway_routes
from tests import gateway_route_sweep_support as sweep

from tests.gateway_route_inventory import (INVENTORY, LANE, LOCAL, META, MODEL, NONE,  # noqa: E402
                                           OUTSIDE, TRACE, bodies, sink)

# The sweep sends about 220 requests in the module fixture, a minute or more in all, and a
# few routes take ten seconds each (a loop audit, a feed read). The suite's 60 s limit is
# per test and the fixture runs inside the first one.
pytestmark = pytest.mark.timeout(900)
def run_sweep(world) -> list:
    special, broad, results = bodies(world), sink(world), []
    for route in gateway_routes():
        for method in route.methods:
            chosen = special.get((method, route.path))
            if chosen is not None:
                path, body, settle = chosen
                if callable(body):      # bound to the journey's head at this moment
                    body = body()
                    assert body is not None, f"the grant flow refused the body for {route.path}"
            else:
                path = route.path + ("sweep-probe" if route.match == "prefix" else "")
                body, settle = (broad if method in ("POST", "PUT") else None), None
            began = time.monotonic()
            result = world.exercise(method, path, body, settle)
            result.update(route=route.path, seconds=round(time.monotonic() - began, 2),
                          own_body=chosen is not None)
            results.append(result)
    return results


@pytest.fixture(scope="module")
def swept(tmp_path_factory):
    """(world, results): the whole sweep, run once."""
    from harness import keychain
    patch = pytest.MonkeyPatch()
    patch.setattr(keychain, "keychain_get", lambda *args, **kwargs: None)
    for name in ("keychain_set", "keychain_delete"):
        patch.setattr(keychain, name, lambda *args, **kwargs: {
            "error": "the route sweep has no credential store"})
    world = sweep.World(tmp_path_factory.mktemp("route-sweep"), patch)
    try:
        results = run_sweep(world)
        out = os.environ.get("FLYWHEEL_ROUTE_SWEEP_OUT")
        if out:
            with open(out, "w", encoding="utf-8") as handle:
                json.dump([{**row, "class": INVENTORY.get(row["route"], ("?",))[0]}
                           for row in results], handle, indent=1)
        yield world, results
    finally:
        world.close()
        patch.undo()


def test_every_route_of_the_gateway_is_on_the_list():
    routes = {route.path for route in gateway_routes()}
    unlisted = sorted(routes - set(INVENTORY))
    assert not unlisted, (
        f"{unlisted} are gateway routes and are not in INVENTORY. Add each with what it does "
        "about a model; the sweep then exercises it.")
    stale = sorted(set(INVENTORY) - routes)
    assert not stale, f"{stale} are in INVENTORY and are no longer gateway routes"
    assert len(routes) >= 180           # the list is the gateway's whole surface, not a sample


def test_no_route_sends_a_model_request_without_its_account(swept):
    _world, results = swept
    wrong = [text for row in results if INVENTORY[row["route"]][0] != TRACE
             for text in sweep.faults(row)]
    assert not wrong, "\n".join(wrong)


def test_the_whole_ledger_of_the_sweep_holds_one_start_and_one_end_per_call(swept):
    world, results = swept
    from tests import gateway_messages_support as support
    ends = support.recorded(world.entries())
    calls = [entry for entry in ends if entry.kind in ("endpoint_call", "endpoint_call_failed")]
    sent = sum(len(row["provider_model"]) for row in results
               if INVENTORY[row["route"]][0] != TRACE)
    assert sent >= 12 and len(calls) >= sent, (sent, len(calls))


def test_every_model_route_reached_the_provider_and_recorded_each_call(swept):
    _world, results = swept
    for path, (kind, how) in INVENTORY.items():
        if kind != MODEL or "is not sent here" in how:
            continue
        rows = [row for row in results if row["route"] == path and row["method"] == "POST"]
        assert rows and all(row["own_body"] for row in rows), path
        for row in rows:
            assert row["status"] == 200, (path, row["status"])
            assert len(row["provider_model"]) >= 1, f"{path} did not reach the provider stub"
            assert len(row["started"]) == len(row["provider_model"]) == len(row["ended"]), row


def test_each_entry_of_the_sweep_names_the_endpoint_and_the_route_that_made_the_call(swept):
    world, _results = swept
    named = {(entry.meta.get("route") or entry.meta.get("interface"), entry.meta["endpoint"])
             for entry in world.entries() if entry.kind == "endpoint_call"}
    assert {("/api/route", "ollama"), ("/v1/chat/completions", "ollama"),
            ("openai-embeddings", "openai"), ("/api/capability", "ollama"),
            ("/api/bench/run", "openai"), ("/api/eval/run", "ollama"),
            ("/api/audit/run", "ollama"), ("/api/workflow", "ollama"),
            ("anthropic-messages", "openai"), ("openai-responses", "openai")} <= named, named


def test_an_agent_run_writes_a_started_record_to_its_trace_for_each_request(swept, capsys):
    """/api/agent over HTTP, through the grant flow. Its model request is not in the gateway
    ledger: the run's own private trace holds a started record for it.

    The run is an operation in a worker process. Where that process can run (the reference
    machine) one request reaches the stub and the trace holds its started record. On the CI
    runners the operation ends before any contact (502), so nothing is sent there and the
    order is held by tests/test_gateway_agent_contact_invariant.py with a stub transport.
    Either way the grant step was passed and no request left without a started record."""
    _world, results = swept
    row, = [r for r in results if r["route"] == "/api/agent" and r["method"] == "POST"]
    with capsys.disabled():
        print(f"\n  /api/agent over HTTP: status {row['status']}, {len(row['provider_model'])} "
              f"model request(s), {row['trace_started']} started trace record(s); "
              f"answer {row['answer'][:160]}", end="")
    assert row["own_body"] and row["status"] not in (401, 403, 422), row
    assert row["started"] == [] and row["trace_started"] >= len(row["provider_model"]), row


def test_a_route_that_runs_no_model_at_a_provider_sends_it_no_model_request(swept):
    _world, results = swept
    for row in results:
        kind = INVENTORY[row["route"]][0]
        if kind in (NONE, LOCAL, LANE, OUTSIDE, META) or (kind == TRACE and not row["own_body"]):
            assert row["provider_model"] == [], (row["method"], row["path"], kind)
        if kind in (NONE, LANE, OUTSIDE):
            assert row["provider_other"] == [], (row["method"], row["path"], kind)
        if kind not in (LOCAL, META):
            assert row["local"] == [] or kind == NONE and row["route"] in LOCAL_READS, (
                row["method"], row["path"], kind, row["local"])


# Routes that run no model and read the local model server's health or roster.
LOCAL_READS = {"/api/world", "/api/desktop/status", "/api/training/status", "/api/readiness",
               "/api/lanes", "/api/parity"}


def test_only_the_marked_routes_try_an_address_outside_this_machine(swept):
    _world, results = swept
    tried = {(row["method"], row["path"]): row["outside"] for row in results if row["outside"]
             and INVENTORY[row["route"]][0] not in (META, OUTSIDE, LANE)}
    assert not tried, tried


def test_the_sweep_sent_every_method_of_every_route(swept):
    _world, results = swept
    assert len(results) == sum(len(route.methods) for route in gateway_routes())
    answered = [row for row in results if row["status"] > 0]
    assert len(answered) >= len(results) - 3, [
        (row["method"], row["path"]) for row in results if row["status"] <= 0]


def _planted(world, enforced: bool) -> dict:
    """Add a route that calls a provider directly, as a route written tomorrow might."""
    from harness import gateway_reach
    from harness.endpoints import OpenAICompatBackend
    real = world.handler._get

    def get(handler):
        if handler.path.split("?", 1)[0] == "/api/planted":
            backend = OpenAICompatBackend(name="openai", base_url=f"{world.provider.url}/v1",
                                          model="stub-model", api_key="sk-sweep-not-a-real-key")
            out = backend.chat(sweep_message(), system="", max_tokens=8, temperature=0, seed=0)
            return handler._json({"text": out["text"]})
        return real(handler)
    from harness import gateway
    world.handler._get = get
    gateway_reach.release()             # each test starts with the rule off (tests/conftest.py)
    if enforced:
        gateway_reach.enforce(gateway._router_ledger)
    try:
        return world.exercise("GET", "/api/planted")
    finally:
        world.handler._get = real
        gateway_reach.release()


def sweep_message() -> list:
    return [{"role": "user", "content": "hi"}]


def test_control_a_new_route_that_calls_a_provider_directly_is_refused_and_reported(swept):
    world, _results = swept
    result = _planted(world, enforced=True)
    assert result["provider_model"] == [] and result["status"] == 500
    found = sweep.faults(result)
    assert found and "the reach rule refused a model request" in found[0]


def test_control_with_the_reach_rule_off_the_same_route_sends_a_request_with_no_entry(swept):
    world, _results = swept
    result = _planted(world, enforced=False)
    assert len(result["provider_model"]) == 1 and result["started"] == []
    found = sweep.faults(result)
    assert found and "model request(s) reached the provider" in found[0]
