"""parity_rows.py -- the claim table the parity audit runs against.

One row per capability, and one kind of claim: a list of WITNESSES that
`parity.parity_matrix` checks against this repo every time it is read, so a
row whose witness disappears reports ABSENT and the matrix fails.

What other products declare lives in `harness/parity_peers.py`, keyed by the
row key here. A declaration is a dated reading of somebody's documentation
and a witness is a check that runs, so they are stored apart and a reader
cannot mistake one for the other. Every row here needs a column there, and
`tests/test_parity.py` fails a row that has none.


Witness kinds:
    ("module", "harness/x.py")    the file is present
    ("route",  "/api/x")          the gateway dispatches on that path
    ("route",  "_handler_name")   the gateway defines that handler
    ("test",   "tests/test_x.py") the test file is present

The table lives apart from the audit because it is the part designed to
grow. `harness/parity.py` reads ROWS from here and does the checking.
"""
from __future__ import annotations

ROWS = [
    {"key": "any-provider-routing",
     "desc": "one request shape routed to any provider with failover chains",
     "witnesses": [("route", "/v1/chat/completions"), ("module", "harness/endpoint_registry.py")]},
    {"key": "receipt-on-every-answer",
     "desc": "re-checkable receipt attached to every routed answer",
     "witnesses": [("module", "harness/envelope.py")]},
    {"key": "integrity-guard",
     "desc": "reward-hacking guard: a tampered pass is flagged, never accepted",
     "witnesses": [("module", "harness/integrity.py")]},
    {"key": "verifier-ensembling",
     "desc": "consensus across oracles (all/any/majority/weighted)",
     "witnesses": [("module", "harness/consensus.py")]},
    {"key": "staged-workflows",
     "desc": "multi-step workflows with one chained receipt per run",
     "witnesses": [("module", "harness/workflows.py"), ("test", "tests/test_profiles_workflows.py")]},
    {"key": "profile-manifests",
     "desc": "named operating profiles over one substrate, any endpoint",
     "witnesses": [("module", "harness/profiles.py"), ("route", "/api/profiles")]},
    {"key": "plugin-registry",
     "desc": "lanes, builtin tools, and custom MCP servers in one registry",
     "witnesses": [("module", "harness/plugins.py"), ("route", "/api/plugins"),
                   ("test", "tests/test_plugins.py")]},
    {"key": "mcp-client-and-server",
     "desc": "consumes MCP servers (gated, witnessed) and serves itself as one",
     "witnesses": [("module", "harness/mcp_client.py"), ("module", "harness/local_mcp.py")]},
    {"key": "durable-memory-recall",
     "desc": "content-addressed memory with verbatim, provenance-carrying recall",
     "witnesses": [("module", "harness/memory_api.py"), ("route", "/api/memory"),
                   ("test", "tests/test_memory_api.py")]},
    {"key": "context-compaction-receipt",
     "desc": "bounded context with a receipt for every fold, recallable later",
     "witnesses": [("module", "harness/compaction.py"), ("module", "harness/fold_index.py")]},
    {"key": "workspace-sandbox",
     "desc": "agent runs scoped to a validated workspace root, refused by name",
     "witnesses": [("route", "_resolve_workspace_root"), ("test", "tests/test_workspace_root.py")]},
    {"key": "live-agent-stream",
     "desc": "every turn, tool call, and result streamed as it happens",
     # Was ("route", "_sse_agent"), a name that never existed. The capability
     # is real and lives on the operation route, which returns a streaming
     # response when the operation asks for one and serves an events feed per
     # run; the witness had simply been pointed at a dead branch in _post that
     # `_route_operation` intercepts before it can run.
     "witnesses": [("module", "harness/gateway_operation_route.py"),
                   ("test", "tests/test_gateway_operation_route.py")]},
    {"key": "projected-world-hash",
     "desc": "root-hashed projected state; tampering any receipt moves it",
     "witnesses": [("module", "harness/world.py")]},
    {"key": "loop-closure-audit",
     "desc": "falsifiable self-audit of the whole perceive-verify-memory loop",
     "witnesses": [("module", "harness/loop_closure.py")]},
    {"key": "adaptive-routing-scoreboard",
     "desc": "observed per-provider success, latency, circuit breakers",
     "witnesses": [("module", "harness/router_stats.py"), ("route", "/api/router/stats")]},
    # Rows the field shipped first. Each was an open gap when this matrix
    # was declared and each is witnessed now, which is why they stay here:
    # a matrix that deletes a row once it is won cannot show that it lost.
    {"key": "native-receipted-linter",
     "desc": "a built-in extensible linter whose findings are content-"
             "addressed and re-checkable, not deferred to external tools",
     "witnesses": [("module", "harness/linter.py"),
                   ("route", "/api/lint"),
                   ("test", "tests/test_linter.py")]},
    {"key": "lsp-go-to-definition",
     "desc": "editor go-to-definition over any user-named LSP server",
     "witnesses": [("module", "harness/lsp_bridge.py"),
                   ("route", "/api/lsp"),
                   ("test", "tests/test_lsp_bridge.py")]},
    {"key": "lsp-diagnostics-references",
     "desc": "diagnostics and find-references in the editor",
     "witnesses": [("module", "harness/lsp_diagnostics.py"),
                   ("test", "tests/test_lsp_diagnostics.py")]},
    {"key": "lsp-run-record",
     "desc": "a language server client that keeps a re-checkable record of "
             "the exchange: every frame chained, every answer stamped with "
             "the document version and negotiated encoding it was asked at, "
             "and a verify command that re-derives the chain",
     "witnesses": [("module", "harness/lsp_client.py"),
                   ("module", "harness/lsp_witness.py"),
                   ("test", "tests/test_lsp_witness.py"),
                   ("test", "tests/test_lsp_cli.py")]},
    {"key": "dap-debug-session",
     "desc": "drive any Debug Adapter Protocol adapter: set breakpoints, run "
             "to a stop, and read the stack and the variables at it",
     "witnesses": [("module", "harness/dap_client.py"),
                   ("module", "harness/dap_session.py"),
                   ("test", "tests/test_dap_client.py")]},
    {"key": "dap-run-record",
     "desc": "a debug adapter client under a default-deny grant boundary on "
             "the two reverse requests, keeping a re-checkable record of every "
             "frame in both directions, each stop in the order it happened, "
             "and every request the client refused, with a verify command that "
             "re-derives the chain offline",
     "witnesses": [("module", "harness/dap_policy.py"),
                   ("module", "harness/dap_witness.py"),
                   ("test", "tests/test_dap_policy.py"),
                   ("test", "tests/test_dap_witness.py"),
                   ("test", "tests/test_dap_session.py"),
                   ("test", "tests/test_dap_cli.py")]},
    {"key": "acp-delegation-receipt",
     "desc": "delegate a turn to any Agent Client Protocol agent as the "
             "client half of the protocol, under a default-deny permission "
             "boundary, and keep a re-checkable wire record of the turn that "
             "includes every request the client refused",
     "witnesses": [("module", "harness/acp_client.py"),
                   ("module", "harness/acp_policy.py"),
                   ("module", "harness/acp_witness.py"),
                   ("test", "tests/test_acp_policy.py"),
                   ("test", "tests/test_acp_witness.py")]},
    {"key": "plugin-marketplace",
     "desc": "discoverable third-party plugin catalog with one-step install",
     "witnesses": [("module", "harness/marketplace.py"),
                   ("route", "/api/marketplace"),
                   ("test", "tests/test_marketplace.py")]},
    {"key": "secure-credentials",
     "desc": "provider secrets in the OS keychain (presence-only everywhere "
             "else) plus reuse of provider CLI logins; first-party account "
             "OAuth does not apply to a bring-your-own-provider tool",
     "witnesses": [("module", "harness/keychain.py"),
                   ("route", "/api/keychain"),
                   ("test", "tests/test_keychain.py")]},
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
                   ("test", "tests/test_infra_route.py")]},
    {"key": "task-isolation",
     "desc": "give a task a disposable copy of the workspace by the cheapest "
             "mechanism the filesystem offers, and record which one ran, what "
             "the others refused, and what the copy cost",
     "witnesses": [("module", "harness/workspace_clone.py"),
                   ("test", "tests/test_workspace_clone.py")]},
    {"key": "posix-os-confinement",
     "desc": "run a shell command under an OS-enforced sandbox on Linux and "
             "macOS rather than only on Windows, and record which backend ran "
             "and which guarantees it enforced, including the ones it did not",
     "witnesses": [("module", "harness/posix_sandbox.py"),
                   ("module", "harness/sandboxed_runner.py"),
                   ("test", "tests/test_posix_sandbox.py"),
                   # The builder file next door asserts what the argv and the
                   # profile say. This one runs them, so it is the witness
                   # that the claim was tested and not only written down.
                   ("test", "tests/test_posix_sandbox_entry.py")]},
    {"key": "isolation-probe",
     "desc": "actively test the boundaries the agent is claimed to run "
             "inside, and seal every boundary that was tried",
     "witnesses": [("module", "harness/infra/isolation_test.py"),
                   ("route", "/api/infra/isolation")]},
    {"key": "credential-exposure-scan",
     "desc": "find reachable secrets and report non-reversible fingerprints, "
             "never the values, in a sealed receipt",
     "witnesses": [("module", "harness/infra/credential_scanner.py"),
                   ("route", "/api/infra/credential-scan")]},
    {"key": "two-authority-kill-switch",
     "desc": "stop a running agent only under two different authorities, "
             "sealed whether it fires or refuses",
     "witnesses": [("module", "harness/infra/kill_switch.py"),
                   ("route", "/api/infra/kill")]},
    {"key": "per-action-operator-grant",
     "desc": "every mutating action prepares a named proposal (destination, "
             "tool, scopes) and needs a single-use grant before dispatch",
     "witnesses": [("module", "harness/gateway_operation.py"),
                   ("module", "harness/gateway_grant_route.py"),
                   ("route", "/api/gateway-grants/"),
                   ("test", "tests/test_gateway_operation_grants.py")]},
    {"key": "signed-receipt-external-anchor",
     "desc": "receipts signed with a key you hold and anchored to a record "
             "outside this project, so the timestamp is not self-attested",
     "witnesses": [("module", "harness/receipt_signer.py"),
                   ("module", "harness/anchor.py"),
                   ("test", "tests/test_anchor.py")]},
    {"key": "formal-proof-oracle",
     "desc": "a proof assistant as a gate, reporting UNVERIFIABLE when it is "
             "absent instead of assuming the check passed",
     "witnesses": [("module", "harness/infra/lean_adapter.py"),
                   ("route", "/api/lean")]},
    {"key": "native-acceleration-with-fallback",
     "desc": "optional compiled kernels with a mathematically equivalent "
             "pure-Python path, so a result never depends on a built extension",
     "witnesses": [("module", "harness/infra/native_detect.py")]},
    {"key": "autonomy-tiers-and-decision-records",
     "desc": "what the agent may do is gated by a recorded autonomy tier, and "
             "the architecture decision behind that tier carries a receipt",
     "witnesses": [("module", "harness/governance/tadr_tier.py"),
                   ("module", "harness/governance/tadr_receipt.py"),
                   ("route", "/api/governance/tiers"),
                   ("test", "tests/test_governance_tadr.py")]},
    {"key": "accepted-lesson-loop",
     "desc": "a recorded failure becomes a lesson only after a person accepts "
             "it, and the lesson carries the hashes of its evidence",
     "witnesses": [("module", "harness/lesson.py"),
                   ("route", "/api/lessons"),
                   ("test", "tests/test_lesson.py")]},
    {"key": "private-verified-benchmarks",
     "desc": "run a private task set across every endpoint, dispose each "
             "attempt through a gate you own, and price verified quality",
     "witnesses": [("module", "harness/verified_bench.py"),
                   ("route", "/api/bench/run"),
                   ("test", "tests/test_verified_bench.py")]},
    {"key": "paired-uplift-measurement",
     "desc": "same task set, same provider, paired arms, and an interval that "
             "is allowed to include zero and say so",
     "witnesses": [("module", "harness/uplift_bench.py"),
                   ("route", "/api/uplift"),
                   ("test", "tests/test_uplift_bench.py")]},
    {"key": "phone-access-own-tunnel",
     "desc": "drive the same loop from a phone over a tunnel you run, with no "
             "vendor cloud between the phone and the engine",
     "witnesses": [("module", "docs/REMOTE-ACCESS.md"),
                   ("module", "desktop/lib/assistant/speech_voice.dart"),
                   ("module", "desktop/lib/assistant/url_device_sink.dart")]},
]
