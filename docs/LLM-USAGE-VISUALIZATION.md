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

Focused tests and visual fixtures do not establish installed acceptance or
support for every inference runtime.

## Release note for the next feature release

The Usage view adds live counter charts for a selected local llama.cpp or vLLM
runtime. The selection follows Chat's endpoint and model. The authenticated
route reads counters only: it sends no generation request and starts no model.
Missing counters remain unavailable; pausing or leaving the view stops polling.
Existing completed-answer receipts retain their accounting and validation rules.
This change does not enable managed provider sessions or change the account panel.

This feature remains unreleased until its change is included in a tagged build.
Counter fixtures and widget tests do not prove performance on a particular model,
accuracy of runtime reports, or installed-app acceptance.
