"""What every gateway route does about a model: the list tests/test_gateway_route_reach.py checks.

A route added to the gateway has to be added here with its class. The sweep
then exercises it over HTTP and holds it to that class. `bodies` and `sink`
are what the sweep sends.
"""
import time

MODEL = "runs a model at a roster endpoint; every call is in the gateway ledger (start, then end)"
TRACE = ("a gateway operation in a child process; a model call there is recorded in the run's "
         "own trace (a started record, then a closing one), not in this ledger")
LOCAL = "the model server on this machine (--serve-url); no provider account; outside the ledger"
META = "asks a provider for a list, a probe or a token count; runs no model; no ledger entry"
LANE = "calls a separate program (a lane, a plugin, a client); what that program contacts is its own"
OUTSIDE = "contacts a named service that is not a model provider"
NONE = "runs no model and contacts no provider"

# route path -> (class, how it is tested beyond this sweep, or "")
SPECIAL = {
    "/api/eval/run": (MODEL, "tests/test_gateway_route_accounting.py"),
    "/api/audit/run": (MODEL, "tests/test_gateway_route_accounting.py"),
    "/api/bench/run": (MODEL, "tests/test_gateway_route_accounting.py"),
    "/api/workflow": (MODEL, "tests/test_gateway_route_accounting.py"),
    "/api/plan/": (MODEL, "tests/test_gateway_route_accounting.py (run_workflow); the HTTP body "
                   "needs a sealed plan binding and is not sent here"),
    "/api/capability": (MODEL, "tests/test_gateway_route_accounting.py"),
    "/api/subagents/": (MODEL, "tests/test_gateway_route_accounting.py (the v1 body's worker "
                        "process records through gateway_ledger_relay)"),
    "/v1/chat/completions": (MODEL, "tests/test_gateway_chat_route_accounting.py"),
    "/api/route": (MODEL, "tests/test_gateway_chat_route_accounting.py"),
    "/v1/embeddings": (MODEL, "tests/test_gateway_chat_route_accounting.py"),
    "/v1/messages": (MODEL, "tests/test_gateway_contact_invariant.py"),
    "/v1/responses": (MODEL, "tests/test_gateway_contact_invariant.py"),
    "/api/agent": (TRACE, "tests/test_gateway_agent_contact_invariant.py; the sweep sends "
                   "one granted run and reads its trace"),
    "/api/operations/": (TRACE, "reads or cancels an operation"),
    "/api/provider-sessions/": (TRACE, "native provider sessions, bound per operation"),
    "/api/output/check": (TRACE, "a governed check; no model"),
    "/generate": (LOCAL, ""), "/health": (LOCAL, ""), "/v1/": (LOCAL, ""),
    "/api/companion": (LOCAL, "the seat answers from the local model; escalation is only named"),
    "/api/models": (META, "tests/test_gateway_no_redirect.py (the key follows no redirect)"),
    "/api/endpoints/health": (META, ""), "/api/endpoints": (META, ""),
    "/v1/models": (META, ""),
    "/v1/messages/count_tokens": (META, "tests/test_gateway_unbilled_and_chat_contacts.py"),
    "/api/lane/": (LANE, ""), "/api/lanes/": (LANE, ""), "/api/agent/mcp/": (LANE, ""),
    "/api/discourse": (LANE, ""), "/api/discourse/corpora": (LANE, ""),
    "/api/discourse/digests": (LANE, ""), "/api/forum/gates": (LANE, ""),
    "/api/forum/ledger": (LANE, ""), "/api/forum/run-room": (LANE, ""),
    "/api/forum/status": (LANE, ""), "/api/relay/remote": (LANE, ""),
    "/api/relay/result": (LANE, ""), "/api/relay/runs": (LANE, ""),
    "/api/relay/sessions": (LANE, ""), "/api/relay/start": (LANE, ""),
    "/api/relay/status": (LANE, ""), "/api/feeds": (LANE, ""), "/api/plugins/probe": (LANE, ""),
    "/api/telos/kernel": (LANE, ""), "/api/telos/raster": (LANE, ""), "/api/codex/": (LANE, ""),
    "/api/live-screen/": (LANE, ""),
}
REST = """
/.well-known/flywheel.json /api/academy /api/academy/complete /api/agent/run /api/agent/runs
/api/attest /api/audit/verify /api/auth /api/auth/cancel /api/auth/login /api/auth/logout
/api/auth/token /api/browser /api/browser/ /api/bulletin-identity /api/bulletin-identity/create
/api/bulletin-identity/register /api/comprehension /api/context-memory/ /api/continuation/
/api/continuation/preview /api/credential-handles /api/credential-handles/ /api/credo
/api/desktop/status /api/enterprise-envs/service-desk-incident/review /api/eval/verify
/api/evidence/ /api/explain /api/forge /api/forge/recheck /api/frontier /api/gateway-grants/
/api/governance/classify /api/governance/compliance /api/governance/tiers /api/grants/
/api/graph /api/hooks /api/hooks/ /api/import /api/import/inspect /api/import/inspect/
/api/incident-sim/process-audit/review /api/index /api/index/summary /api/index/workspace-map/
/api/infra/bom /api/infra/credential-scan /api/infra/egress /api/infra/isolation /api/infra/kill
/api/infra/trust-model /api/instruments /api/invent /api/journeys/ /api/journeys/extensions/
/api/keychain /api/keychain/delete /api/keychain/set /api/lanes /api/lean /api/learn/animate
/api/lessons /api/lessons/admit /api/lessons/patterns /api/lessons/retire /api/lint /api/loops
/api/lsp /api/marketplace /api/memory /api/memory/list /api/memory/note /api/memory/recall
/api/operations /api/packs /api/packs/admit /api/parity /api/peer-sessions /api/plugins
/api/pm/roadmap /api/profiles /api/projects /api/projects/add /api/projects/remove
/api/readiness /api/receipts /api/receipts/proof /api/retention /api/retrieve
/api/robustness/inject /api/router/stats /api/runners /api/runners/ /api/scaffold
/api/scan/vulnerabilities /api/schedule /api/schedule/ /api/science /api/science/run
/api/science/runs /api/session-tokens /api/session-tokens/ /api/settings/node_path /api/skills
/api/skills/ /api/snapshot /api/source-context/ /api/store /api/store/audit /api/store/entity
/api/store/query /api/store/verify /api/studio/body/ /api/studio/brandkit /api/studio/graph
/api/studio/pipeline /api/studio/poster /api/studio/sound /api/subagents /api/suite /api/tension
/api/traces/ /api/train/duel /api/train/loop /api/training/status /api/typeface
/api/typeface/face /api/typeface/family /api/typeface/gallery /api/typeface/publish
/api/typeface/variable /api/uplift /api/usage /api/usage/live /api/usage/verify
/api/workflow/run /api/workflows /api/world /api/writing/ /llms.txt /openapi.json
""".split()
INVENTORY = {**{path: (NONE, "") for path in REST}, **SPECIAL}
INVENTORY["/api/bulletin-identity/register"] = (OUTSIDE, "the Bulletin origin")

