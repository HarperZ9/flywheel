<!-- writing-profile: readme -->
# Trace observation

Trace observation tells an evaluator what a model's reasoning exposes on a given run, and records what it does not expose as a measured gap. It shares one sealed chain and one escalation path with the pre-action monitor, so an observation can hold an agent's next tool call until the owner reviews it.

## What it reads

| Tier | Signals | Access class |
| --- | --- | --- |
| Local open-weight model (Ollama) | raw reasoning text, token log probabilities, edits to the reasoning span | A1r, A2, A3 |
| Closed provider API | only documented signals: reasoning summaries, thinking blocks the provider returns, reasoning token counts, tool calls, log probabilities where offered | A0, A1s |
| DeepSeek API | `reasoning_content`, which the provider documents as the chain of thought | A1r (provider claim) |

Encrypted or opaque reasoning fields (`encrypted_content`, `signature`, `redacted_thinking`, thought signatures) are hashed exactly as received and stored as `{name, sha256, bytes}` with the gap code `PROVIDER_ENCRYPTED`. No code path decodes, decrypts, parses or forwards them, and a static test enforces that for every adapter.

## Run it on a recorded response

```python
from harness.trace_observation.observe import observe_run, render_report

result = observe_run(
    "monitor-home", run_id="run-1", provider="anthropic",
    turns=[{"request": request_json, "response": response_json}],
    observed_on="2026-10-01")
print(render_report(result))
```

The report keeps three lists apart: what the run observed, what no outside party can observe through documented interfaces, and what Flywheel has not yet set up locally.

## Components

- `adapters/`: one capture adapter per provider (Anthropic, OpenAI, xAI, Google, DeepSeek, Mistral, Ollama). Each names every response path it reads, the documentation source behind it, and a confidence. Paths no source documents are marked `adapter-unverified`.
- `access_gap.py`: the per-run measured-gap record. It compares the provider access-gap record (API surface, six providers, read 2026-10-01) against what the run saw, field by field: `MATCH`, `DRIFT`, `UNVERIFIABLE` or `DOCUMENTED_ONLY`. It marks cells that rest only on a reseller's page, cells with undated sources, and stale cells.
- `openweight/`: raw capture and the reasoning-edit interventions on a local model. Truncation snaps to sentence ends. The error edit changes one number and comes with an unedited prefix and a neutral control. A second independent trace gives the resample baseline. Null arms are scored on dependent items only, with their upper bound stated. A code mask separates reasoning dependence from copying a drafted program. Filler is a disruption probe, never the null.
- `behavioral/`: closed-model designs that need no reasoning text. Observed versus unobserved cue arms, with signed two-sided gaps and the observation-invariance score. A perceived-condition covariate, with stratum sizes. A realism ladder gated on a manipulation check. Answer-level contradiction on comparative pairs, with a split-half null.
- `controls.py`: planted inputs with known answers, run before any real result counts. A failed control raises a hold.
- `monitor_hook.py`: findings become holds. Flags come only from measured findings: documentation drift, a failed control, an observed-versus-unobserved gap whose interval excludes zero, or a finding an owner-configured component submits.

## The hold

`raise_trace_flag` writes a sealed `flywheel.preaction-traceflag/v1` record into the monitor's chain, then registers the flag. On the run's next proposed call, the monitor's trajectory layer holds the call. The flag clears when the owner approves once, rejects or terminates. Expiry leaves it standing. The flag files live in the monitor home, which the monitor always protects, so an agent cannot clear its own flag. `flywheel monitor verify` re-walks observation receipts, flags and holds together.

## What it does not prove

A record shows what a run could read. Raw reasoning text is sampled output, not the computation. A summary is a second model's writing about the first model's reasoning. A gap shows a quantity was not measured through documented access on the recorded date; provider interfaces change. A flag or a gap verdict is a behavioral observation on these inputs and says nothing about intent. Passing the control bank shows the instruments return known answers on planted inputs; it does not bound misses on cases nobody planted.
