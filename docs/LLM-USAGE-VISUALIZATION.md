# Model activity

The Usage screen includes a custom runtime visualization beside completed-answer
usage receipts. It uses Flutter's built-in drawing APIs and Python's standard
library alone.

Select a model to inspect generation and prompt-processing history. Pause stops
new observation requests. Leaving the screen disposes its timer; backgrounding
the app suspends observation. History is bounded to 60 observations per model.
Missing measurements create gaps. A failed refresh marks retained data stale.

The authenticated `/api/usage/live` route observes configured local endpoints by
reading their counters. A counter the runtime omits shows as unavailable. Rates
describe counter changes over a measured interval. A counter reset starts a fresh
baseline.

The initial adapters read llama.cpp `/slots` and vLLM `/metrics`. Separate vLLM
model labels produce separate rows and rate baselines. llama.cpp counts refer to
the current slot tasks; vLLM counts are runtime totals. A missing prompt-processing
counter leaves prefill unavailable while decode can still be measured. These
samples do not reconstruct completed work between polls. Disconnections and
invalid samples clear the baseline before another rate is reported.

Runtime model paths and unsafe display labels are replaced with stable opaque
labels. A model label is what the runtime reports about itself.

Runtime counters and signed answer receipts answer different questions. The
former describe runtime activity; the latter retain completed-answer accounting.
Throughput comes from the counters, and power draw is a candidate for a later
integration.

The visual reference is [llm-visuals](https://github.com/DingoOz/llm-visuals).
Flywheel implements its own view and observation path, written from scratch.

Focused tests and visual fixtures cover llama.cpp and vLLM counters; each further
inference runtime gets its own fixture.

## Release note for the next feature release

The Usage view adds live counter charts for a selected local llama.cpp or vLLM
runtime. The selection follows Chat's endpoint and model. The authenticated
route reads counters only: it sends no generation request and starts no model.
Missing counters remain unavailable; pausing or leaving the view stops polling.
Existing completed-answer receipts retain their accounting and validation rules.
This change does not enable managed provider sessions or change the account panel.

This feature ships in tagged builds from v1.3.1 (`git tag --contains 895da353`).
Counter fixtures and widget tests check the charts and the polling; performance on
a given model and the accuracy of runtime reports come from the runtime itself.
