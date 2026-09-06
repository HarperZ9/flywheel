"""parity_peers.py -- what other products declare, and when we read it.

This is the half of the capability matrix that is NOT witnessed. A Flywheel
cell names a witness in this repo and `parity.parity_matrix` checks it. A peer
cell is a dated reading of someone else's public documentation or public source,
carries no verdict weight, and can be wrong the day after it is written. The two
kinds of claim live in separate modules because they are separate kinds of
claim.

Four values, and the fourth is the one that matters:

    YES      the peer's own docs or source say it ships this
    PART     it ships some of what the row describes, not all
    NO       read the surface where it would be documented, it is not there
    UNREAD   nobody here has checked

UNREAD exists because the star on the published table means "no listed peer
declares this," and a cell nobody read cannot support that sentence. Before
this value the table had three, so an unchecked capability was indistinguishable
from a checked absence, and every gap in our own research read as a point in our
favour. `parity_matrix` now stars a row only when every peer cell is NO.

The peer set is five and the table says so by name. It was three for a while
while the two closest competitors, both MIT and both shipping surfaces this
matrix scores, went unlisted. "Against the field" over a peer set chosen by us
is a claim about the peers we picked.
"""
from __future__ import annotations

YES, PART, NO, UNREAD = True, "partial", False, None

VALUES = (YES, PART, NO, UNREAD)

#: One column each, in table order, with the date its cells were last read and
#: the surface they were read from. A peer added here without a full column in
#: DECLARATIONS fails `tests/test_parity.py`.
PEERS = (
    {"key": "codex", "label": "codex", "read_on": "2026-09-05",
     "source": "developers.openai.com/codex and the config reference"},
    {"key": "cursor", "label": "cursor", "read_on": "2026-09-03",
     "source": "cursor.com/docs"},
    {"key": "claude-code", "label": "claude code", "read_on": "2026-09-05",
     "source": "code.claude.com/docs"},
    {"key": "hermes", "label": "hermes", "read_on": "2026-09-05",
     "source": "hermes-agent.nousresearch.com and NousResearch/hermes-agent"},
    {"key": "omp", "label": "omp", "read_on": "2026-09-05",
     "source": "can1357/oh-my-pi README, docs/ and src/"},
)

PEER_KEYS = tuple(p["key"] for p in PEERS)

