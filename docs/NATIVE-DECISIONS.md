# Experimental native decision contract

The harness can validate a bounded choice proposal and evaluate supplied outcomes against separate labels. This is a source-level experiment. It is not mounted in the gateway, trained on task data, or a measured replacement for another router.

`harness.decision_contract.validate_request` accepts the exact request schema below and returns an independent snapshot:

```json
{
  "schema": "flywheel.decision-request/v1",
  "decision_ref": "example-1",
  "state": "Choose a route for this task.",
  "choices": [
    {"id": "local", "description": "Use the configured local worker."},
    {"id": "remote", "description": "Use the configured remote worker."}
  ],
  "eligible_choice_ids": ["local"],
  "evidence_refs": ["roster-1"]
}
```

The current limits are 50 choices, 100 evidence references, 8,192 state characters, 2,048 description characters and 4,096 response bytes. These are contract limits, not measured model capacity.

`evaluate_proposal(request, response, scorer_ref="example-scorer")` accepts a JSON response with exactly `choice_id` and `evidence_refs`. A choice must be declared and eligible; evidence references must belong to the request. A null choice abstains. Malformed or ineligible proposals produce fixed abstention reasons.

The result carries hashes, validated references and explicit limits. Oversized or nonstring responses have a null response digest because they were not hashed. A referenced source has not thereby been checked for truth. Caller-supplied eligibility is not authorization.

The offline evaluator accepts independent labels and result envelopes. It reports valid selection coverage, correctness among valid selections, overall correctness, abstention and invalid-result counts with denominators. Unknown latency and cost stay null. Invalid envelopes remain in the overall denominator; inspect their count when interpreting selective accuracy. Labels, measurements and result authenticity remain caller assertions.

Only an explicit proposal to abstain contributes to abstention quality. A contract rejection, including malformed or ineligible output, is counted separately as `rejected_proposals`; it cannot earn task success because the expected answer was abstention. Empty eligibility is also kept out of model abstention quality, and conflicting eligibility labels make that result invalid. These distinctions separate protective enforcement from scorer performance.

Run the deterministic controls from the repository root:

```shell
python -c "import json; from harness.decision_evaluation import synthetic_control_report; print(json.dumps(synthetic_control_report(), indent=2, allow_nan=False))"
python -m pytest tests/test_decision_contract.py tests/test_decision_evaluation.py
```

The controls include a correct choice, a wrong but valid choice, an ineligible choice, an always-abstain policy and a rejected proposal where the label expects abstention. They are fixtures with placeholder result hashes. They exercise the evaluator, not a provider or learned model. A perfect control score is not a model benchmark.

Before mounting a scorer, measure downstream task outcomes, uncertainty, total cost and latency on held-out cases. Keep execution on the existing authorization path. A learned score cannot grant permissions or certify task success.
