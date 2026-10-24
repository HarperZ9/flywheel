"""The run-budget record's vocabulary, with no runtime imports.

The worker writes the record (run_budget) and the gateway and the offline
verifier read it back (gateway_run_outcome). The verifier's import closure
must stay free of the live worker modules, so the words both sides agree on
live here and nowhere else.
"""
SCHEMA_V1 = "flywheel.run-budget/v1"   # named its codes list with the older name
SCHEMA = "flywheel.run-budget/v2"
#: The limits a run can stop on. wall_time is enforced by the process-tree
#: deadline and only recorded by the budget.
TRIPS = ("model_calls", "tool_actions", "usage_tokens", "cost_micros",
         "limit_signals", "wall_time")
#: The kinds of limit an output can report.
SIGNALS = ("rate_limit", "quota", "billing", "auth", "overloaded")
#: The limit signal reads English phrasing only: an error in another language,
#: or worded another way, is not seen.
#: What the budget record covers: usage the harness metered and the provider
#: reported, and limit signals found by matching English phrases in output.
SCOPE = ("HARNESS_METERED_USAGE", "PROVIDER_REPORTED_USAGE_COUNTED",
         "LIMIT_SIGNAL_BY_PHRASE_MATCH", "LIMIT_SIGNAL_ENGLISH_PHRASES")
