"""parity_rows.py -- the claim table the parity audit runs against.

One row per capability. The Flywheel side of a row is a list of WITNESSES
that `parity.parity_matrix` checks against this repo every time it is read,
so a row whose witness disappears reports ABSENT and the matrix fails.

The competitor side is different in kind. Those cells are dated
DECLARATIONS read off public documentation and configuration, never
measurements taken here, and they carry no verdict weight. They exist so
the gap list can exist, and the gap list is the point.

Witness kinds:
    ("module", "harness/x.py")    the file is present
    ("route",  "/api/x")          the gateway dispatches on that path
    ("route",  "_handler_name")   the gateway defines that handler
    ("test",   "tests/test_x.py") the test file is present

Competitor cells are True (ships it), False (does not), or "partial", for
codex (the OpenAI Codex app), cursor, and claude-code.

The table lives apart from the audit because it is the part designed to
grow. `harness/parity.py` reads ROWS from here and does the checking.
"""
from __future__ import annotations

ROWS = [
    {"key": "any-provider-routing",
     "desc": "one request shape routed to any provider with failover chains",
     "witnesses": [("route", "/v1/chat/completions"), ("module", "harness/endpoint_registry.py")],
     "codex": False, "cursor": "partial", "claude-code": False},
    {"key": "receipt-on-every-answer",
     "desc": "re-checkable receipt attached to every routed answer",
     "witnesses": [("module", "harness/envelope.py")],
     "codex": False, "cursor": False, "claude-code": False},
    {"key": "integrity-guard",
     "desc": "reward-hacking guard: a tampered pass is flagged, never accepted",
     "witnesses": [("module", "harness/integrity.py")],
     "codex": False, "cursor": False, "claude-code": False},
    {"key": "verifier-ensembling",
     "desc": "consensus across oracles (all/any/majority/weighted)",
     "witnesses": [("module", "harness/consensus.py")],
     "codex": False, "cursor": False, "claude-code": False},
    {"key": "staged-workflows",
     "desc": "multi-step workflows with one chained receipt per run",
     "witnesses": [("module", "harness/workflows.py"), ("test", "tests/test_profiles_workflows.py")],
     "codex": False, "cursor": False, "claude-code": "partial"},
    {"key": "profile-manifests",
     "desc": "named operating profiles over one substrate, any endpoint",
     "witnesses": [("module", "harness/profiles.py"), ("route", "/api/profiles")],
     "codex": "partial", "cursor": "partial", "claude-code": "partial"},
    {"key": "plugin-registry",
     "desc": "lanes, builtin tools, and custom MCP servers in one registry",
     "witnesses": [("module", "harness/plugins.py"), ("route", "/api/plugins"),
                   ("test", "tests/test_plugins.py")],
     "codex": True, "cursor": "partial", "claude-code": True},
    {"key": "mcp-client-and-server",
     "desc": "consumes MCP servers (gated, witnessed) and serves itself as one",
     "witnesses": [("module", "harness/mcp_client.py"), ("module", "harness/local_mcp.py")],
     "codex": True, "cursor": True, "claude-code": True},
    {"key": "durable-memory-recall",
     "desc": "content-addressed memory with verbatim, provenance-carrying recall",
     "witnesses": [("module", "harness/memory_api.py"), ("route", "/api/memory"),
                   ("test", "tests/test_memory_api.py")],
     "codex": False, "cursor": "partial", "claude-code": "partial"},
    {"key": "context-compaction-receipt",
     "desc": "bounded context with a receipt for every fold, recallable later",
     "witnesses": [("module", "harness/compaction.py"), ("module", "harness/fold_index.py")],
     "codex": "partial", "cursor": "partial", "claude-code": "partial"},
    {"key": "workspace-sandbox",
     "desc": "agent runs scoped to a validated workspace root, refused by name",
     "witnesses": [("route", "_resolve_workspace_root"), ("test", "tests/test_workspace_root.py")],
     "codex": True, "cursor": True, "claude-code": True},
    {"key": "live-agent-stream",
     "desc": "every turn, tool call, and result streamed as it happens",
     # Was ("route", "_sse_agent"), a name that never existed. The capability
     # is real and lives on the operation route, which returns a streaming
     # response when the operation asks for one and serves an events feed per
     # run; the witness had simply been pointed at a dead branch in _post that
     # `_route_operation` intercepts before it can run.
     "witnesses": [("module", "harness/gateway_operation_route.py"),
                   ("test", "tests/test_gateway_operation_route.py")],
     "codex": True, "cursor": True, "claude-code": True},
    {"key": "projected-world-hash",
     "desc": "root-hashed projected state; tampering any receipt moves it",
     "witnesses": [("module", "harness/world.py")],
     "codex": False, "cursor": False, "claude-code": False},
    {"key": "loop-closure-audit",
     "desc": "falsifiable self-audit of the whole perceive-verify-memory loop",
     "witnesses": [("module", "harness/loop_closure.py")],
     "codex": False, "cursor": False, "claude-code": False},
    {"key": "adaptive-routing-scoreboard",
     "desc": "observed per-provider success, latency, circuit breakers",
     "witnesses": [("module", "harness/router_stats.py"), ("route", "/api/router/stats")],
     "codex": False, "cursor": False, "claude-code": False},
    # Rows the field shipped first. Each was an open gap when this matrix
    # was declared and each is witnessed now, which is why they stay here:
    # a matrix that deletes a row once it is won cannot show that it lost.
    {"key": "native-receipted-linter",
     "desc": "a built-in extensible linter whose findings are content-"
             "addressed and re-checkable, not deferred to external tools",
     "witnesses": [("module", "harness/linter.py"),
                   ("route", "/api/lint"),
                   ("test", "tests/test_linter.py")],
     "codex": False, "cursor": False, "claude-code": False},
    {"key": "lsp-go-to-definition",
     "desc": "editor go-to-definition over any user-named LSP server",
     "witnesses": [("module", "harness/lsp_bridge.py"),
                   ("route", "/api/lsp"),
                   ("test", "tests/test_lsp_bridge.py")],
     "codex": False, "cursor": True, "claude-code": False},
    {"key": "lsp-diagnostics-references",
     "desc": "diagnostics and find-references in the editor",
     "witnesses": [("module", "harness/lsp_diagnostics.py"),
                   ("test", "tests/test_lsp_diagnostics.py")],
     "codex": False, "cursor": True, "claude-code": False},
    {"key": "plugin-marketplace",
     "desc": "discoverable third-party plugin catalog with one-step install",
     "witnesses": [("module", "harness/marketplace.py"),
                   ("route", "/api/marketplace"),
                   ("test", "tests/test_marketplace.py")],
     "codex": True, "cursor": True, "claude-code": True},
    {"key": "secure-credentials",
     "desc": "provider secrets in the OS keychain (presence-only everywhere "
             "else) plus reuse of provider CLI logins; first-party account "
             "OAuth does not apply to a bring-your-own-provider tool",
     "witnesses": [("module", "harness/keychain.py"),
                   ("route", "/api/keychain"),
                   ("test", "tests/test_keychain.py")],
     "codex": True, "cursor": True, "claude-code": True},
    # Added 2026-09-03. The rows above were declared in July, and the engine
    # grew a boundary layer, a grant layer, and a measurement layer after
    # that. A matrix that stops at the July surface reports a smaller tool
    # than the one that ships, which is the same defect as overclaiming.
    {"key": "agent-boundary-audit",
     "desc": "read the trust model, the run bill of materials, and the "
             "classified egress of the process the agent is running in",
     "witnesses": [("module", "harness/infra/trust_model.py"),
                   ("module", "harness/infra/run_bom.py"),
                   ("module", "harness/infra/egress_matrix.py"),
                   ("route", "/api/infra/trust-model"),
                   ("test", "tests/test_infra_route.py")],
     "codex": False, "cursor": False, "claude-code": False},
    {"key": "isolation-probe",
     "desc": "actively test the boundaries the agent is claimed to run "
             "inside, and seal every boundary that was tried",
     "witnesses": [("module", "harness/infra/isolation_test.py"),
                   ("route", "/api/infra/isolation")],
     "codex": False, "cursor": False, "claude-code": False},
    {"key": "credential-exposure-scan",
     "desc": "find reachable secrets and report non-reversible fingerprints, "
             "never the values, in a sealed receipt",
     "witnesses": [("module", "harness/infra/credential_scanner.py"),
                   ("route", "/api/infra/credential-scan")],
     "codex": False, "cursor": False, "claude-code": False},
    {"key": "two-authority-kill-switch",
     "desc": "stop a running agent only under two different authorities, "
             "sealed whether it fires or refuses",
     "witnesses": [("module", "harness/infra/kill_switch.py"),
                   ("route", "/api/infra/kill")],
     "codex": False, "cursor": False, "claude-code": False},
    {"key": "per-action-operator-grant",
     "desc": "every mutating action prepares a named proposal (destination, "
             "tool, scopes) and needs a single-use grant before dispatch",
     # partial, not false: the field ships approval prompts. What it does not
     # ship is a proposal the operator can read before answering and a grant
     # reference that spends itself on one dispatch.
     "witnesses": [("module", "harness/gateway_operation.py"),
                   ("module", "harness/gateway_grant_route.py"),
                   ("route", "/api/gateway-grants/"),
                   ("test", "tests/test_gateway_operation_grants.py")],
     "codex": "partial", "cursor": "partial", "claude-code": "partial"},
    {"key": "signed-receipt-external-anchor",
     "desc": "receipts signed with a key you hold and anchored to a record "
             "outside this project, so the timestamp is not self-attested",
     "witnesses": [("module", "harness/receipt_signer.py"),
                   ("module", "harness/anchor.py"),
                   ("test", "tests/test_anchor.py")],
     "codex": False, "cursor": False, "claude-code": False},
    {"key": "formal-proof-oracle",
     "desc": "a proof assistant as a gate, reporting UNVERIFIABLE when it is "
             "absent instead of assuming the check passed",
     "witnesses": [("module", "harness/infra/lean_adapter.py"),
                   ("route", "/api/lean")],
     "codex": False, "cursor": False, "claude-code": False},
    {"key": "native-acceleration-with-fallback",
     "desc": "optional compiled kernels with a mathematically equivalent "
             "pure-Python path, so a result never depends on a built extension",
     "witnesses": [("module", "harness/infra/native_detect.py")],
     "codex": False, "cursor": False, "claude-code": False},
    {"key": "autonomy-tiers-and-decision-records",
     "desc": "what the agent may do is gated by a recorded autonomy tier, and "
             "the architecture decision behind that tier carries a receipt",
     "witnesses": [("module", "harness/governance/tadr_tier.py"),
                   ("module", "harness/governance/tadr_receipt.py"),
                   ("route", "/api/governance/tiers"),
                   ("test", "tests/test_governance_tadr.py")],
     "codex": False, "cursor": False, "claude-code": False},
    {"key": "accepted-lesson-loop",
     "desc": "a recorded failure becomes a lesson only after a person accepts "
             "it, and the lesson carries the hashes of its evidence",
     # partial: persistent instruction files exist in the field. An accept
     # gate with evidence hashes and a retirement path does not.
     "witnesses": [("module", "harness/lesson.py"),
                   ("route", "/api/lessons"),
                   ("test", "tests/test_lesson.py")],
     "codex": False, "cursor": "partial", "claude-code": "partial"},
    {"key": "private-verified-benchmarks",
     "desc": "run a private task set across every endpoint, dispose each "
             "attempt through a gate you own, and price verified quality",
     "witnesses": [("module", "harness/verified_bench.py"),
                   ("route", "/api/bench/run"),
                   ("test", "tests/test_verified_bench.py")],
     "codex": False, "cursor": False, "claude-code": False},
    {"key": "paired-uplift-measurement",
     "desc": "same task set, same provider, paired arms, and an interval that "
             "is allowed to include zero and say so",
     "witnesses": [("module", "harness/uplift_bench.py"),
                   ("route", "/api/uplift"),
                   ("test", "tests/test_uplift_bench.py")],
     "codex": False, "cursor": False, "claude-code": False},
    {"key": "phone-access-own-tunnel",
     "desc": "drive the same loop from a phone over a tunnel you run, with no "
             "vendor cloud between the phone and the engine",
     # The field reaches a phone through its own hosted service. Reaching it
     # without one is the difference, and the row is not unique either way.
     "witnesses": [("module", "docs/REMOTE-ACCESS.md"),
                   ("module", "desktop/lib/assistant/speech_voice.dart"),
                   ("module", "desktop/lib/assistant/url_device_sink.dart")],
     "codex": True, "cursor": False, "claude-code": True},
]
