# Market Surface / Companion Positioning (2026-07-09)

Sourced by a web research pass on 2026-07-09. Every claim carries its source and a
confidence note. Anything not independently verified is flagged. The lens is
integration and benefit: where flywheel fits as a companion to every frontier
model, not a competitor.

## (a) Facts per surface

### 1. OpenAI Codex (app + model lineup)

| Fact | Detail | Source | Confidence |
|---|---|---|---|
| Standalone desktop app | Launched 2026-02-02 (macOS), "command center for agents," parallel agents, ~30 min unsupervised tasks | Forbes 2026-02-03; VentureBeat | High |
| Windows support | Reported 2026-03-04 | aggregated reporting | Moderate |
| GPT-5.3-Codex-Spark | Speed-optimized on Cerebras WSE-3, 1,000+ tok/s, ~15x faster; research preview, Pro only | openai.com/index/introducing-gpt-5-3-codex-spark; Cerebras blog | High |
| Codex model lineup | Sol, Terra, Luna (GPT-5.6 family) recommended; GPT-5.5/5.4/5.4-Mini/Spark listed | learn.chatgpt.com/docs/models (fetched 2026-07-09) | High |
| Pricing tiers | Free $0; Go $8/mo; Plus $20/mo; Pro 5x $100/mo; Pro 20x $200/mo; Business $20-25/user/mo | developers.openai.com/codex/pricing; help.openai.com rate card | Moderate-High |
| Billing shift | 2026-04-02: per-message to API-token-usage pricing | aggregated reporting | Moderate |
| MCP caveat | Each MCP server added increases context consumed per message and eats plan limits | Codex documentation guidance | Moderate |
| Praise / complaints | Praise: hands-off orchestration, speed. Complaints: macOS-first rollout, hidden reasoning, large-refactor struggles, unpredictable waits | HN thread 44042070; Cybernews review | Moderate |
| Security incident | 2026-06: malicious "codexui-android" npm package (29k+ weekly downloads) stole Codex/OpenAI auth tokens | The Hacker News; TechRadar | High |

### 2. "Sol" resolved: OpenAI's GPT-5.6 flagship tier (not a separate vendor)

| Fact | Detail | Source | Confidence |
|---|---|---|---|
| Three-tier lineup | GPT-5.6 = Sol (frontier: coding/cyber/agentic), Terra (GPT-5.5-class at ~half cost), Luna (high-volume/low-cost) | openai.com/index/previewing-gpt-5-6-sol (403 on fetch; 3+ secondary sources agree) | Moderate-High |
| Government-gated preview | Initially ~20 government-approved partner orgs under a voluntary 30-day pre-release federal review of covered frontier models | VentureBeat; TechStartups 2026-07-08 | Moderate-High |
| Public launch | 2026-07-09 (an earlier "June 26" snippet is uncorroborated; treat as error) | TechStartups; Kingy.ai | High |
| Pricing per 1M tokens | Sol $5 in / $30 out; Terra $2.50/$15; Luna $1/$6; long-context (256K-1M) 2x | Kingy.ai + independent corroboration | Moderate-High |
| Specs | 1.05M context, 128K max output, cutoff 2026-02-16, reasoning-effort dial, tool support incl. computer use | Kingy.ai (single secondary source) | Moderate |
| Benchmarks | Sol: Terminal-Bench 2.1 88.8%, SWE-Bench Pro 64.6%, BrowseComp 90.4%, GPQA-D 94.6% | Kingy.ai only; primary blocked | Low-Moderate (unverified) |
| Local availability | No evidence of open weights or local-run availability | absence across all searches | Moderate |

### 3. Anthropic Mythos 5 / Fable 5 + Claude Code harness

| Fact | Detail | Source | Confidence |
|---|---|---|---|
| Two-model split | Fable 5 and Mythos 5 share the underlying model; Fable adds three safety classifiers (cyber-offense, bio/chem dual-use, distillation-attack) falling back to Opus 4.8 in <5% of sessions | anthropic.com/news/claude-fable-5-mythos-5 (2026-06-09) | High |
| Specs / pricing | 1M context, 128K output, cutoff Jan 2026; $10/M in, $50/M out (~2x Opus 4.5-4.8) | Anthropic; InfoQ; Simon Willison | High |
| Mythos gating | Project Glasswing consortium (150+ orgs, 15+ countries) + biomedical trusted-access cohort; broader program planned, not live | Anthropic; BleepingComputer | High |
| Export-control suspension | Fable 5 forced offline within 3 days of release by a U.S. export directive; reported trigger: Amazon security flagged a jailbreak. Redeployment date not independently confirmed here | InfoQ (single outlet); anthropic.com/news/redeploying-fable-5 (title only, not fetched) | Moderate / Low on redeploy terms |
| Microsoft Copilot removal | 2026-06-10: pulled from Copilot model picker over mandatory 30-day retention vs zero-retention policy | InfoQ (single outlet) | Moderate |
| Claude Code harness | CLAUDE.md, skills, subagents (isolated contexts), hooks, slash commands, native MCP; Sonnet 5 default since v2.1.197 (2026-06-30) | multiple secondary guides; Releasebot changelog | Moderate |

