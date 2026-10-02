"""trace_observation -- what a model's reasoning exposes, and what it does not.

Open-weight models running locally are observed in full: raw reasoning text,
token log probabilities, and edits to the reasoning span. Closed models are
observed only through signals their providers document (reasoning summaries,
thinking blocks a provider returns, reasoning token counts, tool calls,
log probabilities where offered) and through behavior. Anything a provider
withholds or encrypts enters as a typed gap record, stored by digest and never
parsed, decoded or forwarded.

Every result lands in the pre-action monitor's sealed chain, and a flagged
trajectory can hold the run's next call through the monitor's escalation path.
Standard library only.
"""
