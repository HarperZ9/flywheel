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
2. **Subagents + parallel sessions** â€” answers Claude Code's
   background agents. The gateway already runs owned process trees with
   terminal Stop; spawn N agent loops against one goal with role
   prompts, fan-out/fan-in, and per-child receipts.
3. **Hooks with teeth** â€” answers Claude Code's hooks. Event-triggered
   automations (file change, git event, journey stage) where every hook
   run is itself receipted and a failing hook blocks the action
   fail-closed. Nobody's hooks are accountable.
4. **PM surface** â€” answers the manager use case. Journey stages are
   already a pipeline; add the roadmap view: goals â†’ decomposed tasks â†’
   per-task verification status â†’ one-page status a PM can read.
   Verification makes "done" mean something.
5. **Domain packs for medicine/finance/design** â€” the extension
   mechanism exists; ship the first three packs as admitted data-only
   packs (terminology checklists, compliance gates, design tokens) to
   prove any domain plugs in without code changes.
6. **Skill from experience** â€” answers Hermes. A lesson that carries a
   gate: an admitted skill is a procedure plus a passing gate receipt.
   Trace-bench already produces the evidence; lessons already have
   admission.

## The rule that stays fixed

Every pillar above inherits the floor: receipts on outcomes, gates on
accepts, honest nulls, no composite scores. The ceiling is everything
else.

## Does not prove

This charter is a map, not an acceptance. Each workstream lands with its
own tests, gates, and record.