# hermes: the Hermes Agent (MIT). Its front page names persistent memory, five
# terminal backends with container hardening, isolated subagents, and cron. Its
# repo carries a full LSP client under agent/lsp/ and an ACP adapter under
# acp_adapter/, and zero hits for DebugAdapter. Its documentation navigation has
# no section for receipts, audit, ledger, or signing, which is what the NO cells
# on the receipt rows below record: read where it would be documented, absent.
#
# omp: Oh My Pi (MIT), a coding agent whose README states 60+ providers with
# configurable fallback chains, LSP for navigation and refactoring, DAP against
# real debuggers (lldb, dlv, debugpy), subagent worktree isolation, permission
# gating remembered per session, and a plugin marketplace. The same README ends
# "No audit log, receipt signing, or hash-chain verification is mentioned."
#
# Cells left UNREAD are not judgements. They are rows where the peer's surface
# was not read on the date above, and they suppress the star.
DECLARATIONS: dict[str, dict[str, object]] = {
    # Codex was NO here and that was wrong: `model_providers.<id>` takes
    # base_url, env_key and wire_api, so it does route to a provider of the
    # user's choosing. PART on two counts the same page carries, wire_api
    # accepts only "responses" and nothing describes a failover chain.
    "any-provider-routing":
        {"codex": PART, "cursor": PART, "claude-code": NO,
         "hermes": UNREAD, "omp": YES},
    "receipt-on-every-answer":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": NO, "omp": NO},
    "integrity-guard":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": UNREAD, "omp": UNREAD},
    "verifier-ensembling":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": UNREAD, "omp": UNREAD},
    # PART for the three that ship staged execution without a chained receipt
    # per run. Claude Code's workflow primitives (agent, parallel, pipeline,
    # phase, resume by replay) are a full staging surface; the receipt is the
    # half of this row none of them claim.
    "staged-workflows":
        {"codex": NO, "cursor": NO, "claude-code": PART,
         "hermes": PART, "omp": PART},
    "profile-manifests":
        {"codex": PART, "cursor": PART, "claude-code": PART,
         "hermes": UNREAD, "omp": UNREAD},
    "plugin-registry":
        {"codex": YES, "cursor": PART, "claude-code": YES,
         "hermes": UNREAD, "omp": YES},
    "mcp-client-and-server":
        {"codex": YES, "cursor": YES, "claude-code": YES,
         "hermes": PART, "omp": YES},
    "durable-memory-recall":
        {"codex": NO, "cursor": PART, "claude-code": PART,
         "hermes": YES, "omp": YES},
    "context-compaction-receipt":
        {"codex": PART, "cursor": PART, "claude-code": PART,
         "hermes": UNREAD, "omp": PART},
    "workspace-sandbox":
        {"codex": YES, "cursor": YES, "claude-code": YES,
         "hermes": YES, "omp": YES},
    "live-agent-stream":
        {"codex": YES, "cursor": YES, "claude-code": YES,
         "hermes": YES, "omp": YES},
    "projected-world-hash":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": NO, "omp": NO},
    "loop-closure-audit":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": NO, "omp": NO},
    "adaptive-routing-scoreboard":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": UNREAD, "omp": UNREAD},
    "native-receipted-linter":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": UNREAD, "omp": NO},
    # Both claude-code cells below were NO and both were wrong. Read from
    # code.claude.com/docs/en/plugins-reference: a plugin carries `lspServers`
    # in plugin.json or a `.lsp.json` beside it, naming the server command and
    # the extensions it handles, plus a `diagnostics` option that pushes
    # diagnostics into context by default. A cell that stays NO once a
    # competitor ships the feature is a claim in our own favour, which is the
    # direction an audit is least likely to catch.
    "lsp-go-to-definition":
        {"codex": NO, "cursor": YES, "claude-code": YES,
         "hermes": YES, "omp": YES},
    "lsp-diagnostics-references":
        {"codex": NO, "cursor": YES, "claude-code": YES,
         "hermes": YES, "omp": YES},
    # hermes ships agent/lsp/eventlog.py, so it keeps some record of the
    # exchange. Whether that record is chained or re-derivable was not read,
    # and PART is what an unopened file is worth.
    "lsp-run-record":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": PART, "omp": NO},
    # Read 2026-09-05 from Microsoft's own implementors list at
    # microsoft.github.io/debug-adapter-protocol/implementors/tools. It names
    # VS Code, Visual Studio, Eclipse, Emacs, Theia, Vim/Neovim, IntelliJ, Zed
    # and Kate, and it names neither Cursor, Codex nor Claude Code. The cursor
    # cell is YES anyway and by inference rather than off that list, since
    # Cursor is a VS Code fork and ships its debugger. Saying so here rather
    # than quietly writing YES is the point of dating these cells. omp ships
    # src/dap/{client,session,types}.ts, a debug tool and docs/tools/debug.md;
    # hermes returns zero hits for DebugAdapter and has no dap module.
    "dap-debug-session":
        {"codex": NO, "cursor": YES, "claude-code": NO,
         "hermes": NO, "omp": YES},
    "dap-run-record":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": NO, "omp": NO},
    # Read 2026-09-05 from the protocol's own lists at
    # agentclientprotocol.com/get-started/agents and /get-started/clients.
    # Codex CLI, Cursor and Claude Agent are all listed on the AGENT side and
    # none of the three is listed as a CLIENT, which is the half that holds
    # the permission boundary and can therefore witness a refusal. hermes and
    # omp both ship an ACP adapter and neither states a receipt for the turn.
    "acp-delegation-receipt":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": PART, "omp": PART},
    "plugin-marketplace":
        {"codex": YES, "cursor": YES, "claude-code": YES,
         "hermes": UNREAD, "omp": YES},
    "secure-credentials":
        {"codex": YES, "cursor": YES, "claude-code": YES,
         "hermes": UNREAD, "omp": YES},
    "agent-boundary-audit":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": UNREAD, "omp": UNREAD},
    "isolation-probe":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": UNREAD, "omp": UNREAD},
    "credential-exposure-scan":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": UNREAD, "omp": UNREAD},
    "two-authority-kill-switch":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": UNREAD, "omp": UNREAD},
    # omp is YES, not PART: destructive tools pause for confirmation and a
    # permission can be granted once and remembered for the session, which is
    # the whole of what this row describes.
    "per-action-operator-grant":
        {"codex": PART, "cursor": PART, "claude-code": PART,
         "hermes": PART, "omp": YES},
    "signed-receipt-external-anchor":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": NO, "omp": NO},
    "formal-proof-oracle":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": NO, "omp": NO},
    # omp compiles roughly 80k lines of Rust into six crates behind a native
    # addon loader. PART because the fallback half of the row, a pure path
    # that runs when the native one will not load, was not read.
    "native-acceleration-with-fallback":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": UNREAD, "omp": PART},
    "autonomy-tiers-and-decision-records":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": UNREAD, "omp": UNREAD},
    "accepted-lesson-loop":
        {"codex": NO, "cursor": PART, "claude-code": PART,
         "hermes": PART, "omp": PART},
    "private-verified-benchmarks":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": UNREAD, "omp": UNREAD},
    "paired-uplift-measurement":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": UNREAD, "omp": UNREAD},
    # Both reach a phone, and neither over a tunnel the user owns: hermes
    # through third-party messaging platforms, omp through a shared session
    # link. That is the distinction this row is named for.
    "phone-access-own-tunnel":
        {"codex": YES, "cursor": NO, "claude-code": YES,
         "hermes": PART, "omp": PART},
}


def declarations_for(key: str) -> dict[str, object]:
    """Every peer's cell for one row, UNREAD where the row is not declared."""
    row = DECLARATIONS.get(key) or {}
    return {peer: row.get(peer, UNREAD) for peer in PEER_KEYS}


def undeclared_rows(keys) -> list[str]:
    """Row keys with no entry here at all, so a new row cannot slip in silent."""
    return [k for k in keys if k not in DECLARATIONS]
