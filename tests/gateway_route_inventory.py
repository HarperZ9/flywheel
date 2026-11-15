"""What every gateway route does about a model: the list tests/test_gateway_route_reach.py checks.

A route added to the gateway has to be added here with its class. The sweep
then exercises it over HTTP and holds it to that class.
"""
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
    "/api/agent": (TRACE, "tests/test_gateway_agent_contact_invariant.py"),
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
