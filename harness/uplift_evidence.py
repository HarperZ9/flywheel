"""Interpret the legacy retry experiment without upgrading it to uplift evidence.

The persisted v1 records remain unchanged. This projection also applies when an
older gateway artifact is read, so old inference cannot reappear as a new claim.
"""
from copy import deepcopy

DIAGNOSTIC_NOTE = (
    "No workflow uplift established: generation budgets differ, and the wrapped "
    "selector is also its scorer. The rate difference is descriptive; no valid "
    "paired uplift interval is available. Use candidate pools with a separate "
    "held-out scorer and a generation-matched control."
)


def interpret_legacy_run(doc: dict) -> dict:
    result = deepcopy(doc)
    result.update(analysis_kind="legacy_retry_diagnostic",
                  claim_status="not_established", note=DIAGNOSTIC_NOTE)
    result["next_method"] = {
        "pool": "harness/pool.py", "selection": "harness/pool_arms.py",
        "existing_driver": "scripts/compute_arms.py",
        "scope": "Existing driver covers preregistered certificate families; "
                 "coding workflows need distinct selection and final tests.",
    }
    for delta in result.get("deltas", []):
        if delta.get("newcombe_95") is not None:
            delta["legacy_reported_interval"] = delta["newcombe_95"]
        delta.update(claim_status="not_established", newcombe_95=None,
                     includes_zero=None, note=DIAGNOSTIC_NOTE)
    for row in result.get("rows", []):
        n, passed = row.get("n_tasks"), row.get("passes")
        valid = (type(n) is int and n > 0 and type(passed) is int
                 and 0 <= passed <= n)
        row["completion_denominator"] = n if valid else None
        row["confirmed_completion_rate"] = round(passed / n, 4) if valid else None
    return result