MESSAGE = [{"role": "user", "content": "Say hi."}]
TASKS = [{"task_id": "t1", "prompt": "say hi", "gate_cmd": "python -c pass"}]


def _sealed(world, answer):
    """Wait for a v1 swarm to seal: its worker processes have ended."""
    swarm = (answer or {}).get("swarm_id")
    deadline = time.monotonic() + 120
    while swarm and time.monotonic() < deadline:
        status, body = world.request("GET", f"/api/subagents/swarm?id={swarm}")
        if status != 200 or body.get("status") == "sealed":
            return
        time.sleep(0.2)


def bodies(world) -> dict:
    """(method, path) -> (path to send, body, settle) for the routes with a body of their own.

    A body made by `world.granted` goes through the per-operation grant flow over HTTP
    (prepare, approve once) just before it is sent."""
    from harness.workflows import WORKFLOWS
    first = sorted(WORKFLOWS)[0]
    plain = {
        "/api/eval/run": {"endpoint": "ollama", "model": "stub-model", "n": 1},
        "/api/audit/run": {"work_receipt": {"x": 1}, "artifact": "done", "endpoint": "ollama",
                           "model": "stub-model"},
        "/v1/messages": {"model": "claude-sonnet-5", "max_tokens": 64, "messages": MESSAGE},
        "/v1/responses": {"model": "gpt-5.3-codex", "input": "Say hi."},
        "/v1/messages/count_tokens": {"model": "claude-sonnet-5", "messages": MESSAGE},
    }
    behind = {
        "/v1/chat/completions": ("chat.complete", {
            "model": "ollama:stub-model", "messages": MESSAGE, "stream": False}),
        "/api/route": ("route.send", {"prompt": "Say hi.", "endpoint": "ollama",
                                      "model": "stub-model"}),
        "/v1/embeddings": ("embeddings.create", {
            "input": "hi", "model": "openai:text-embedding-3-small"}),
        "/api/workflow": ("workflow.run", {"workflow": first, "goal": "say hi",
                                           "endpoint": "ollama", "allow_write": False,
                                           "allow_exec": False}),
        "/api/bench/run": ("bench.run", {"tasks": TASKS, "endpoints": ["openai"],
                                         "timeout_s": 20}),
        "/api/capability": ("capability.probe", {"endpoint": "ollama:stub-model"}),
        "/api/companion": ("companion.ask", {"prompt": "Say hi."}),
        "/api/agent": ("agent.run", {"goal": "say hi", "endpoint": "ollama", "max_steps": 1,
                                     "allow_write": False, "allow_exec": False,
                                     "stream": False}),
        "/api/forge": ("forge.create", {"goal": "add two numbers"}),
        "/api/invent": ("invent.round", {"k": 1}),
        "/api/lean": ("lean.check", {"code": "theorem t : True := trivial"}),
        "/api/store/entity": ("store.put", {"kind": "note", "data": {"text": "hi"}}),
        "/api/import": ("import.config", {"root": str(world.root)}),
        "/api/suite": ("suite.audit", {"path": str(world.root)}),
    }
    out = {("POST", path): (path, body, None) for path, body in plain.items()}
    for path, (action, operation) in behind.items():    # granted when sent: bound to the head
        out[("POST", path)] = (path, lambda a=action, o=operation: world.granted(a, o), None)
    out[("GET", "/api/models")] = ("/api/models?endpoint=openai", None, None)
    out[("POST", "/api/subagents/")] = ("/api/subagents/spawn", {
        "goal": "say hi", "endpoint": "openai-compatible", "model": "stub-model",
        "children": [{"role": "explore"}], "max_steps": 1, "timeout_s": 60}, _sealed)
    return out


def sink(world) -> dict:
    """One broad body for every other POST: the fields most handlers read."""
    return {"prompt": "Say hi.", "goal": "say hi", "endpoint": "ollama", "model": "stub-model",
            "text": "hi", "input": "hi", "messages": MESSAGE, "query": "hi", "q": "hi",
            "task": "hi", "question": "hi", "claim": "hi", "topic": "hi", "code": "x = 1",
            "name": "sweep-probe", "id": "sweep-probe", "root": str(world.root),
            "path": str(world.root), "n": 1, "k": 1, "max_tokens": 16, "max_steps": 1,
            "tasks": TASKS, "endpoints": ["openai"], "workflow": "sweep-probe"}
