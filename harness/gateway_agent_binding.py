"""Immutable supervised-agent routing, workspace and budget authority."""
from dataclasses import asdict
from pathlib import Path
import re
from urllib.parse import urlsplit

from .evidence_json import canonical_sha256
from .gateway_operation import GatewayOperationError
from .plan_run_snapshot import freeze_json, thaw_json
from .gateway_agent_workspace import freeze_workspace, validate_workspace

SCHEMA = "flywheel.gateway-agent-binding/v1"
SCHEMA_V2 = "flywheel.gateway-agent-binding/v2"
MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,159}")


def _endpoint(name):
    from .providers import REGISTRY
    from .endpoint_registry import _NATIVE
    if name == "stub":
        return dict(name=name, adapter="stub", base_url="", slot="", local=True,
                    default_model="stub", specification_sha256=canonical_sha256({"name": "stub"}))
    if name in REGISTRY:
        spec = REGISTRY[name]
        return dict(name=name, adapter="openai", base_url=spec.base_url.rstrip("/"),
            slot=spec.api_key_env, local=spec.local, default_model=spec.default_model,
            specification_sha256=canonical_sha256(asdict(spec)))
    if name in {"anthropic", "gemini"}:
        spec = next(row for row in _NATIVE if row[0] == name)
        return dict(name=name, adapter=name,
            base_url="https://" + spec[3] + ("/v1beta" if name == "gemini" else ""),
            slot=spec[2], local=False, default_model=spec[4],
            specification_sha256=canonical_sha256(list(spec)))
    raise GatewayOperationError("AGENT_ENDPOINT_UNSUPPORTED")


def _profile(model, endpoint):
    from .model_profiles import MODEL_PROFILES, ollama_reference, ollama_digest_value
    if endpoint != "ollama": return None
    for name, profile in MODEL_PROFILES.items():
        release = profile["release"]
        if ollama_reference(model) == ollama_reference(release["ollama_model_name"]):
            return {"profile": name, "expected_manifest_sha256": ollama_digest_value(
                release["ollama_manifest_digest"]), "expected_artifact_sha256": release["artifact_sha256"]}
    return None


def _model(operation, endpoint):
    requested = operation.get("model")
    model = requested if requested is not None else endpoint["default_model"]
    if type(model) is not str or MODEL_PATTERN.fullmatch(model) is None:
        raise GatewayOperationError("AGENT_ENDPOINT_UNSUPPORTED")
    if endpoint["adapter"] == "stub" and model != "stub":
        raise GatewayOperationError("AGENT_ENDPOINT_UNSUPPORTED")
    return {"requested_model_reference": requested, "model_id": model,
        "selection": "explicit" if requested is not None else "frozen_default",
        "observation_policy": ("unavailable" if endpoint["adapter"] == "stub" else
            "ollama_exact" if endpoint["name"] == "ollama" else "provider_reported"),
        "profile": None}


def _budget(operation):
    return {"max_steps": operation["max_steps"], "max_tokens": operation.get("max_tokens", 1024),
            "timeout_s": operation.get("timeout_s", 300)}


def _sampling(endpoint, protocol=None):
    if protocol and protocol["native_api_route"] == "anthropic_messages":
        return {"temperature": None, "router_seed": 0, "provider_seed": None,
                "temperature_policy": "omitted"}
    return {"temperature": 0, "router_seed": 0, "provider_seed": None,
            "temperature_policy": "zero_or_omitted" if endpoint["adapter"] == "anthropic" else "zero"}


def _capabilities(value):
    return {"allow_write": value["allow_write"], "allow_exec": value["allow_exec"],
            "allow_mcp": False}


def _tool_protocol(value, endpoint, capabilities):
    mode = value.get("tool_protocol")
    if mode is None:
        return None
    from .gateway_agent_native_tools import native_tool_contract, text_tool_contract
    if mode == "native":
        return native_tool_contract(capabilities, endpoint)
    if mode == "text":
        return text_tool_contract()
    raise GatewayOperationError("AGENT_BINDING_DRIFT")


