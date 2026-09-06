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
"""
from __future__ import annotations

#: Row key -> why every peer cell on that row reads the way it does.
NOTES: dict[str, str] = {
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
    "agent-boundary-audit":
        "The scout read hermes as YES and the sources do not carry it "
        "that far. hermes_cli/security_audit.py runs an OSV scan over the "
        "dependency set, which is a real run bill of materials, and "
        "SECURITY.md section 2 states a trust model. Egress is the half "
        "that does not hold: network isolation is a Docker deployment "
        "guide of two networks behind an allow-list proxy, so an operator "
        "configures the boundary and the running process never reads its "
        "own classified egress. omp is NO on all three.",
    "task-isolation":
        "Three of the five give a task its own tree, and the mechanism "
        "half is not where Flywheel leads. omp's pi-iso resolves more "
        "than this ladder does: APFS clones, btrfs and zfs reflinks, "
        "overlayfs, projfs and rcopy, against reflink, clonefile and copy "
        "here with no rung for the rest. cursor runs up to eight agents "
        "each in its own git worktree behind /worktree and "
        ".cursor/worktrees.json (cursor.com/docs/configuration/ "
        "worktrees, read 2026-09-06). claude-code takes --worktree and an "
        "`isolation: worktree` subagent field "
        "(code.claude.com/docs/en/worktrees, read 2026-09-06). hermes "
        "hardens containers for its terminal backends. All four are PART "
        "for one reason: nothing records which mechanism ran, what the "
        "others refused, or what the copy cost, so a timing read months "
        "later cannot be attributed to the filesystem. codex is NO. Its "
        "sandbox is a permission boundary around the actual working "
        "directory, and worktrees appear only as advice to the user "
        "(learn.chatgpt.com/docs/sandboxing, read 2026-09-06, where "
        "developers.openai.com/codex/concepts/sandboxing now redirects).",
    "isolation-probe":
        "omp has real isolation and this row is not about having it. pi- "
        "iso resolves APFS clones, btrfs and zfs reflinks, overlayfs, "
        "projfs and rcopy, and hermes hardens containers for its terminal "
        "backends. Neither runs an active test against the boundary it is "
        "inside, and neither seals the set of boundaries that were tried. "
        "Providing a boundary and probing one are different capabilities.",
    "credential-exposure-scan":
        "omp is PART on the reporting half. docs/secrets.md substitutes a "
        "deterministic placeholder such as $3P8W5JH1TK2Q$ for a detected "
        "secret, which is a non-reversible fingerprint in `replace` mode, "
        "though the `obfuscate` mode is reversible by design. Nothing "
        "scans for reachable secrets and no receipt seals the result. "
        "hermes resolves credentials from several sources and never "
        "enumerates what is exposed.",
    "two-authority-kill-switch":
        "Both can stop a run and each does it under one authority. hermes "
        "carries gateway/hosted/room_policy_checkpoint.py, which is the "
        "closest thing either has to a sealed stop, and it seals a policy "
        "digest rather than the stop. Nothing in either requires a second "
        "authority, and neither records a refusal to stop.",
    "per-action-operator-grant":
        "omp is YES, not PART: destructive tools pause for confirmation "
        "and a permission can be granted once and remembered for the "
        "session, which is the whole of what this row describes.",
    "native-acceleration-with-fallback":
        "omp compiles roughly 80k lines of Rust into six crates behind a "
        "native addon loader. PART because the fallback half of the row, "
        "a pure path that runs when the native one will not load, was not "
        "read. hermes ships a native FTS5 extension for CJK tokenization "
        "with its own README under native/fts5_cjk/. The compiled half is "
        "there. Nothing states an equivalent path for a machine that "
        "cannot build it, which is the half this row exists to name.",
    "autonomy-tiers-and-decision-records":
        "Both gate what the agent may do by a recorded tier. omp's "
        "approval mode has three tiers (read, write, exec) and three "
        "modes (always-ask, write, yolo), with per-tool policy allow, "
        "deny or prompt, and it fails closed: \"Tools without an "
        "`approval` declaration, and malformed approval decisions, are "
        "treated as `exec`.\" hermes has an approval mode command and a "
        "hosted execution policy carrying a sha256 policy_digest. The "
        "decision record behind a tier is what neither keeps.",
    "private-verified-benchmarks":
        "omp is the one YES on this row across the whole table, and it is "
        "earned. packages/metaharness is \"one manager for repository "
        "benchmarks\" over a private task set, with the same experiment, "
        "run and trace model, a model flag that repeats across endpoints, "
        "a verifier run \"in the same mutated VM\", run rows carrying "
        "benchmark, score, progress, spend and tokens, and a --budget in "
        "dollars. That is a private set, a gate the operator owns, and a "
        "price attached to verified quality. hermes runs real evals under "
        "evals/ and its task sets are public, so it holds the run half "
        "only.",
    "paired-uplift-measurement":
        "hermes runs paired arms for real: its core tool-deferral summary "
        "reports an \"A/B verdict\" over 288 live runs, 14 tasks by 3 reps, "
        "with contested cells re-run to n=6 and the result called \"flat "
        "within rep noise\". That is a preserved null, which is the hard "
        "part of this row. What is missing is a stated interval, so the "
        "reading is a verdict rather than a bound. omp's metaharness "
        "launches \"a comparable arm; sample + config inherited from a "
        "sibling\" and scores it, and it reports no interval either.",
    "phone-access-own-tunnel":
        "Both reach a phone, and neither over a tunnel the user owns: "
        "hermes through third-party messaging platforms, omp through a "
        "shared session link. That is the distinction this row is named "
        "for.",
}

#: Rows declared before the note rule. This set can only shrink; every
#: new row needs an entry in NOTES instead.
UNDOCUMENTED: frozenset = frozenset({
    "receipt-on-every-answer",
    "mcp-client-and-server",
    "durable-memory-recall",
    "workspace-sandbox",
    "live-agent-stream",
    "projected-world-hash",
    "loop-closure-audit",
    "lsp-diagnostics-references",
    "dap-run-record",
    "signed-receipt-external-anchor",
    "formal-proof-oracle",
    "accepted-lesson-loop",
})
