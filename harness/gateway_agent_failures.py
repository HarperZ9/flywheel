"""Closed failure vocabulary shared by worker, trace and lifecycle."""
AGENT_FAILURES = frozenset({"AGENT_BINDING_DRIFT", "AGENT_REPREPARE_REQUIRED",
    "AGENT_MODEL_MISMATCH", "AGENT_ENDPOINT_UNSUPPORTED", "OPERATION_DEADLINE_EXCEEDED"})


def failure_reason(exc):
    code = getattr(exc, "code", None)
    return code if code in AGENT_FAILURES else "EXTERNAL_ACTION_FAILED"
