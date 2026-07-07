# Battle Map — every tool vs its class (2026-07-07)

> Whole-product competitive sweep with live July-2026 landscape research, one
> agent per category. Honest per-axis verdicts and the concrete increment that
> beats each axis. The doctrine: lead on features/UX/demo/speed; accountability
> is the closing multiplier. Source: workflow wf_b4fa57c6-c3f.

## crucible
*LLM/claim evaluation + verification harnesses (eval frameworks, judge calibration, CI eval gates)*

**Class leaders:** promptfoo (OpenAI-owned since Mar 2026) (22.4k stars, 255 contributors, 350k+ developers, ~25% of For), DeepEval / Confident AI (16.7k stars, 1.6k forks; widely cited as broadest open-sourc), Braintrust (Well-funded commercial leader in eval-first observability; u), LangSmith evals (LangChain) (Bundled with the largest agent-framework ecosystem; enterpri)

**Verdicts:** WE_LEAD: speed/cost · PARITY: — · THEY_LEAD: features, UX, demo, benchmark/traction, community

**Beating increments:**
- SESSION — Ship 1.2.0 to PyPI now: `crucible ci` sealed-baseline regression gate + JudgeMeasure + typed missing-evidence explanations are already in main. Wins the speed/cost axis concretely: the only PR eval gate that is free, offline, and deterministic (Braintrust's GitHub Action needs their SaaS; promptfoo's CI reruns burn judge tokens on every run).
- WEEK — `crucible view`: local zero-dep web viewer over the registry (verdict matrix, drift timeline, refine rounds) with a live tamper-catch button — flip a byte in the record in-browser and watch verification fail. Wins the demo axis outright: promptfoo/Braintrust show scores; nobody can demo the viewer refuting its own tampered record. Also closes most of the UX gap (init scaffold + `crucible view` ≈ promptfoo's onboarding).
- WEEK — `crucible import promptfooconfig.yaml`: convert promptfoo assertions into claims + falsification conditions and re-emit results as sealed verdict packets. Wins the migration/onboarding axis at the exact moment the OpenAI Evals sunset is funneling thousands of users into config rewrites — one command turns their existing suite into a re-checkable registry.
- MONTH — Judge calibration with sealed human-label packs: LangSmith Align Evals' workflow (grade a sample, iterate the judge prompt against human scores) but the alignment score itself recomputes from a content-addressed pack, so a calibrated judge ships WITH the evidence it was calibrated. Exceeds their best feature on its own turf: their alignment number is a dashboard artifact, ours is portable and re-derivable by the team that receives the judge.
- MONTH — GitHub Action + PR-comment matrix around `crucible ci` with the baseline sealed into the repo: regression = claim losing standing, hand-edited baselines rejected on load, comment cells reference assessment seals. Exceeds Braintrust's PR gate on the axis that matters in CI — a reviewer can re-derive every cell locally without an account, a network call, or a token.

**Invented niche:** Benchmark-claim escrow: sealed, third-party-re-runnable verdict packets attached to public AI performance claims — README badges, model cards, leaderboard rows, vendor "our agent scores X on Y" marketing. Leaderboards (HELM, LMSYS) rank and observability platforms trace, but no incumbent escrows the claim itself so that anyone downstream can recompute the verdict offline from the packet. crucible's organs compose into it directly: thesis = the published claim + falsification condition, gather supplies source receipts for the eval inputs, index supplies the repo/commit context the claim was made against, the cleanroom bundle IS the escrow artifact, and `crucible review` is the third-party check. Concrete first wedge: a `crucible badge` that renders a shields.io-style badge whose linked packet re-derives the number it displays.

**Accountability multiplier (last):** Every verdict is a pure function of a sealed record — the one harness where an auditor, competitor, or CI bot can recompute the result without trusting the team that ran it.

## telos-agent
*Full AI agent product: terminal/desktop agent that does work end-to-end (LLM tool loop, TUI, sessions, skills, native computer control)*

**Class leaders:** Claude Code (Anthropic) (Default frontier choice; proprietary, paid subscription; wee), OpenCode (140K-170K stars reported, 850 contributors, 11K commits, cla), Devin / Devin Desktop (Cognition) (Reported $25B valuation talks (Apr 2026), ARR doubled post-W), OpenHands (~70K stars; active SDK paper + benchmarks org; strong resear)

**Verdicts:** WE_LEAD: native computer control · PARITY: — · THEY_LEAD: features, UX, demo, speed/cost, benchmark/traction, community

**Beating increments:**
- WEEK - `telos agent` entry binary (features axis, table stakes that unlock every other row): an LLM tool loop over the existing 69-tool catalog with model-foundry routing (Anthropic/OpenAI/local), permission gates reusing the admission machinery, headless -p mode, and session save/load in the existing room/loop-ledger state. clawcodex proved one dev can ship this loop; ours starts with a 69-tool body already built.
- SESSION-to-WEEK - the concurrent-desktop demo (demo axis, beats Open Interpreter/Manus): a 90-second recorded demo where the agent drives a native Windows app plus browser via UIA/CDP synthetic events WHILE the operator visibly keeps typing in another window, ending with the browser-evidence packet replayed. No competitor can film this: cloud agents don't have your desktop, computer-use agents freeze your hands.
- WEEK - persistent parallel sessions (UX axis, meets then beats OpenCode's signature): client/server split so sessions survive terminal death and SSH drops, parallel rooms over existing room state - exceeding OpenCode because every reconnected session replays from its ledger instead of a scrollback.
- WEEK - ACP adapter (community/distribution axis): implement Cognition's open Agent Client Protocol so `telos agent` runs inside Devin Desktop and every ACP editor - distribution through the $25B incumbent's own front door, the same slot Codex/OpenCode already occupy.
- MONTH - published Terminal-Bench 2.1 + SWE-bench Verified runs with cost-per-resolved-task (benchmark + cost axes): route through a cheap open-weight model and a frontier model via model-foundry; first target is beating clawcodex's 58.2% SWE-bench Verified, and leading the one number nobody publishes - dollars per resolved task, receipt attached per task.

**Invented niche:** The concurrent-desktop agent: a second pair of hands on YOUR logged-in workstation - real native apps and browser sessions with your actual auth and state, driven by synthetic UIA/CDP events beside you while your cursor and keyboard stay free, every action leaving a replayable evidence packet. Cloud agents (Manus, Devin, OpenHands) work in VMs without your desktop; local computer-use agents (Open Interpreter, computer-use) seize your input to work; nobody occupies the both-at-once slot, and telos's native-control + room-state + browser-evidence organs are already the three parts it composes from.

**Accountability multiplier (last):** Same agent, same tools, one difference at the end: every competitor's action trail is a log you must trust, ours is a proof packet whose verifier recomputes the claims and can say DRIFT or UNVERIFIABLE - re-checkable by someone who doesn't trust us.

## forum
*multi-agent orchestration frameworks*

**Class leaders:** LangGraph (LangChain) (~34.5M monthly PyPI downloads (per 2026 third-party comparis), CrewAI + CrewAI AMP (~45k GitHub stars (largest dedicated-framework community), ~), Microsoft Agent Framework (AutoGen+Semantic Kernel successor; AG2 fork) (AutoGen repo ~45k+ stars redirecting mindshare to MAF; Micro), OpenAI Agents SDK (+AgentKit) (26.4k+ stars, 4k forks (May 2026); one of the three most-ado)

**Verdicts:** WE_LEAD: — · PARITY: demo · THEY_LEAD: features, UX, benchmark, community

**Beating increments:**
- Live run cockpit (one session): stdlib ANSI terminal view that streams waves, tier escalations, gate prompts, and budget burn as a run executes, reusing the ledger event stream. Wins UX for terminal-native operators: LangGraph Studio and CrewAI AMP both require their platform; nobody ships a zero-dep, no-account live cockpit.
- Published head-to-head bench (one week): thin adapters running the same 5-task suite through forum, LangGraph, CrewAI, and OpenAI Agents SDK, publishing tokens/latency/model-calls per task in the repo with a rerun script. Wins speed+cost by converting the zero-model-call routing edge (rivals spend an LLM supervisor call per route) into a number instead of a claim, and puts forum into the benchmark conversation it is currently absent from.
- Zero-rewrite import (one week): `forum import` for CrewAI YAML crews and simple LangGraph supervisor graphs, executing them under forum so an existing crew immediately gains crash-safe resume, gates with deadlines, and budgets it does not have at home. Wins features/interop and gives switchers a no-cost trial path.
- Single-file replay studio (one month): grow examples/forum-demo.html into an offline HTML studio that opens any ledger JSONL: dependency-graph view, wave timeline, run-vs-run diff, in-browser deep verify. Wins demo: LangGraph Studio needs a server and account, ours opens from a double-clicked file.
- Streaming + A2A executor (one month): SSE streaming on the stdlib daemon and an A2A-speaking executor adapter so forum agents can join Google/Microsoft A2A meshes as peers. Closes the two loudest feature gaps and contests ADK's headline interop axis on neutral ground.

**Invented niche:** Framework-neutral agent flight recorder: an ingest seam that converts LangSmith/OTel/AgentOps traces into forum's hash-chained ledger format, then gives verify, deterministic replay, causal-chain, capsule, and run-room over runs from ANY framework. Observability vendors ship dashboards over mutable traces; no incumbent ships tamper-evident, replayable, cross-framework post-incident forensics for agent fleets. It composes organs forum already has (ledger, capsules, rooms, the crucible VerifierProvider seam) and sells into every rival's install base instead of against it.

**Accountability multiplier (last):** Every feature above lands in the same hash-chained, content-addressed ledger, so any run, native or imported, can be re-verified, replayed, and challenged: the receipt is the floor under the whole surface, never the pitch.

## crucible
*Local-model training + verified-inference harnesses (dataset -> train -> eval -> serve)*

**Class leaders:** LLaMA-Factory (~68.4K GitHub stars (largest in category, March 2026 count);), Unsloth (~53.9K stars, crossed 50K Feb 2026; the default answer for s), Axolotl (~11.4K stars; strong cloud-provider partnerships (Runpod, Mo), torchtune (v0.6.1 on PyPI; ~5K stars (moderate confidence); ecosystem a)

**Verdicts:** WE_LEAD: — · PARITY: — · THEY_LEAD: features, UX, demo, speed, cost, benchmark, community

**Beating increments:**
- DEMO axis (session-to-week, gated on the operator unblocking the llama.cpp build): ship the GGUF+Ollama artifact from the ready ship_gguf.sh pipeline — `ollama pull` a 14B whose Modelfile links the dataset receipt, eval receipts, and quantize hash manifest, with a clean-machine falsifier that re-derives the chain. Exceeds Ollama's own library demo on one property no listed model has: pull-and-reproduce provenance, not just pull-and-run.
- BENCHMARK axis (week, needs the hard-set lane finished to 100): run the curated hard set through the existing 13-provider registry — our gated loop vs stock 14B vs an Unsloth-tuned equivalent vs a frontier single shot, matched budget, published whatever it says including zero. Exceeds lm-eval-harness on eval integrity: every task passed oracle_can_fail + leak + behavioral-dedup admission gates, and every score row carries a re-runnable receipt; no incumbent publishes gate-audited task sets.
- UX axis (week): one command, `local-model run <corpus>` — dataset -> shards -> QLoRA -> eval -> package as resumable stages with a receipt at each boundary, plus a stranger-runnable Colab/notebook of the gated loop. Matches LLaMA-Factory's zero-code bar for the CPT slice and exceeds it on the one thing YAML configs don't give: byte-level re-derivability of what actually ran.
- SPEED/COST axis (month, compose don't absorb): adopt Unsloth's open kernels as an optional trainer backend behind the same manifest/receipt seal, closing the 2-5x throughput gap while keeping the accept path oracle-only. Honest framing: this reaches parity on speed and keeps our lead on reproducibility; exceeding Unsloth on raw kernels is not a realistic month goal.
- FEATURES axis (month): promote the retroactive dataset receipt to seal-at-pack-time for all future runs and extend it through GGUF quantization, giving the only train stack whose provenance chain reaches the served artifact — a feature none of LLaMA-Factory/Unsloth/Axolotl ships in any form as of July 2026.

**Invented niche:** The provenance-complete model artifact: a pullable GGUF whose Modelfile carries a hash-linked dataset->train->eval->quantize receipt chain that a clean machine re-derives end-to-end. Adjacent to Ollama's library and HF model cards, and empty: model cards are prose, Modelfiles are configs, Axolotl YAMLs are intent-not-evidence, and the 2026 proof-carrying/zkML research lane (arXiv 2605.16407, TOPLOC) verifies pipelines or serving, never the train-to-artifact chain. We already own every organ it composes: dataset/receipt.py, envelope/chain, task_curator eval lanes, ship_gguf.sh hash manifest.

**Accountability multiplier (last):** Every axis win above ships with the one thing no competitor in this category emits: a receipt a third party re-runs to reproduce the verdict — the closing multiplier, never the pitch.

## index
*Workspace intelligence / codebase maps / agent context management (second-brain-for-code)*

**Class leaders:** DeepWiki (Cognition / Devin) (Launched Apr 2025, now the default first-contact surface for), CodeGraph (colbymchenry/codegraph) (47.4k GitHub stars within ~5 months of its Jan 2026 launch —), GitNexus (~1.2k to 42k stars between Apr and Jun 2026; production-audi), Sourcegraph 7.x (The big-code enterprise incumbent; 7.0 shipped Feb 2026 with)

**Verdicts:** WE_LEAD: speed / cost · PARITY: features · THEY_LEAD: UX, demo, benchmark, community

**Beating increments:**
- DEMO (one session): publish a GitHub Pages gallery of live artifacts — workbench, verified wiki, atlas, and lens pre-generated for index itself plus 2-3 famous OSS repos (e.g. FastAPI, requests) — linked at the top of the README with a 30-second GIF of the Ctrl-K palette and budget slider. Beats CodeGraph/GitNexus (README-screenshot demos) outright and closes most of the gap to deepwiki.com for zero-install first contact, since our artifacts are static HTML and cost nothing to host.
- UX (one week): graph-answers in the palette — teach the workbench command palette to answer the structured questions agents and reviewers actually ask ('who imports X', 'path from A to B', 'what breaks if this file changes') sub-second, offline, from the already-embedded graph, each answer carrying its file:line evidence. Exceeds DeepWiki Fast mode on latency and cost (0 tokens, works air-gapped) for the structural-question class, which is most of them.
- FEATURES (one week): `index watch` — incremental auto-resync on file change feeding the MCP server, with every sync stamped by the existing freshness certificate. Matches CodeGraph's headline 'auto syncs on code changes' and exceeds it: theirs syncs silently, ours can prove to the agent that the graph it is reading is FRESH or name exactly what went STALE.
- BENCHMARK (one month): publish the category's only fully reproducible token-economics study — Claude Code with index MCP vs raw grep vs CodeGraph vs GitNexus on 3 public repos, harness and raw logs in-repo, wired through `index bench`. The market leaders won 40k+ stars on 70-88% reduction claims nobody can re-run; a number anyone can reproduce is both a benchmark entry and a demo of the thesis.
- FEATURES (one month): TypeScript/JavaScript symbol layer (zero-dep parser) extending symbol pages, `index symbols`, and the LSP beyond Python — the single biggest surface gap vs tree-sitter-based rivals, targeted at the two languages agent-heavy repos actually use most.

**Invented niche:** The agent-context flight recorder: every context envelope served to an agent over MCP is persisted as a hash-pinned, budget-annotated, failure-coded artifact, and the context lens replays it after the fact — so when an agent run goes wrong, you open the exact envelope it had, see what the budget dropped and why, and re-derive it against today's tree. Mem0 stores memories, LangSmith traces prompts, Cursor hides retrieval entirely, Sourcegraph serves context and forgets it; nobody ships post-hoc, re-derivable replay of what an agent's context actually contained. Every organ needed (envelope, lens, freshness, invalidate, MCP) already exists in index today — this is composition, not new research.

**Accountability multiplier (last):** Every rival graph goes stale silently; every index artifact — wiki page, edge, envelope — carries the command that re-derives it, and `--verify` returns DRIFT with an exit code CI can gate on.

## gather
*Web research intake / scraping / crawling engines for AI agents (July 2026)*

**Class leaders:** Firecrawl (Most prominent hosted scraping API; GitHub stars in the tens), browser-use (~103k GitHub stars (July 2026, moderate confidence); $17M se), Crawl4AI (50k+ stars, billed as the most-starred crawler on GitHub (mo), Crawlee (Apify) (~15-17k stars JS + growing Python port (moderate confidence))

**Verdicts:** WE_LEAD: — · PARITY: cost · THEY_LEAD: features, UX, demo, speed, benchmark/traction, community

**Beating increments:**
- MONITORS THAT PROVE (features axis, beats Firecrawl monitors; ~1 week): ship `gather monitor` — scheduled re-fetch of a stored page set, diffed against the corpus with track's typed MATCH/RELOCATED/DRIFT/GONE verdicts at element level plus schema_extract field-level diffs, history folded into the existing hash chain. Firecrawl's 2026 monitors use an LLM to judge whether a change is meaningful; gather returns a typed, re-derivable verdict of exactly which node changed and how. That is strictly more precise than the incumbent feature.
- IN-BROWSER LIVE PLAYGROUND (demo axis, beats every OSS competitor; ~1 session-to-week): the zero-dep stdlib core is uniquely Pyodide-friendly — ship a static page (hosted on the portfolio site) where a user pastes HTML or a URL and watches markdown + per-block receipts render live, then clicks 'tamper' and sees verification fail. No competitor's engine runs in the visitor's browser tab; Firecrawl's playground needs their servers, Crawl4AI/Scrapling have none. Add a CLI GIF to the README the same session.
- PUBLISHED APPLES-TO-APPLES BENCHMARK + selectolax fast path (speed + benchmark axes; ~1 week): extend examples/bench.py into a versioned benchmark harness that runs gather (stdlib and [fast]), Scrapling, Crawl4AI, and firecrawl's OSS engine on the same fixtures and publishes the full table including where gather loses. Add selectolax as a second fast-parse backend targeting parse/select in the low-millisecond range to contest Scrapling's ~2ms claim directly. Nobody in the category publishes a benchmark that includes their own losses; being the referee wins the axis.
- REPLAYABLE INTERACT SESSIONS (features axis vs browser-use/Firecrawl /interact; ~2-4 weeks, month-honest): grow the existing Playwright backend into `gather interact` — scripted click/fill/scroll/screenshot steps where each action and the resulting DOM state hash are appended to an action ledger. Not an LLM agent (out of scope for one increment) but the only interaction session in the category that can be re-verified step by step; targets the CI/regression-scraping use case browser-use is too nondeterministic for.
- KEYLESS ONE-LINER FIRST TOUCH (UX axis, closes the Jina/Firecrawl gap for the local class; ~1 session): document and test `uvx gather-engine extract <url>` / `pipx run` as the zero-install first touch, add `gather quickstart` that runs the offline proof end-to-end in one command, and ship the MCP server config as a one-line paste for Claude/Cursor. Matches Firecrawl's 2026 keyless-MCP move without a hosted service.

**Invented niche:** Research change-custody: a local, re-verifiable record of what a set of web sources said over time, queryable at element level. Compose corpus (content-addressed snapshots) + track (typed drift verdicts) + monitor (increment 1) + scholar (citation edges) so a user can cite a claim to a specific element in a specific witnessed snapshot and later prove whether the source still says it, with a hash chain a third party re-derives. No incumbent exists: Firecrawl monitors are hosted and LLM-judged (unprovable), archive.org snapshots are not element-diffable, Scrapling relocates elements but keeps no custody history, Exa/Tavily return answers with no snapshot at all. Natural buyers: fact-checkers, legal/compliance teams watching terms-of-service and regulatory pages, and researchers who must show their web citations have not rotted. Feeds directly into crucible (judgment over drift) and index (graph over the corpus).

**Accountability multiplier (last):** Every feature above already emits a re-derivable receipt (per-block hashes, chained crawl/stream ledgers, an enforced fetched-vs-inferred boundary) — the one property no competitor can retrofit, and it comes free with the most capable choice.
