"""parity_peer_roster.py -- who the peers are, and when each was last read.

Two facts get confused when they share a file. Who is in the comparison and
when their surface was read is one; what each of them declares on a given row
is the other, and that one lives in `parity_peers.py`. Splitting them keeps the
roster short enough to audit at a glance, which is where the reading dates and
the sources have to be legible.

Four values, and the fourth is the one that matters:

    YES      the peer's own docs or source say it ships this
    PART     it ships some of what the row describes, not all
    NO       read the surface where it would be documented, it is not there
    UNREAD   nobody here has checked

UNREAD exists because the star on the published table means "no listed peer
declares this," and a cell nobody read cannot support that sentence. Before
this value the table had three, so an unchecked capability was indistinguishable
from a checked absence, and every gap in our own research read as a point in our
favour. `parity_matrix` stars a row only when every peer cell is NO.

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
    {"key": "codex", "label": "codex", "read_on": "2026-09-06",
     "source": "learn.chatgpt.com/docs, the full page index at /llms.txt, "
               "and the config reference"},
    {"key": "cursor", "label": "cursor", "read_on": "2026-09-06",
     "source": "cursor.com/docs and the full page index at /llms.txt"},
    {"key": "claude-code", "label": "claude code", "read_on": "2026-09-06",
     "source": "code.claude.com/docs and the full page index at "
               "/docs/llms.txt"},
    {"key": "hermes", "label": "hermes", "read_on": "2026-09-06",
     "source": "NousResearch/hermes-agent source: SECURITY.md, docs/, "
               "agent/, hermes_cli/, gateway/, evals/, optional-mcps/"},
    {"key": "omp", "label": "omp", "read_on": "2026-09-06",
     "source": "can1357/oh-my-pi README, docs/ and packages/metaharness/"},
)

PEER_KEYS = tuple(p["key"] for p in PEERS)

# What each reading covered, so a later reader can tell a thin pass over a
# front page from a pass through the source.
#
# codex, cursor, claude-code: read from published documentation only. Where a
# cell turns on a mechanism rather than a claim, the note in
# `parity_peer_notes*` names the page it came from.
#
# All three were re-read on 2026-09-06, starting from the page index each one
# publishes at llms.txt rather than from its navigation. A front page shows what
# a vendor wants read first; the index enumerates everything, so "no page on
# this topic" becomes a claim a later reader can check against the same file on
# the same date. That reading corrected two cells, both written up in
# `parity_peer_notes_shortfall`: codex durable-memory-recall NO to PART, and
# cursor mcp-client-and-server YES to PART.
#
# The codex source moved host as well as date. developers.openai.com/codex now
# answers 308 to learn.chatgpt.com/docs, and the old string would have sent a
# later reader to a redirect. One retrieval trap is worth recording: Cursor's
# own index lists page URLs with a .md suffix that answer 404 to a direct fetch,
# and the same path without the suffix resolves.
#
# hermes: the Hermes Agent (MIT), read 2026-09-06 from its source rather than
# its front page: agent/provider_registry.py and hermes_cli/fallback_cmd.py for
# routing, agent/credential_pool.py and agent/secret_sources/ for credentials,
# docs/micro-compaction.md for context, hermes_cli/security_audit.py and
# docs/security/network-egress-isolation.md for the boundary rows, evals/ for
# the measurement rows, and SECURITY.md. It carries a full LSP client under
# agent/lsp/, an ACP adapter under acp_adapter/, and zero hits for
# DebugAdapter. The receipt rows stay NO: the repo has no chained record, no
# signature over a run, and no re-derivation.
#
# omp: Oh My Pi (MIT), read 2026-09-06 from its README, docs/cli-reference.md,
# docs/approval-mode.md, docs/secrets.md and packages/metaharness/README.md.
# 60+ providers with fallback chains under retry.fallbackChains, LSP for
# navigation, DAP against real debuggers, task isolation through pi-iso (APFS
# clones, btrfs/zfs reflinks, overlayfs, projfs), a three-tier approval mode,
# deterministic secret placeholders, and metaharness for repository benchmarks
# with comparable arms and a budget. The same README ends "No audit log,
# receipt signing, or hash-chain verification is mentioned."