def freeze_agent_binding(operation, workspace_root: Path | None = None):
    value = operation.operation
    if value.get('execution_mode') == 'native_cli_session':
        from .gateway_cli_binding import freeze_cli_binding
        return freeze_cli_binding(operation, workspace_root)
    endpoint = _endpoint(value["endpoint"])
    capabilities = _capabilities(value)
    protocol = _tool_protocol(value, endpoint, capabilities)
    binding = {"schema": SCHEMA_V2 if protocol else SCHEMA,
        "operation_sha256": operation.operation_sha256,
        "endpoint": endpoint, "model": _model(value, endpoint),
        "workspace": freeze_workspace(value.get("root"), workspace_root or Path.cwd()),
        "budget": _budget(value), "capabilities": capabilities,
        "sampling": _sampling(endpoint, protocol),
        "transport": {"redirects": False, "ambient_proxy": False, "fallback": False,
                      "max_requests": value["max_steps"]}}
    if protocol:
        binding["tool_protocol"] = protocol
    binding["model"]["profile"] = _profile(binding["model"]["model_id"], endpoint["name"])
    validate_agent_binding(binding, operation)
    return freeze_json(binding, max_bytes=32768)


def validate_agent_binding(binding, operation):
    """Validate the IPC snapshot without reloading registry, root policy or env."""
    if operation.operation.get('execution_mode') == 'native_cli_session':
        from .gateway_cli_binding import validate_cli_binding
        return validate_cli_binding(binding, operation)
    try:
        value = operation.operation
        expected_keys = {"schema", "operation_sha256", "endpoint", "model",
            "workspace", "budget", "capabilities", "sampling", "transport"}
        has_protocol = "tool_protocol" in value
        if has_protocol:
            expected_keys.add("tool_protocol")
        if (type(binding) is not dict or set(binding) != expected_keys
                or binding["schema"] != (SCHEMA_V2 if has_protocol else SCHEMA)
                or binding["operation_sha256"] != operation.operation_sha256):
            raise ValueError
        endpoint = binding["endpoint"]
        if (set(endpoint) != {"name", "adapter", "base_url", "slot", "local", "default_model", "specification_sha256"}
                or endpoint["name"] != value["endpoint"]
                or endpoint["adapter"] not in {"stub", "openai", "anthropic", "gemini"}
                or any(type(endpoint[k]) is not str for k in endpoint if k != "local")
                or type(endpoint["local"]) is not bool
                or re.fullmatch(r"[a-f0-9]{64}", endpoint["specification_sha256"]) is None
                or endpoint["slot"] and re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", endpoint["slot"]) is None):
            raise ValueError
        url = urlsplit(endpoint["base_url"])
        if endpoint["adapter"] != "stub" and (url.scheme not in {"http", "https"}
                or not url.hostname or url.username or url.password or url.query or url.fragment
                or url.scheme != "https" and not endpoint["local"]):
            raise ValueError
        model = binding["model"]
        # Profile pins are frozen catalog authority; never relabel them as observations.
        expected = _model(value, endpoint); expected["profile"] = model.get("profile")
        capabilities = _capabilities(value)
        protocol = _tool_protocol(value, endpoint, capabilities)
        if (freeze_json(model) != freeze_json(expected) or freeze_json(binding["budget"]) != freeze_json(_budget(value))
                or freeze_json(binding["capabilities"]) != freeze_json(capabilities)
                or freeze_json(binding["sampling"]) != freeze_json(_sampling(endpoint, protocol))
                or freeze_json(binding["transport"]) != freeze_json({"redirects": False, "ambient_proxy": False,
                    "fallback": False, "max_requests": value["max_steps"]})):
            raise ValueError
        if protocol and freeze_json(binding["tool_protocol"]) != freeze_json(protocol):
            raise ValueError
        validate_workspace(binding["workspace"])
        if model["profile"] is not None and (set(model["profile"]) != {
                "profile", "expected_manifest_sha256", "expected_artifact_sha256"}
                or type(model["profile"]["profile"]) is not str
                or any(re.fullmatch(r"[a-f0-9]{64}", model["profile"][k]) is None
                    for k in ("expected_manifest_sha256", "expected_artifact_sha256"))):
            raise ValueError
        freeze_json(binding, max_bytes=32768)
    except Exception:
        raise GatewayOperationError("AGENT_BINDING_DRIFT") from None


def binding_for_authorized(authorized):
    snapshot = getattr(authorized.execution_plan, "agent_binding", None)
    if snapshot is None: raise GatewayOperationError("AGENT_REPREPARE_REQUIRED")
    binding = thaw_json(snapshot)
    validate_agent_binding(binding, authorized)
    return binding
