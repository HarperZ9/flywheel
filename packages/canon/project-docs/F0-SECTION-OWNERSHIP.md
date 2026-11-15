# F0 — the section-ownership contract (ruling 1)

The renderer is a later phase, but the contract it must honor is fixed now,
because it decides what a bidirectional sync is allowed to touch. Ruling 1: in
every managed file, canon owns exactly one delimited region; everything outside
that region is hand-authored and is never read, rewritten, or moved by canon.

## Why this is F0

canon writes back to the same files a human edits. Without a hard ownership
line, a render would either clobber hand-written prose or a hand-edit would
silently revert a rendered block. The record schema is meaningless in practice
until this line is drawn, so it is part of the foundation, not the renderer.

## The managed region

Each managed file carries one canon-owned region between two markers:

```
<!-- canon:begin scope=<global|workspace> -->
   ... rendered from records; overwritten wholesale on every render ...
<!-- canon:end -->
```

Rules:
- **Inside the markers is canon's.** The renderer replaces the entire region on
  each render from the effective record set for that file's scope. A hand-edit
  inside the region is not durable and will be overwritten.
- **Outside the markers is the human's.** canon never parses, reorders, or emits
  a single byte outside the region. A file may have hand-authored prose before
  and after the region; both survive every render untouched.
- **One region per file.** Exactly one begin/end pair. A file with zero markers
  is off-limits entirely (canon writes nothing). A file with more than one pair
  is a contract violation the renderer refuses.
- **Read-back is region-scoped.** When canon ingests a managed file (the reverse
  direction), it reads records only from inside the region. Hand-authored prose
  outside is not turned into records and cannot leak into the canonical set.

## The render-scope allow-list

Only these files carry a canon-owned region. The renderer and every export leg
write only to this fixed list; the R1 write-surface assertion and the R2/M2
scope-guard fail any write outside it.

- `~/.claude/CLAUDE.md` — global
- `<workspace>/CLAUDE.md` — workspace
- `<workspace>/AGENTS.md` — workspace
- `GEMINI.md` — global and workspace
- `SOUL.md` — global and workspace (a projection of the block set, not a second
  persona canon; see the decisions doc, ruling b)
- the Obsidian vault mirror — global and workspace
- the M2 export configs: OpenCode `AGENTS.md` + `opencode.jsonc`; the Hermes
  `SOUL.md` / `MEMORY.md` / `USER.md` leg; the ChatGPT paste bundle

The ~90 per-repo `CLAUDE.md` / `AGENTS.md` files are **not** on this list. They
stay hand-authored, keeping every project repo self-contained. No record is
scoped to a repo, and no render ever touches one.

## F0 scope

F0 fixes the contract and the allow-list; it writes no markers and renders no
file. The marker parser, the region-replace, and the scope-guard that enforces
this list are the R-family phases. What F0 guarantees is that the schema already
carries the one field this contract turns on — `scope` — with exactly the two
values the allow-list ranges over.
