# Subagent swarms: parallel sessions with per-child receipts

Date: 2026-08-24

## The scan (August 2026)

| Competitor | What they ship | The gap this feature exploits |
|---|---|---|
| Claude Code background agents | Subagent spawns with role prompts; results summarized back to the parent | No per-child receipt you can re-check later; no quorum rule a verifier can replay; child output is prose, not evidence |
| Codex CLI | Single-loop agent with resumable sessions | One loop, one context; parallelism is the operator opening more terminals |
| OpenCode | Multi-provider agents in one TUI | Fan-out is manual; nothing seals what each branch actually did |
| Cursor | Background agents in the IDE | Cloud-hosted runs with no local evidence trail |

Everyone ships concurrency as convenience. Nobody ships it as
accountability.

## The feature

`harness/subagents.py` + `harness/subagents_route.py`
(`GET/POST /api/subagents*`, schemas `flywheel.subagent-spec/v1`,
`flywheel.subagent-run/v1`, `flywheel.subagent-swarm/v1`):

1. One goal fans out to N children (1..8), each bound to a fixed role:
   explore, plan, implement, verify, review. Roles are an allowlist,
   and each carries the ONLY permissions it can hold: escalation is
   refused at registration, so an explorer cannot request write
   authority and a planner cannot request exec.
2. Every child launches as its own process tree -- argv, never a
   shell -- inside its own scratch workspace under
   `<run_root>/subagents/<swarm_id>/`, with the issued spec sealed by
   canonical hash. The child re-validates the seal and every field
   before it acts; a tampered spec is refused at exit code 3.
3. Each child is sealed a run receipt: spec hash, exit code, output
   hash, duration, timeout flag, and whether its result passed the
   parent's integrity check (schema, matching seal, completed status).
4. Fan-in is deterministic arithmetic against a declared quorum policy
   (all / majority / any). No learned model decides whether the swarm
   satisfied its goal.
5. Fan-in fires the accountable hooks `agent.completed` event from the
   run root's registry, so a failing blocking hook marks the swarm
   blocked exactly like any other event on this platform.

Why it matters: Claude Code made subagents convenient. This makes them
auditable. A junior dev, a hospital, or a bank can read the swarm
receipt afterward and see which children ran, what authority each held,
which timed out, and whether anyone tried to exceed their grant at
registration time. That receipt survives the session; prose summaries
do not.

## Verification

```text
python -m pytest tests/test_subagents.py -q                  # 10/10
python -m pytest tests/test_subagents_route.py -q            # 4/4
python -m pytest tests/ -q                                   # exit 0
python scripts/check_file_gate.py                            # clean
python scripts/check_verifier_stdlib.py                      # clean
python scripts/check_claim_language.py                       # clean
```

## Does not prove

A satisfied quorum attests the children ran and reported; it does not
prove the goal was achieved -- that travels on the swarm receipt's
`does_not_prove` list. Children run the real gated agent loop through
`router_agent`, but cross-restart job control (spawn, disconnect,
reattach, cancel a running swarm) is not built yet: a spawn is bounded
by its own timeout window in this process. Desktop surfaces for swarms
are not drawn yet either; the API is the contract.
