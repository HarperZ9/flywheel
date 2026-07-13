"""parity.py -- the capability matrix, witnessed not asserted.

Every Flywheel row names a WITNESS inside this repo (a module, a route
string in the gateway source, a test file) and the audit CHECKS it: a row
whose witness is missing reports ABSENT, so the matrix can fail. Competitor
cells are dated DECLARATIONS from public docs and configs, never
measurements; they are labeled as such and carry no verdict weight. The
summary names both what is uniquely witnessed here and where the field is
ahead -- the gap list is the point, not the scoreboard."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

DECLARED_ON = "2026-07-13"

# (key, description, witness) where witness is:
#   ("module", "harness/x.py")            -- file exists
#   ("route",  "/api/x")                  -- string present in gateway source
#   ("test",   "tests/test_x.py")         -- test file exists
# plus per-competitor declarations: True (ships it), False (does not),
# "partial". Competitors: codex (OpenAI Codex app), cursor, claude-code.
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
     "witnesses": [("route", "_sse_agent")],
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
    # Known gaps: rows the field ships and Flywheel does not, kept visible.
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
    {"key": "oauth-keychain",
     "desc": "per-provider OAuth with OS-keychain storage",
     "witnesses": [("module", "harness/oauth.py")],
     "codex": True, "cursor": True, "claude-code": True},
]


def _check_witness(kind: str, ref: str, gateway_src: str) -> bool:
    if kind == "module" or kind == "test":
        return (REPO / ref).is_file()
    if kind == "route":
        return ref in gateway_src
    return False


def parity_matrix() -> dict:
    """Audit every row's witnesses against this repo, right now."""
    gateway_src = (REPO / "harness" / "gateway.py").read_text(
        encoding="utf-8", errors="replace")
    rows = []
    witnessed = absent = 0
    unique = []
    gaps = []
    for r in ROWS:
        checks = [{"kind": k, "ref": ref,
                   "present": _check_witness(k, ref, gateway_src)}
                  for k, ref in r["witnesses"]]
        ok = all(c["present"] for c in checks)
        witnessed += ok
        absent += not ok
        competitors = {c: r[c] for c in ("codex", "cursor", "claude-code")}
        if ok and not any(v is True for v in competitors.values()):
            unique.append(r["key"])
        if not ok and any(v is True for v in competitors.values()):
            gaps.append(r["key"])
        rows.append({"key": r["key"], "desc": r["desc"],
                     "flywheel": "WITNESSED" if ok else "ABSENT",
                     "checks": checks, "competitors": competitors})
    return {"schema": "flywheel.parity/v1",
            "declared_on": DECLARED_ON,
            "note": "flywheel cells are audited against this repo at read "
                    "time; competitor cells are dated declarations from "
                    "public docs and configs, not measurements",
            "rows": rows,
            "summary": {"witnessed": witnessed, "absent": absent,
                        "uniquely_witnessed": unique, "gaps": gaps}}
