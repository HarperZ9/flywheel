# Primary source dive — the "AI second brain" repost

> The X repost (@Lummox_eth) points to an article by @leopardracer,
> "I Gave My Second Brain 1,500 Conversations and It Changed Everything"
> (x.com/leopardracer/status/2073340097051689327, 291K views). Read in full via
> the authenticated browser (2026-07-06). This is the REAL data behind the
> repost — the actual method, not the blurb. Captured because it is the closest
> competitor to the verified-wiki system we are building.

## The competitor's method (as stated)

- **Karpathy wiki method**: compile everything into a living wiki, **one page per
  topic**; every time an agent runs it **writes back into the wiki first**, so
  the brain "gets smarter each time." New topic -> new page, auto-created.
- **Four specialized read-agents**, each a different angle on the same corpus,
  run by **Hermes on a 6-hour cron**:
  - *Post* — reads old articles/builds, finds what made money (with live web proof).
  - *Build* — finds what you built but never shipped, says what to make next.
  - *Stoic* — reads journal + a psychology profile, coaches you.
  - *Note* — studies best posts, hands you the next one to write.
- **Ingestion sources**: Claude.ai export (Settings -> Privacy -> Export data),
  `~/.claude/projects/` Claude Code sessions, articles, X/analytics numbers.
- **Processing**: strip each raw chat to messages + real decisions (drop tool
  noise) -> one clean note per conversation -> cross-read all -> build a
  psychology profile ("how I think, what blocks me", with real quotes).
- **Privacy step**: exclude private conversations (partner chats, client work)
  by title AND body before processing. "When in doubt, drop it."
- **Human-in-the-loop, ONCE**: "show me the connections you found and let me
  approve them one by one. Don't go fully autonomous until I've reviewed one
  test run." After that it runs unattended every 6 hours.
- Storage is **Obsidian** (obsidian.md vault); automation is a Hermes agent or a
  Claude routine/cron.

## Where it is weak (our opening — accountability is the floor)

The system's whole value is agents **writing back into the wiki every 6 hours,
unattended** — and **nothing is verified**:
- No check that a written-back page is FAITHFUL to its sources. An LLM agent
  editing the vault on a cron accumulates hallucinated connections and stale
  claims with zero detection.
- No freshness/DRIFT signal: when a source changes, the derived note silently
  rots. Obsidian cannot tell you which of the 238 notes went stale.
- Connections are LLM-asserted ("these three notes are secretly one series"),
  approved once, then trusted forever — no provenance, no re-check.
- The human gate fires ONCE (the first test run), then autonomy is unbounded.

## What we already have that beats it (mapped to modules)

| Competitor feature | Our verified counterpart | Module |
|---|---|---|
| Living wiki, page per topic | verified wiki, content-sealed nodes | `harness/wiki.py` |
| Agent write-back "gets smarter" | write-back **witnessed**: MATCH/DRIFT/UNVERIFIABLE | `wiki.verify` |
| LLM-asserted connections | links **derived** from shared concepts, deterministic | `wiki.derive_links` |
| Approve connections once | continuous human-gate + receipts | forum gate (spine) |
| Exclude private chats manually | privacy boundary by construction | index `privacy_boundary` |
| Karpathy one-page-per-topic | code pages from real module graph, commit-pinned | `index_wiki` |
| Strip chat -> clean note | scout curation + intake receipt | `scout.py`, `intake.py` |
| Cron every 6 hours | flywheel spin (cache -> ~0 repeat cost) | `flywheel.py` |

## Build gaps to close (parity we do NOT yet have)

1. **Agent write-back to the wiki** with page-per-topic granularity (append vs
   rewrite), each write **witnessed** before it lands (faithful or rejected).
2. **Ingestion adapters**: `~/.claude/projects/` sessions + Claude.ai export ->
   scout catalog -> verified corpus nodes. (We already read `~/.local/share/
   opencode` this session — the same shape.)
3. **Multi-lens read agents** (Post/Build/Stoic/Note analog) over the base, each
   emitting a receipt, human-gated on new connections — not one-time.
4. **Freshness report** as a first-class UX surface: "N nodes drifted since
   capture" (the question Obsidian structurally cannot answer).
