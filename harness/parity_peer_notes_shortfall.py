"""parity_peer_notes_shortfall.py -- the rows that had no reasoning behind them.

Twelve rows were declared before the note rule existed and were frozen in
`UNDOCUMENTED` as the shortfall they were. Nine of them are written up here,
from a peer reading done on 2026-09-06. Three are still there, and the set
records what each one still needs.

What made the write-up possible is that Cursor, Codex, and Claude Code each
publish an `llms.txt` that enumerates every page they have. Reading one in full
on a dated day turns "no page on this topic" from something a reader has to take
on trust into something they can check against the same index. That matters most
on the five rows below where every peer cell reads NO, because those are the rows
that hand this project a star, and a star resting on a gap in our own research
would be a claim in our own favour.

Two cells moved in the writing. Codex `durable-memory-recall` went NO to PART,
which costs us nothing and corrects a reading that flattered us. Cursor
`mcp-client-and-server` went YES to PART, which flatters us, so it is grounded on
three independent Cursor pages rather than one.

A practical note for whoever reads a peer surface next. Cursor's own `llms.txt`
lists page URLs with a `.md` suffix that answer 404 to a direct fetch; the same
path without the suffix resolves. Codex and Claude Code serve the suffixed form.
"""
from __future__ import annotations

#: Row key -> why every peer cell on that row reads the way it does, for rows
#: that carried no note until 2026-09-06. Merged into `NOTES` next door.
NOTES: dict[str, str] = {
    "receipt-on-every-answer":
        "All five NO, and the near misses are what make that checkable. Codex "
        "publishes an append-only compliance log stream "
        "(learn.chatgpt.com/docs/enterprise/compliance-api, read 2026-09-06) "
        "that requires an admin role, covers a workspace, and describes no "
        "hash over anything. Cursor ships the same shape at "
        "account/teams/admin-api#get-audit-logs. Claude Code ships telemetry "
        "export at agent-sdk/observability. An org-level audit stream answers "
        "who did what inside a tenant, which is a different artifact from a "
        "record attached to one answer that a reader outside the tenant can "
        "re-derive, so scoring those logs as partial would blur two things "
        "worth keeping apart. Codex's record-and-replay page is the other near "
        "miss and is further away than its name suggests: it teaches a "
        "computer-use workflow by observing window content, names no storage "
        "format, and offers nobody a way to check a run afterwards. The hermes "
        "and omp source readings of 2026-09-06 both end at no chained record. "
        "The absence half rests on the three published indexes, each read in "
        "full on 2026-09-06, which carry no page on receipts, provenance, "
        "signing, or hash chains.",

    "projected-world-hash":
        "All five NO, off the same index reads as receipt-on-every-answer. No "
        "page in any of the three indexes read on 2026-09-06 names a root hash "
        "over projected state. The nearest published mechanism is Claude "
        "Code's checkpointing, which restores files to an earlier point. That "
        "is a rewind, and a checkpoint a caller can move without anything "
        "noticing is not what this row scores. Neither hermes nor omp keeps a "
        "chained record at all, which both 2026-09-06 source readings found "
        "directly rather than by absence.",

    "loop-closure-audit":
        "All five NO. A peer would have to write the loop down before it could "
        "audit one, and none of the five publishes that object. Codex comes "
        "nearest by shipping memories and a compliance stream, which are two "
        "surfaces with nothing published that ties a memory back to the run it "
        "came from. Grounded on the full index reads of 2026-09-06 rather than "
        "any single page, because the claim being made is an absence.",

    "signed-receipt-external-anchor":
        "All five NO, and this row is stricter than the receipt row above it. "
        "The anchor has to sit outside the project, so a peer that signed its "
        "own receipts with its own key would still read NO here. None of the "
        "five signs a run at all. No page in any index read on 2026-09-06 "
        "mentions signing a run, a transparency log, a timestamp authority, or "
        "an outside notary of any kind. The omp README ends with the sentence "
        "that no audit log, receipt signing, or hash-chain verification is "
        "mentioned, and the hermes reading of the same date found no signature "
        "over a run.",

    "formal-proof-oracle":
        "All five NO. No proof assistant appears anywhere in the three "
        "published indexes read on 2026-09-06: no Lean, no Coq, no Z3, no SMT "
        "page of any kind. omp runs a verifier inside its task isolation and "
        "hermes exposes verify recipes reporting an exit code, and an exit "
        "code from a command that never ran looks the same as a passing check "
        "unless something says otherwise. That second half is where the "
        "absence bites hardest. A peer with no oracle has nothing to report "
        "UNVERIFIABLE about and simply carries on.",

    "dap-run-record":
        "All five NO, which needs saying carefully, because omp does ship a "
        "DAP client and reads YES on dap-debug-session next door. This row is "
        "the narrower one: a default-deny grant boundary on the two reverse "
        "requests, a re-checkable record of every frame in both directions, "
        "and a verify command that re-derives the chain offline. omp runs a "
        "debugger and keeps no such record. Cursor's nearest page is "
        "agent/debug-mode, an agent mode rather than a debug adapter, and the "
        "Cursor index of 2026-09-06 carries no DAP page at all. Neither the "
        "Codex index nor the Claude Code index does. hermes returns zero hits "
        "for DebugAdapter. A row where this project ships the only instance is "
        "the row most worth doubting, so what is written up here is the "
        "peer-side reading and not our own implementation.",

    "mcp-client-and-server":
        "Cursor moved from YES to PART on 2026-09-06. That correction moves in "
        "our favour, so it carries three independent pages rather than one. "
        "cursor.com/docs/mcp describes only the consuming half, saying MCP "
        "servers expose capabilities that connect Cursor to external tools or "
        "data sources. docs/sdk/bridge is where a served surface would live "
        "and instead exposes an sdk.v1 Connect and protobuf contract, with no "
        "mention of MCP on the page. docs/cli/overview lists an agent "
        "subcommand and its session controls, and nothing that serves. The "
        "complete Cursor index read the same day names no other page where the "
        "server half could be documented. "
        "The other four hold. Claude Code serves itself: code.claude.com/docs/"
        "en/mcp carries the heading \"Use Claude Code as an MCP server\" over "
        "the command `claude mcp serve`. That cell was nearly lowered on a "
        "fetch of the CLI reference whose summary reported no such subcommand, "
        "which is worth recording as its own lesson. An absence read off a "
        "summary of a page is not an absence in the page. Codex publishes both "
        "halves, extend/mcp for the client and mcp-server for the served "
        "surface. hermes stays PART and omp stays YES from the 2026-09-06 "
        "source readings.",

    "durable-memory-recall":
        "Codex moved from NO to PART on 2026-09-06. It ships local memory "
        "files under a memories directory in the Codex home that, in the words "
        "of learn.chatgpt.com/docs/customization/memories, include summaries, "
        "durable entries, recent inputs, and supporting evidence from prior "
        "chats. NO there was a claim in our own favour, the direction the "
        "lsp-go-to-definition note flags as least likely to be caught by an "
        "audit. PART and not YES, because the row asks for content-addressed "
        "memory with verbatim, provenance-carrying recall: those files are "
        "generated summaries with no hash, no address, and no pointer back to "
        "the chat behind them. Nothing published says a person accepted one, "
        "and the page tells users not to edit them on the grounds that they "
        "are generated state. "
        "Cursor stays PART on rules, which are files a person writes and "
        "version controls. The word memory appears once on cursor.com/docs/"
        "rules, inside a sentence about models not retaining any. hermes and "
        "omp stay YES from the 2026-09-06 source readings. No star moves in "
        "either direction, since the row already carried peer cells above NO.",

    "lsp-diagnostics-references":
        "codex NO, the rest above it. The codex cell is an absence claim and "
        "rests on the complete index at learn.chatgpt.com read 2026-09-06, "
        "which carries no LSP page. Read it as documented absence rather than "
        "proof the binary cannot do it. cursor is an editor built on VS Code, "
        "where diagnostics and find-references are furniture, so that cell is "
        "inference from what the product is and not from a page that says so. "
        "It is the weakest cell in the row and should be the first one "
        "re-read. hermes carries a full LSP client under agent/lsp/ and omp "
        "uses LSP for navigation, both read 2026-09-06. claude-code is "
        "grounded in the lsp-go-to-definition note, which corrected this row's "
        "sibling after both of its cells were found wrong in our favour.",
}
