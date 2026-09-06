"""parity_peer_notes.py -- why each peer cell reads the way it does.

These were comments above the rows in `parity_peers.py` until that file
reached the line gate, which a table that grows by one row per shipped
capability was always going to do. Moving them here keeps every word and
buys three things a comment could not give: a note is bound to a row key
rather than to a position in a file, an orphan note fails a test instead of
sitting above the wrong row, and the audit trail can be read by anything
that reads the matrix.

A note says which half of a row a peer has and which half it does not. The
rows in UNDOCUMENTED predate the rule and carry cells with no reasoning
behind them, which is a real shortfall rather than a style choice: those
cells cannot be checked by anyone but their author. The set only shrinks,
and a new row that is in neither place fails `tests/test_parity.py`.

That gate has since taken this file too. The notes for the rows added on
2026-09-03 live in `parity_peer_notes_boundary`, the nine written up on
2026-09-06 to clear most of the shortfall live in `parity_peer_notes_shortfall`,
and the nine rows the coverage reading owed live in
`parity_peer_notes_coverage`. All three are merged into `NOTES` at the bottom,
so nothing that reads the matrix has to know there are four.
"""
from __future__ import annotations

from .parity_peer_notes_boundary import NOTES as _BOUNDARY
from .parity_peer_notes_coverage import NOTES as _COVERAGE
from .parity_peer_notes_shortfall import NOTES as _SHORTFALL

