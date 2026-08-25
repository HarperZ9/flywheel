# The Flywheel platform charter: accountability is the floor, not the ceiling

Date: 2026-08-24
Status: charter + gap map. Every claim of "exists" cites a module or
route; every "missing" names the workstream that closes it.

## The thesis, stated whole

Accountability â€” receipts, verification, no model on the accept path â€”
is the floor every other capability stands on. It is not the product.
The product is an environment where superintelligence is in everyone's
hands: a harness that is simultaneously the IDE, the coding agent, the
automated agent, the evaluation lab, the training pipeline, and the
platform any domain builds on. The verification layer is what lets that
environment be trusted by a junior dev, a hospital, a bank, and a
design studio alike â€” and then it gets out of the way.

## The inventory: what exists today (verified)

| Pillar | Exists as | Where |
|---|---|---|
| IDE | 30-destination desktop, 24 views, installer, a11y, recovery | `desktop/` |
| Coding harness | agent loop, tools, write/exec permissions, per-step tool receipts | `harness/local_agent.py`, `/api/agent` |
| Model freedom | multi-provider ladder (Claude, ox-alpha, DeepSeek, GLM, Gemini, local), BYOK | `harness/endpoints.py` |
| Accountability floor | receipts, Merkle transparency log, disproof gate, certificates, exact grants | `harness/receipts.py`, `transparency_log.py`, `operation_grants.py` |
| Evaluation | private verified benchmarks, verified frontier, regression loop from traces | `verified_bench.py`, `trace_bench.py` |
| Parallel agents | role-prompted swarms, per-child receipts, quorum fan-in, `agent.completed` hooks | `subagents.py`, `/api/subagents` |
| Improvement loop | traces â†’ task sets â†’ regression report | `trace_bench.py` |
| Planning | forge â†’ PRP â†’ gated plan runs | `plan_run_contract.py` |
| Memory | fold index, recall, durable notes | `memory_api.py` |
| Lessons | curriculum, teach-back, admit/retire | `lessons*` |
| Creative | studio poster/brandkit/sound/graph, telos kernels | `studio*` |
| Local models | QLoRA 14B CPT trained, serve tier, Train lane | `train*`, Layer A |
| Extension platform | capability-gated packs, MCP plugins, marketplace | `domain_pack.py`, `plugins.py` |

## The gap map: what "surpass every tool" requires next

Ordered by leverage. Each row is a buildable workstream with the
competitor it answers.

1. **Receipt-to-reward training bridge** â€” the keystone. Verified bench
   outcomes and gate passes are exactly the verifiable reward signal RL
   needs. Build the dataset builder: receipts â†’ (prompt, proposal,
   reward) pairs â†’ GRPO/QLoRA-ready JSONL for the local model. Answers
   Prime Intellect's training loop with one they cannot match: rewards
   minted from cryptographic evidence, on-device, no cloud. "Train
   local models" becomes "your harness teaches your model on proofs."
2. **Subagents + parallel sessions (SHIPPED 2026-08-24)** -- answers
    Claude Code's background agents. One goal fans out to N children
    under fixed roles whose authority is enforced at registration;
    every child carries a sealed spec and is sealed a run receipt;
    fan-in is deterministic quorum arithmetic that fires the
    accountable hooks `agent.completed` event. Swarms reattach after a
    gateway restart, cancel cleanly by pid, and render on the desktop
    as the Swarms destination. See
    `project-docs/features/2026-08-24-subagent-swarms.md`.
3. **Hooks with teeth** â€” answers Claude Code's hooks. Event-triggered
   automations (file change, git event, journey stage) where every hook
   run is itself receipted and a failing hook blocks the action
   fail-closed. Nobody's hooks are accountable.
4. **PM surface (FIRST LIGHT SHIPPED 2026-08-24; desktop 2026-08-25)**
    -- answers the manager use case. `GET /api/pm/roadmap` builds the
    one-page view: goals (swarm receipts), decomposed child work with
    per-child verification status, a verification floor of bound
    skills, and its own does-not-prove notes on the page. The Roadmap
    destination renders it on the desktop. See
    `project-docs/features/2026-08-24-pm-roadmap.md`. Still open:
    journey stages on the page.
5. **Domain packs for medicine/finance/design (FIRST THREE SHIPPED
   2026-08-24; admission flow 2026-08-25)** -- the extension mechanism
   now carries three first-party data-only packs as repo data
   (terminology checklist, claims-compliance screens, design-token
   rules), each admitted by the shipped verifier with hash-pinned
   oracle evidence and zero code changes. Admission is a route now:
   verify, persist immutable run-root state, fire `pack.admitted`
   hooks. See
   `project-docs/features/2026-08-24-first-domain-packs.md`. Still
   open: per-domain depth beyond the seed checklists.
6. **Skill from experience (SHIPPED 2026-08-24)** -- answers Hermes. An
    admitted skill is now mechanically a procedure plus a passing gate
    receipt: only an ADMITTED lesson binds, evidence is an all-pass
    verified bench or a zero-regression trace report, bindings store
    digests only, and the registry refuses tampered rows. See
    `project-docs/features/2026-08-24-skill-from-experience.md`.

## The rule that stays fixed

Every pillar above inherits the floor: receipts on outcomes, gates on
accepts, honest nulls, no composite scores. The ceiling is everything
else.

## Does not prove

This charter is a map, not an acceptance. Each workstream lands with its
own tests, gates, and record.
