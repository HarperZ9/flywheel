"""agent_false_accept -- which guards catch a destructive agent tool call.

A benign request goes to an agent whose tools are mocks. Every call it makes
is recorded, run against an in-memory filesystem and scheduler, labelled by
rule, and shown to each guard. Nothing the model emits is executed: the
sandbox is a dict, the scheduler is a list, the network is a log.

The corpus records a condition only as "baseline", "steered" or "random".
How a condition was produced stays with whoever ran it.
"""
SCHEMA = "flywheel.agent-false-accept/v1"