#: Row key -> why every peer cell on that row reads the way it does, for the
#: rows declared in July. The ones added on 2026-09-03 have theirs next door
#: and are merged into `NOTES` below. Read that module for the seam.
_EARLY: dict[str, str] = {
    "any-provider-routing":
        "Codex was NO here and that was wrong: `model_providers.<id>` "
        "takes base_url, env_key and wire_api, so it does route to a "
        "provider of the user's choosing. PART on two counts the same "
        "page carries, wire_api accepts only \"responses\" and nothing "
        "describes a failover chain. hermes is YES on the whole row. "
        "agent/provider_registry.py routes one request shape to any "
        "registered provider, and hermes_cli/fallback_cmd.py manages \"the "
        "fallback provider chain (tried in order when the primary fails)\" "
        "with entries shaped {provider, model, base_url}.",
    "integrity-guard":
        "Both read for a tamper guard on a passing result and neither has "
        "one. hermes runs verify recipes in agent/verify_runner.py, omp "
        "runs a verifier inside the mutated VM. A recipe that exits zero "
        "is taken at its word in both, so a doctored pass is a pass.",
    "verifier-ensembling":
        "Neither combines oracles under a stated rule. hermes runs its "
        "recipes in sequence and reports each. omp's metaharness scores "
        "arms separately and leaves the comparison to a reader.",
    "staged-workflows":
        "PART for the three that ship staged execution without a chained "
        "receipt per run. Claude Code's workflow primitives (agent, "
        "parallel, pipeline, phase, resume by replay) are a full staging "
        "surface; the receipt is the half of this row none of them claim.",
    "profile-manifests":
        "Both are YES, and both go further than the three PART cells "
        "beside them. hermes documents profile routing in docs/profile- "
        "routing.md, a named profile carrying its own model and provider "
        "selection. omp's `--profile <name>` gives \"an isolated profile "
        "for auth, sessions, settings, and caches\", which is the whole "
        "row.",
    "plugin-registry":
        "hermes keeps builtin tools and MCP servers reachable from one "
        "place, and optional-mcps/<name>/manifest.yaml is a real registry "
        "file. The lane half of the row has no counterpart, so the three "
        "kinds do not sit in one registry the way this row asks.",
    "context-compaction-receipt":
        "The scout read this as YES for hermes and reading the source "
        "lowered it. docs/micro-compaction.md describes genuine bounded "
        "context: a cursor, one rolling summary, and archive_and_compact "
        "which \"atomically soft-archives the active rows and inserts the "
        "compacted set\", so an original exchange survives the fold. What "
        "the row asks for beyond that is a receipt per fold and a "
        "documented way to recall a folded exchange. The document returns "
        "nothing for receipt, recall or restore.",
    "adaptive-routing-scoreboard":
        "The scout said NO for both and the source says otherwise. hermes "
        "ships agent/credential_pool.py, a \"persistent multi-credential "
        "pool for same-provider failover\" with status-sized cooldowns, "
        "exhaustion latching and rotation, which is a live circuit "
        "breaker by any reading. omp's retry.fallbackChains does the same "
        "on a quota wall and restores the primary on cooldown. Neither "
        "records an observed success rate or a latency, and both break on "
        "the credential rather than the provider, so the scoreboard half "
        "of the row is absent. PART is the honest cell here: calling it "
        "NO would hand us a star for a mechanism a competitor ships.",
    "native-receipted-linter":
        "hermes has a built-in linter at tools/skill_linter.py, so the "
        "row's first half holds. Its findings are printed, not content- "
        "addressed, and nothing re-checks a stored finding later.",
    "lsp-go-to-definition":
        "Both claude-code cells below were NO and both were wrong. Read "
        "from code.claude.com/docs/en/plugins-reference: a plugin carries "
        "`lspServers` in plugin.json or a `.lsp.json` beside it, naming "
        "the server command and the extensions it handles, plus a "
        "`diagnostics` option that pushes diagnostics into context by "
        "default. A cell that stays NO once a competitor ships the "
        "feature is a claim in our own favour, which is the direction an "
        "audit is least likely to catch.",
    "lsp-run-record":
        "hermes ships agent/lsp/eventlog.py, so it keeps some record of "
        "the exchange. Whether that record is chained or re-derivable was "
        "not read, and PART is what an unopened file is worth.",
    "dap-debug-session":
        "Read 2026-09-05 from Microsoft's own implementors list at "
        "microsoft.github.io/debug-adapter-protocol/implementors/tools. "
        "It names VS Code, Visual Studio, Eclipse, Emacs, Theia, "
        "Vim/Neovim, IntelliJ, Zed and Kate, and it names neither Cursor, "
        "Codex nor Claude Code. The cursor cell is YES anyway and by "
        "inference rather than off that list, since Cursor is a VS Code "
        "fork and ships its debugger. Saying so here rather than quietly "
        "writing YES is the point of dating these cells. omp ships "
        "src/dap/{client,session,types}.ts, a debug tool and "
        "docs/tools/debug.md; hermes returns zero hits for DebugAdapter "
        "and has no dap module.",
    "acp-delegation-receipt":
        "Read 2026-09-05 from the protocol's own lists at "
        "agentclientprotocol.com/get-started/agents and /get- "
        "started/clients. Codex CLI, Cursor and Claude Agent are all "
        "listed on the AGENT side and none of the three is listed as a "
        "CLIENT, which is the half that holds the permission boundary and "
        "can therefore witness a refusal. hermes and omp both ship an ACP "
        "adapter and neither states a receipt for the turn.",
    "plugin-marketplace":
        "A catalog plus one-step install, both halves. The desktop app's "
        "mcp-directory.ts names \"the Nous-approved install catalog "
        "(optional-mcps/<name>/manifest.yaml)\" as \"the single source of "
        "truth for suggestible servers\", served through GET "
        "/api/mcp/catalog, and desktop-plugin-install.ts performs the "
        "install.",
    "secure-credentials":
        "resolve_anthropic_token() in agent/anthropic_credentials.py "
        "reads ANTHROPIC_TOKEN, then ANTHROPIC_API_KEY, then "
        "~/.claude/.credentials.json or the macOS Keychain, then the "
        "auth.json pool. Keychain storage and reuse of a provider CLI "
        "login are the two things this row names.",
}

#: The name every reader imports. A key in more than one part would be
#: resolved here without a word, so `tests/test_parity.py` asserts the
#: four share no keys at all.
NOTES: dict[str, str] = {**_EARLY, **_BOUNDARY, **_SHORTFALL, **_COVERAGE}

#: Rows declared before the note rule. This set can only shrink; every
#: new row needs an entry in NOTES instead. It was twelve until 2026-09-06,
#: when nine were written up from a peer reading. Each of the three left
#: says what it is still short of, so nobody has to guess whether it was
#: skipped or judged.
UNDOCUMENTED: frozenset = frozenset({
    # Four of five are grounded: Cursor on Landlock and seccomp, Claude Code
    # on bubblewrap and Seatbelt, omp on pi-iso. The Codex sandboxing page
    # and any hermes workspace-root check are both unread.
    "workspace-sandbox",
    # Every cell reads YES and the row earns nobody a star, so it has been
    # the cheapest one to leave. Naming the streaming surface for each of
    # the five is the work: Claude Code's is `--output-format stream-json`.
    "live-agent-stream",
    # The Cursor and Codex halves were settled on 2026-09-06: rules a person
    # writes by hand carry no failure record, and Codex memories carry no
    # acceptance step. The hermes and omp cells still rest on nothing read.
    "accepted-lesson-loop",
})
