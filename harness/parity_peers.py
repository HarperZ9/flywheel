"""parity_peers.py -- what other products declare, row by row.

This is the half of the capability matrix that is NOT witnessed. A Flywheel
cell names a witness in this repo and `parity.parity_matrix` checks it. A peer
cell is a dated reading of someone else's public documentation or public
source, carries no verdict weight, and can be wrong the day after it is
written. The two kinds of claim live in separate modules because they are
separate kinds of claim.

Who the peers are, when each was read, and what that reading covered is in
`parity_peer_roster.py`. The four cell values are defined there too and
re-exported here, so an importer that only wants the table gets one import.

The audit trail is `parity_peer_notes.NOTES`, keyed by row. A note says which
half of a row a peer has and which half it does not, because a cell with no
reasoning behind it cannot be checked by anyone but its author. Twelve rows
declared before that rule carry no note and are listed there as the shortfall
they are; a row added now needs one or `tests/test_parity.py` fails.
"""
from __future__ import annotations

from .parity_peer_roster import (  # noqa: F401  (re-exported for importers)
    NO,
    PART,
    PEER_KEYS,
    PEERS,
    UNREAD,
    VALUES,
    YES,
)

# Cells left UNREAD are not judgements. They are rows where the peer's surface
# was not read on the date in the roster, and they suppress the star.
DECLARATIONS: dict[str, dict[str, object]] = {
    "any-provider-routing":
        {"codex": PART, "cursor": PART, "claude-code": NO,
         "hermes": YES, "omp": YES},
    "receipt-on-every-answer":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": NO, "omp": NO},
    "integrity-guard":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": NO, "omp": NO},
    "verifier-ensembling":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": NO, "omp": NO},
    "staged-workflows":
        {"codex": NO, "cursor": NO, "claude-code": PART,
         "hermes": PART, "omp": PART},
    "profile-manifests":
        {"codex": PART, "cursor": PART, "claude-code": PART,
         "hermes": YES, "omp": YES},
    "plugin-registry":
        {"codex": YES, "cursor": PART, "claude-code": YES,
         "hermes": PART, "omp": YES},
    "mcp-client-and-server":
        {"codex": YES, "cursor": PART, "claude-code": YES,
         "hermes": PART, "omp": YES},
    "durable-memory-recall":
        {"codex": PART, "cursor": PART, "claude-code": PART,
         "hermes": YES, "omp": YES},
    "context-compaction-receipt":
        {"codex": PART, "cursor": PART, "claude-code": PART,
         "hermes": PART, "omp": PART},
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
         "hermes": PART, "omp": PART},
    "native-receipted-linter":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": PART, "omp": NO},
    "lsp-go-to-definition":
        {"codex": NO, "cursor": YES, "claude-code": YES,
         "hermes": YES, "omp": YES},
    "lsp-diagnostics-references":
        {"codex": NO, "cursor": YES, "claude-code": YES,
         "hermes": YES, "omp": YES},
    "lsp-run-record":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": PART, "omp": NO},
    "dap-debug-session":
        {"codex": NO, "cursor": YES, "claude-code": NO,
         "hermes": NO, "omp": YES},
    "dap-run-record":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": NO, "omp": NO},
    "acp-delegation-receipt":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": PART, "omp": PART},
    "plugin-marketplace":
        {"codex": YES, "cursor": YES, "claude-code": YES,
         "hermes": YES, "omp": YES},
    "secure-credentials":
        {"codex": YES, "cursor": YES, "claude-code": YES,
         "hermes": YES, "omp": YES},
    "agent-boundary-audit":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": PART, "omp": NO},
    "task-isolation":
        {"codex": NO, "cursor": PART, "claude-code": PART,
         "hermes": PART, "omp": PART},
    "posix-os-confinement":
        {"codex": YES, "cursor": YES, "claude-code": YES,
         "hermes": PART, "omp": PART},
    "isolation-probe":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": NO, "omp": NO},
    "credential-exposure-scan":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": NO, "omp": PART},
    "two-authority-kill-switch":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": NO, "omp": NO},
    "per-action-operator-grant":
        {"codex": PART, "cursor": PART, "claude-code": PART,
         "hermes": PART, "omp": YES},
    "signed-receipt-external-anchor":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": NO, "omp": NO},
    "formal-proof-oracle":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": NO, "omp": NO},
    "native-acceleration-with-fallback":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": PART, "omp": PART},
    "autonomy-tiers-and-decision-records":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": PART, "omp": PART},
    "accepted-lesson-loop":
        {"codex": NO, "cursor": PART, "claude-code": PART,
         "hermes": PART, "omp": PART},
    "private-verified-benchmarks":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": PART, "omp": YES},
    "paired-uplift-measurement":
        {"codex": NO, "cursor": NO, "claude-code": NO,
         "hermes": PART, "omp": PART},
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
