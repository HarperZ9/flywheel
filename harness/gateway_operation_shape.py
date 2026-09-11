"""gateway_operation_shape.py -- per-action shape validation."""
from __future__ import annotations

from .evidence_json import canonical_sha256
from .continuation_agent_handoff import AGENT_HANDOFF_SCHEMA
from .continuation_store import PREVIEW_REF_PATTERN
from .gateway_operation import (
    PROPOSAL_REF_PATTERN, OPERATION_REF_PATTERN, _relative_path, _text)
from .journey_types import SHA256_PATTERN


def validate_operation_shape(action: str, value: dict) -> None:
    if action == "output.check":
        from .output_check_gateway import validate_output_check_operation as v
        return v(value)
    text_fields = {"model", "goal", "endpoint", "workflow", "profile", "root",
                   "test_cmd", "name", "tool", "detail", "prompt",
                   "solution_sig", "intent_source",
                   "architecture_source", "prp_id", "code", "path", "kind",
                   "oracle_cmd", "fixtures_root", "governance_tier",
                   "bulletin_access", "effort", "tool_protocol",
                   "reason", "authority_1", "authority_2", "mode"}
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
        if "context" in value and not _text(value["context"]):
            raise ValueError
        for list_field in ("examples", "documentation"):
            if list_field in value and type(value[list_field]) is not list:
                raise ValueError
    if action == "hook.register":
        from .accountable_hooks import validate_hook_payload
        validate_hook_payload(event=value["event"], argv=value["argv"],
                              blocking=value["blocking"],
                              hook_id=value["hook_id"])
    if action == "hook.run":
        from .accountable_hooks import validate_hook_run_plan
        validate_hook_run_plan(event=value["event"],
                               registrations=value["registrations"],
                               context=value["context"])
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
    if action == "agent.run" and "continuation" in value:
        _continuation_agent_shape(value["continuation"])
    if action == "agent.run":
        from .gateway_agent_binding import MODEL_PATTERN
        if "model" in value and MODEL_PATTERN.fullmatch(value["model"]) is None:
            raise ValueError
        if (value.get('execution_mode', 'native_cli_session') != 'native_cli_session'
            or 'execution_mode' in value and ('tool_protocol' in value or value['endpoint'] not in {'claude-cli', 'codex-cli'})
            or 'tool_protocol' in value and value['tool_protocol'] not in {'text', 'native'}): raise ValueError
        if "max_tokens" in value: _bounded_int(value["max_tokens"], 1, 32768)
        if "timeout_s" in value: _bounded_int(value["timeout_s"], 1, 1800)
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
    for name in ("arguments", "args", "data", "manifest"):
        if name in value and type(value[name]) is not dict:
            raise ValueError
    if action == "invent.round":
        _bounded_int(value["k"], 1, 50)
        if "offset" in value:
            _bounded_int(value["offset"], 0, 1_000_000)
    if action == "suite.audit" and "max_mutants" in value:
        _bounded_int(value["max_mutants"], 1, 20)
    if action == "lane.call" and "timeout" in value:
        _bounded_int(value["timeout"], 1, 600)
    if action == "lane.call":
        from .bulletin_origin import BulletinOriginError, operation_bulletin_origin
        from .gateway_operation import GatewayOperationError
        if value["name"] == "bulletin" and value["tool"] == "board_write_post":
            try:
                operation_bulletin_origin(value)
            except BulletinOriginError as exc:
                raise GatewayOperationError(exc.code) from None
        elif "bulletin_base_url" in value:
            raise ValueError
    if action == "lane.call" and "bulletin_access" in value:
        if value.get("name") != "bulletin":
            raise ValueError
        from .bulletin_access import validate_request_access
        validate_request_access(value["bulletin_access"])
    if (action == "capability.probe" and "disk_gb" in value
            and type(value["disk_gb"]) not in (int, float)):
        raise ValueError
    if action == "infra.kill":
        _kill_shape(value)


def _kill_shape(value: dict) -> None:
    """The kill switch refuses a request it cannot name in full.

    Two authorities, and they must be different people: one operator typing
    the same name twice is a one-person rule wearing a two-person label. The
    mode and the action list come from the kill switch's own vocabulary, so a
    misspelled action cannot silently do nothing while the receipt says it
    ran."""
    from .infra.kill_switch import ACTIONS, SHUTDOWN_MODES
    if value["authority_1"] == value["authority_2"]:
        raise ValueError
    if "mode" in value and value["mode"] not in SHUTDOWN_MODES:
        raise ValueError
    if "actions" in value:
        wanted = value["actions"]
        if (type(wanted) is not list or not wanted
                or any(name not in ACTIONS for name in wanted)
                or len(set(wanted)) != len(wanted)):
            raise ValueError


