"""gateway_operation_shape.py -- per-action shape validation.

Extracted from gateway_operation.py to keep that module under its
ceiling. One function, pure: given an action and its canonical snapshot,
raise ValueError on any shape this gateway refuses. Field-type rules
live here so the canonicalization core stays about digests, refs, and
scopes.
"""
from __future__ import annotations

from .gateway_operation import PROPOSAL_REF_PATTERN, OPERATION_REF_PATTERN, _text


def validate_operation_shape(action: str, value: dict) -> None:
    text_fields = {"model", "goal", "endpoint", "workflow", "profile", "root",
                   "test_cmd", "name", "tool", "detail", "prompt",
                   "solution_sig", "context", "intent_source",
                   "architecture_source", "prp_id"}
    if any(key in value and not _text(value[key]) for key in text_fields):
        raise ValueError
    if action == "embeddings.create":
        items = value["input"]
        if type(items) is list:
            if not items or any(not _text(item) for item in items):
                raise ValueError
        elif not _text(items):
            raise ValueError
    if action == "forge.create":
        for list_field in ("examples", "documentation"):
            if list_field in value and type(value[list_field]) is not list:
                raise ValueError
    if action == "bench.run":
        tasks = value["tasks"]
        if (type(tasks) is not list or not tasks
                or any(type(t) is not dict
                       or any(not isinstance(t.get(k), str) or not t.get(k)
                              for k in ("task_id", "prompt", "gate_cmd"))
                       for t in tasks)):
            raise ValueError
        ids = [t["task_id"] for t in tasks]
        if len(set(ids)) != len(ids):
            raise ValueError
        eps = value["endpoints"]
        if (type(eps) is not list or not eps
                or any(not isinstance(e, str) or not e for e in eps)):
            raise ValueError
        if "cost_per_task" in value and type(value["cost_per_task"]) is not dict:
            raise ValueError
        if "timeout_s" in value and (type(value["timeout_s"]) is not int
                                     or not 1 <= value["timeout_s"] <= 1800):
            raise ValueError
    if action == "chat.complete":
        messages = value["messages"]
        if (type(messages) is not list or not messages
                or any(type(item) is not dict
                       or set(item) != {"role", "content"}
                       or item["role"] not in {"system", "user", "assistant"}
                       or type(item["content"]) is not str for item in messages)):
            raise ValueError
    for name in ("stream", "allow_write", "allow_exec", "enabled"):
        if name in value and type(value[name]) is not bool:
            raise ValueError
    if "max_steps" in value and (type(value["max_steps"]) is not int
                                 or not 1 <= value["max_steps"] <= 12):
        raise ValueError
    if ("timeout_ms" in value and (type(value["timeout_ms"]) is not int
                                   or not 1 <= value["timeout_ms"] <= 30_000)):
        raise ValueError
    if ("operation_ref" in value and OPERATION_REF_PATTERN.fullmatch(
            value["operation_ref"]) is None):
        raise ValueError
    if (action == "forge.recheck"
            and PROPOSAL_REF_PATTERN.fullmatch(value["prp_id"]) is None):
        raise ValueError
    if "arguments" in value and type(value["arguments"]) is not dict:
        raise ValueError


def destination_for(action: str, value: dict) -> dict:
    if action == "operation.cancel":
        return {"kind": "operation", "ref": value["operation_ref"]}
    if action == "chat.complete":
        return {"kind": "model", "ref": value["model"]}
    if action == "companion.ask":
        return {"kind": "model", "ref": "companion"}
    if action == "route.send":
        return {"kind": "endpoint", "ref": value["endpoint"]}
    if action == "forge.create":
        return {"kind": "forge", "ref": "forge"}
    if action == "forge.recheck":
        return {"kind": "forge", "ref": value["prp_id"]}
    if action == "embeddings.create":
        return {"kind": "model", "ref": value.get("model", "embeddings")}
    if action == "bench.run":
        return {"kind": "bench", "ref": "private-bench"}
    if action in {"agent.run", "workflow.run", "plan.run"}:
        return {"kind": "endpoint", "ref": value["endpoint"]}
    if action.startswith("plugin."):
        return {"kind": "plugin", "ref": value["name"]}
    return {"kind": "marketplace", "ref": value["name"]}


def derived_scopes(action: str, value: dict, secrets: bool) -> tuple:
    selected = set()
    if action == "operation.cancel":
        selected.add("exec")
    if action in {"chat.complete", "agent.run", "workflow.run", "plan.run",
                  "companion.ask", "route.send", "forge.create",
                  "forge.recheck", "embeddings.create"}:
        selected.add("network")
    if action == "bench.run":
        # Gates are subprocess commands: the benchmark is an execution.
        selected.update(("exec", "network"))
    if action in {"plugin.call"}:
        selected.update(("write", "exec", "network", "plugin"))
    if action == "plugin.probe":
        selected.update(("exec", "network", "plugin"))
    if action in {"plugin.register", "plugin.toggle", "plugin.remove",
                  "marketplace.install", "marketplace.add",
                  "marketplace.remove"}:
        selected.update(("write", "plugin"))
    if action in {"agent.run", "workflow.run", "plan.run"}:
        if value.get("allow_write") is True: selected.add("write")
        if value.get("allow_exec") is True: selected.add("exec")
    if secrets: selected.add("secrets")
    return tuple(scope for scope in
                 ("write", "exec", "network", "plugin", "secrets")
                 if scope in selected)