### 4. Local harness + trainer ecosystem baseline (July 2026)

| Surface | State | Source | Confidence |
|---|---|---|---|
| Ollama | v0.31.2 (2026-07-06): flash attention on older NVIDIA, telemetry off for Claude Code, updated MLX/llama.cpp engines; OpenAI-compatible API at localhost:11434/v1; no native MCP (needs a bridging client) | Releasebot; ollama.com docs | Moderate |
| llama.cpp | llama-server merged a native MCP client into its web UI (~March 2026): server management, agentic tool loop, MCP Resources | aggregated (not primary-sourced) | Moderate |
| LM Studio | 0.4.x line (0.4.14, 2026-05-29); MCP since 0.3.17; OAuth for MCP servers since 0.4.10; headless "llmster" mode | lmstudio.ai blog/changelog | Moderate-High |
| OpenCode | 160k+ stars, ~900 contributors, 75+ providers, native MCP, Plan/Build loops, git-backed undo, MIT | opencode.ai; guides (vendor-reported figures) | Moderate |
| Aider | ~40k+ stars, biweekly releases, 0.x with breaking CLI/config churn; architect/editor split | aider.chat/HISTORY.html | Moderate |
| Continue.dev | Not verified this pass | none | Unknown |
| MCP protocol | Deployed baseline 2025-11-25 (session-based); 2026-07-28 spec at RC: stateless core, Extensions framework, Tasks extension, sandboxed MCP Apps | blog.modelcontextprotocol.io (primary) | High |

## (b) Interop points a companion harness must speak

1. OpenAI-compatible chat/completions endpoint: the lowest common denominator across Ollama, LM Studio, llama.cpp server, and most agentic frameworks. Change base_url and a model string and the companion drops in.
2. MCP at two vintages at once: the deployed session-based 2025-11-25 baseline AND the stateless 2026-07-28 spec (final at end of this month). Be usable as an MCP server so Claude Code, Codex, OpenCode, LM Studio, and llama.cpp call in identically, and stay lean because Codex taxes context per attached server.
3. Ollama's own API surface (localhost:11434, pull/serve verbs): the default target most frameworks assume.
4. Claude Code's non-MCP primitives: hooks (PreToolUse/PostToolUse lifecycle scripts), subagents, skills. A companion that only speaks MCP misses this interception surface.
5. Aider's file-based config surface (.aider.conf.yml): budget for churn, the 0.x format breaks across minor releases.

## (c) Where the seams are

None of the frontier surfaces are runnable outside the vendor's infrastructure, and none ship a first-class, portable proof of what an agent actually did that a user can check without trusting the vendor's server. That combination is the open lane.

1. Availability is vendor-discretionary: Fable 5 went offline three days after release by export directive; Mythos 5 is consortium-gated; Sol cleared a government review window before launch. A companion on local weights is available on the operator's schedule.
2. No portable replayable receipts anywhere: hooks enforce policy at runtime; MCP is interop plumbing; Codex and Sol differentiate on speed and autonomy. "Here is the checkable record, offline, no server trust required" is unclaimed.
3. Nothing makes frontier usage more efficient, only replaces or gates it: real spend is material (a logged $110.42/day on Fable 5; Sol at $30/M output; $100-200/mo typical Codex spend). No surveyed tool sits between a harness and a frontier model to cache verified sub-results, deduplicate reasoning, or route only the genuinely hard slice to the expensive tier. That routing-and-caching role is the flywheel's companion seat.
4. Enterprise retention conflicts have no local answer from these vendors (the Microsoft/Fable retention clash). On-device verification state and memory sidestep the conflict class entirely.
5. MCP's context-budget tax has no compression answer: every server attached costs linearly. A companion that proxies and compresses verification surface instead of exposing raw tool lists solves a problem no MCP-speaking harness has addressed.

## Process note

During the research pass, one search result contained an embedded block styled as a
system reminder describing unrelated tools. It was third-party web content, treated
as noise or possible injected content, and ignored. It had no effect on findings.