def _bounded_int(value: object, low: int, high: int) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValueError


def _continuation_agent_shape(value: object) -> None:
    fields = {"schema", "preview_ref", "preview_sha256",
              "source_state_sha256", "selected_files"}
    if (type(value) is not dict or set(value) != fields
            or value.get("schema") != AGENT_HANDOFF_SCHEMA
            or PREVIEW_REF_PATTERN.fullmatch(value.get("preview_ref", "")) is None
            or SHA256_PATTERN.fullmatch(value.get("preview_sha256", "")) is None
            or SHA256_PATTERN.fullmatch(
                value.get("source_state_sha256", "")) is None):
        raise ValueError
    files = value["selected_files"]
    if (type(files) is not list or len(files) > 8
            or len(set(files)) != len(files)
            or any(not _relative_path(item) for item in files)):
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
    if action == "capability.probe":
        return {"kind": "endpoint", "ref": value["endpoint"]}
    if action == "invent.round":
        return {"kind": "forge", "ref": "conjecture-forge"}
    if action == "lean.check":
        return {"kind": "oracle", "ref": "lean"}
    if action == "output.check":
        from .output_check_gateway import output_check_destination as d
        return d(value)
    if action == "suite.audit":
        return {"kind": "suite", "ref": value["path"]}
    if action == "lane.call":
        if value["name"] == "bulletin" and value["tool"] == "board_write_post":
            return {"kind": "lane", "ref": "bulletin",
                    "bulletin_base_url": value.get("bulletin_base_url", "")}
        return {"kind": "lane", "ref": value["name"]}
    if action == "packs.admit":
        return {"kind": "pack", "ref": _pack_ref(value["manifest"])}
    if action == "store.put":
        return {"kind": "store", "ref": value["kind"]}
    if action == "import.config":
        return {"kind": "workspace", "ref": value["root"]}
    if action == "hook.register":
        return {"kind": "hook", "ref": value["hook_id"]}
    if action == "hook.run":
        rows = value["registrations"]
        return {"kind": "hook-event",
                "ref": f"{value['event']}:{len(rows)}:"
                       f"{canonical_sha256(rows)[:12]}"}
    if action == "infra.credential_scan":
        root = value.get("root")
        return {"kind": "scan", "ref": root if root else "environment"}
    if action == "infra.isolation":
        return {"kind": "boundary", "ref": "isolation"}
    if action == "infra.kill":
        return {"kind": "kill-switch", "ref": value.get("mode")
                or "evidence-preserving"}
    if action in {"agent.run", "workflow.run", "plan.run"}:
        return {"kind": "endpoint", "ref": value["endpoint"]}
    if action.startswith("plugin."):
        return {"kind": "plugin", "ref": value["name"]}
    return {"kind": "marketplace", "ref": value["name"]}


def _pack_ref(manifest: dict) -> str:
    """Use a declared pack name; never invent one for an unnamed manifest."""
    ref = manifest.get("pack_id") or manifest.get("name")
    return ref if type(ref) is str and ref.strip() else "unnamed-pack"


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
    if action == "capability.probe":
        selected.add("network")
    if action == "invent.round":
        # The forge calls a model to propose and a kernel to judge.
        selected.update(("network", "write"))
    if action == "lean.check":
        # The Lean kernel is a subprocess and the verdict is stored.
        selected.update(("exec", "write"))
    if action == "output.check":
        from .output_check_gateway import output_check_scopes as scopes
        selected.update(scopes(value))
    if action == "suite.audit":
        # Mutation audit runs the project's own test command repeatedly.
        selected.add("exec")
    if action == "lane.call":
        selected.update(("exec", "network", "plugin"))
    if action in {"packs.admit", "store.put", "import.config"}:
        selected.add("write")
    if action == "hook.register":
        selected.add("write")
    if action == "hook.run":
        selected.add("exec")
    if action == "infra.credential_scan":
        # Record credential fingerprints, never values; retain the secrets scope.
        selected.add("secrets")
    if action == "infra.isolation":
        selected.add("network")
    if action == "infra.kill":
        # Isolate the network, revoke the credentials, end the process.
        selected.update(("exec", "network", "secrets"))
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
