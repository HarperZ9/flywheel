"""Exact nested workflow-run verification for Plan evidence."""
from __future__ import annotations

import re

from .plan_run_snapshot import freeze_json, thaw_json
from .workflows import recompute_chain


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RUN_FIELDS = {"schema", "workflow", "endpoint", "goal_excerpt", "started",
               "steps", "status", "chain_hash"}
_SIGN_FIELDS = {"kind", "workflow", "endpoint", "status", "chain_hash",
                "n_steps", "stored", "store_chain_hash"}


class PlanWorkflowContractError(ValueError):
    """The nested workflow receipt is not exactly self-consistent."""


def _nonempty(value: object) -> bool:
    return type(value) is str and bool(value)


def _valid_countersign(value: object, run: dict) -> bool:
    if type(value) is not dict or set(value) != _SIGN_FIELDS:
        return False
    identity = {
        "kind": "workflow-run", "workflow": run["workflow"],
        "endpoint": run["endpoint"], "status": run["status"],
        "chain_hash": run["chain_hash"], "n_steps": len(run["steps"]),
    }
    return (all(value.get(key) == item for key, item in identity.items())
            and type(value.get("n_steps")) is int
            and _nonempty(value.get("stored"))
            and type(value.get("store_chain_hash")) is str
            and _SHA256.fullmatch(value["store_chain_hash"]) is not None)


def validate_plan_workflow_run(value: object, *, workflow: str, endpoint: str,
                               require_countersign: bool) -> dict:
    """Return a fresh run only when shape, identity, and legacy chain match."""
    try:
        run = thaw_json(freeze_json(value))
        fields = _RUN_FIELDS | ({"run_countersign"}
                                if require_countersign else set())
        strings = ("workflow", "endpoint", "goal_excerpt", "started", "status")
        valid = (set(run) == fields
                 and run.get("schema") == "flywheel.workflow-run/v1"
                 and all(_nonempty(run.get(name)) for name in strings)
                 and _nonempty(workflow) and _nonempty(endpoint)
                 and run["workflow"] == workflow
                 and run["endpoint"] == endpoint
                 and type(run.get("steps")) is list
                 and type(run.get("chain_hash")) is str
                 and _SHA256.fullmatch(run["chain_hash"]) is not None
                 and recompute_chain(run) == run["chain_hash"]
                 and (not require_countersign
                      or _valid_countersign(run.get("run_countersign"), run)))
        if not valid:
            raise PlanWorkflowContractError()
        return run
    except PlanWorkflowContractError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise PlanWorkflowContractError() from None
