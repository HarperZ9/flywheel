# Model activity

The Usage screen includes a custom runtime visualization beside completed-answer
usage receipts. It uses Flutter's built-in drawing APIs and Python's standard
library; it adds no package dependency.

Select a model to inspect generation and prompt-processing history. Pause stops
new observation requests. Leaving the screen disposes its timer; backgrounding
the app suspends observation. History is bounded to 60 observations per model.
Missing measurements create gaps. A failed refresh marks retained data stale.

The authenticated `/api/usage/live` route observes configured local endpoints.
It does not start models or submit prompts. Unsupported counters remain
unavailable. Rates describe counter changes over a measured interval, not answer
quality. Counter resets require a fresh baseline.

The initial adapters read llama.cpp `/slots` and vLLM `/metrics`. Separate vLLM
model labels produce separate rows and rate baselines. llama.cpp counts refer to
the current slot tasks; vLLM counts are runtime totals. A missing prompt-processing
counter leaves prefill unavailable while decode can still be measured. These
samples do not reconstruct completed work between polls. Disconnections and
invalid samples clear the baseline before another rate is reported.

Runtime model paths and unsafe display labels are replaced with stable opaque
labels. Model labels are runtime reports, not proof of the loaded weights.

Runtime counters and signed answer receipts answer different questions. The
former describe runtime activity; the latter retain completed-answer accounting.
Receipt timestamps currently cannot establish generation throughput. Power draw
is not reported by this initial integration.

The visual reference is [llm-visuals](https://github.com/DingoOz/llm-visuals).
Flywheel implements its own view and observation path; the reference project is
not installed, bundled, or imported.

This feature is part of the unreleased 1.0.0 candidate. Focused tests and visual
fixtures do not establish final installed acceptance or support for every
inference runtime.
