# The Import Queue — the tool landscape, live-fetched 2026-07-14

Method: eight read-only agents over the official changelogs and docs of the
current tool landscape (Cursor, Copilot + Codex, Claude Code, Devin/Amp/
Jules/Antigravity, Zed/JetBrains/Warp, Cline/Roo/OpenCode/Aider, Replit/
Lovable/Bolt/v0, plus a new-entrants scout), each feature carrying its
shipped date and fetched URL, followed by a freshness critic whose findings
are embedded below rather than hidden. Vendor performance numbers are
claims throughout and never travel further than this sentence.

## The one seam, everywhere

Every serious tool converged on the same shapes this quarter — approval
gates, activity logs, environment pinning, session snapshots, effort
dials, auto-routing — and **not one of them emits a re-checkable receipt**
for the decision the shape exists to make. Cursor's approval classifier is
opaque; Copilot's auto-routing is a black box; Devin's QA evidence is an
edited recording; Lovable's activity view is prose; OpenCode's revert is
silent history rewriting. The import strategy is therefore uniform: take
the capability, add the receipt it lacks.

## Import queue, ordered by leverage over cost

| # | Import | Source pattern | Receipt Flywheel adds |
|---|---|---|---|
| 1 | **Gate receipts** | Cursor auto-review classifier, Copilot approval tiers, Claude Code auto-mode denials, v0 grouped approvals | every allow/deny journaled with the rule that fired; the ledger, not a toggle, is the authority |
| 2 | **Environment pinning** | Cursor env-as-code, Amp orbs | runtime identity (python, platform, machine) inside every run doc so acceptance re-runs in a named environment |
| 3 | **Import adapters** | Codex one-step Claude Code migration | read CLAUDE.md / .cursor rules / AGENTS.md into Flywheel profiles with a mapping manifest: what mapped, what dropped, honest nulls kept |
| 4 | **Effort dial** | Amp's Dial, Bugbot effort levels | one knob mapping to candidates and verification passes, stamped into the receipt so two efforts are comparable |
| 5 | **Routing receipts** | Copilot CLI auto model selection, Claude Code fallback chains, OpenCode per-prompt models | candidate set, signals, chosen model, and why — auditable and replayable |
| 6 | **Tool-call rescue loop** | Forge (new entrant) validate/rescue/retry | malformed tool calls repaired under witness: original, transform, retries, final — never silently fixed |
| 7 | **Session snapshots with state hashes** | OpenCode revert, Cline queue-and-edit | checkpoint = transcript hash + workspace hash; revert is a receipted operation |
| 8 | **Deterministic web snapshots** | Kage byte-identical archives | gather's cited sources frozen content-addressed; the hash IS the receipt, offline forever |
| 9 | **CPU-only hybrid retrieval** | Semble (BM25 + static embeddings + RRF) | index-layer retrieval mode; the token-savings claim re-measured locally before it is ever repeated |
| 10 | **Element-anchored annotations** | v0 annotations mode | visual change requests bound to before/after screenshot hashes |

## Honest gaps (the critic's findings, kept)

- Devin Desktop (Cognition's IDE line, v3.2 July 2026), CodeRabbit/Qodo/
  Graphite (dedicated review tools), OpenHands/Goose/Continue (open agents),
  and Kiro/Factory Droid went unsurveyed — a follow-up sweep owes them slots.
- Several bucket picks breached the 90-day window (Devin Feb/Mar items,
  Jules Feb, Replit Mar) and are architecture context, not news.
- Antigravity 2.0's detail rests on coverage, not the JS-walled official
  page: moderate confidence, marked.
- New-entrant dates are Show-HN publicity dates, not release dates; Colibri
  in particular is demo-grade until independently reproduced.

Sources: per-feature URLs live in the sweep artifacts (workflow
wf_923e57b7-f66 journal); the load-bearing ones were re-verified by the
critic pass.
