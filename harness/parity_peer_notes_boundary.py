"""parity_peer_notes_boundary.py -- the notes for the rows added later.

`parity_rows` carries a dated comment where the table grew. Rows above it
were declared in July. Rows below it arrived with the boundary and grant
layers, and with the measurement apparatus after them. The notes divide at
the same place, because the file they were in reached the line gate and a
table that grows by one row per shipped capability was always going to take
it there again.

Nothing else distinguishes these notes from the ones next door. Each one
answers the same question in the same register: which half of a row a peer
has, and which half it does not. `parity_peer_notes` merges both dicts into
the single `NOTES` every reader already imports. A key present in both would
be resolved silently by that merge, so a test asserts the two share none.
"""
from __future__ import annotations

#: Row key -> why every peer cell on that row reads the way it does. Read
#: through `parity_peer_notes.NOTES`, which merges this in.
NOTES: dict[str, str] = {
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
    "posix-os-confinement":
        "Three peers reached this row before Flywheel did and one of them "
        "is still ahead inside it, which is what the row is here to say. "
        "codex and claude-code ship the same two mechanisms this module "
        "ships, from the same two programs: \"On macOS, sandboxing works "
        "out of the box using the built-in Seatbelt framework\" and \"On "
        "Linux and WSL2, install bubblewrap with your package manager "
        "first\" (learn.chatgpt.com/docs/sandboxing, read 2026-09-06). "
        "claude-code carries more than either: bubblewrap plus a socat "
        "relay through a proxy holding a per-domain allowlist, an optional "
        "seccomp filter for unix sockets, a protected-path list a "
        "sandboxed command cannot write even inside its own workspace, and "
        "credential masking that hands the command a sentinel while the "
        "proxy substitutes the real value on allowed hosts "
        "(code.claude.com/docs/en/sandboxing, read 2026-09-06). Both are "
        "YES on mechanism. Network was theirs alone until the proxy "
        "landed here, and part of it still is. A CONNECT proxy over a "
        "named host set now sits under both backends in this module, "
        "with every refused request logged beside the allowed ones. "
        "Credential masking and the seccomp filter have no counterpart "
        "here. The half Flywheel holds is the record. "
        "Confinement.record() states the backend, the writable set, the "
        "hidden paths, the host rules, and the limits that did not hold, "
        "and none of the pages cited on this row describes that set "
        "landing somewhere a reader still has once the run is over. "
        "hermes and omp are PART. Searching both "
        "repositories for "
        "bubblewrap, bwrap, sandbox-exec, seatbelt and landlock returns "
        "zero against control searches for sandbox that return 386 and "
        "125, so both are indexed and the absence is a reading rather than "
        "a gap (GitHub code search, 2026-09-06). What they carry instead "
        "is heavier and less portable: hermes has nix/sandbox.nix, "
        "scripts/sandbox/proxy.py and tools/environments/vercel_sandbox.py, "
        "and omp tunes a Kata Containers runtime under infra/. A VM or a "
        "container isolates more than this argv does and needs a runtime "
        "the host may not have, which is the half neither covers. cursor "
        "is YES and is ahead of this module on one axis of three. macOS "
        "is the same Seatbelt profile through the same sandbox-exec. "
        "Linux is Landlock and seccomp composed directly, bubblewrap kept "
        "as a fallback, and the child is told which of the two held: "
        "CURSOR_SANDBOX_LANDLOCK_STATUS reads fully_enforced or "
        "bubblewrap. Landlock can make an ignored file unreadable, so "
        "reads are confined there. This module hides a named set of "
        "credential paths on both backends, which takes away the targets "
        "worth stealing and is a weaker claim than Landlock's: a denylist "
        "leaves readable everything it does not name, so READS_CONFINED "
        "stays False and the record counts hidden paths under their own "
        "name. Network is \"Blocked by default, then opened by your network "
        "mode and sandbox.json\" against a domain allowlist "
        "(cursor.com/docs/agent/security/run-modes and "
        "cursor.com/blog/agent-sandboxing, read 2026-09-06). That axis is "
        "the one the proxy closed: egress_policy names hosts and ports the "
        "same way, and what the run was permitted to reach travels with "
        "the run. The CURSOR_SANDBOX_LANDLOCK_STATUS variable is the "
        "closest any peer here comes to Confinement.record(), and it "
        "names the backend without saying what the backend confined. The "
        "third axis runs the other way. "
        "\"On Windows, we run our Linux sandbox inside WSL2\", and the "
        "same post calls a native Windows sandbox significantly harder "
        "and claims none. The low-integrity namespace in "
        "harness/execution_input_protection.py is native and asks for no "
        "WSL2.",
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
