from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .adapter import assert_requested_tier_allowed, descriptor_for
from .bootstrap_report import BOOTSTRAP_STATES, BootstrapEvent, BootstrapReport, make_event, make_report
from .bootstrap_runtime import (
    build_witness, compile_event_data, compile_or_reuse, host_enforcement_observed,
    load_runtime, present_event_data, readiness_result, resolve_workspace, result_data,
)
from .bootstrap_runtime_error import BootstrapRuntimeError
from .bootstrap_validation import BootstrapConfigError, config_text, safe_text, snapshot_config_values
from .bootstrap_witness_store import BootstrapWitnessStoreError, write_bootstrap_witness


@dataclass(frozen=True, slots=True)
class BootstrapConfig:
    workspace: str
    state_dir: str
    target: str
    tier: str
    profile: str
    offline: bool
    run_id: str
    records_path: str | None = None
    atoms_path: str | None = None
    readiness_response_path: str | None = None
    started_at: str = "not-recorded"
    readiness_response: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        for name, value in _snapshot_config(self).items():
            object.__setattr__(self, name, value)


def run_bootstrap(config: BootstrapConfig) -> BootstrapReport:
    try: snapshot = _snapshot_config(config)
    except BootstrapConfigError as exc: return _invalid_config_report(exc)
    events: list[BootstrapEvent] = []
    try: descriptor = descriptor_for(snapshot["target"])
    except KeyError:
        return _terminal(events, "detect_entry", "invalid_args", "unsupported bootstrap target", {"reason": "unsupported_target"})
    base = _adapter_data(descriptor.adapter_id, descriptor.integration_tier, snapshot)
    if descriptor.integration_tier == "unsupported":
        return _terminal(events, "detect_entry", "unsupported_lifecycle", "unsupported bootstrap lifecycle", base)
    try: assert_requested_tier_allowed(descriptor, snapshot["tier"])
    except ValueError:
        return _terminal(events, "detect_entry", "tier_mislabeled", "requested tier exceeds adapter descriptor", base)
    events.append(make_event("detect_entry", "detected entry", base))
    try: workspace, state_dir = resolve_workspace(snapshot["workspace"], snapshot["state_dir"])
    except BootstrapRuntimeError as exc: return _terminal(events, "resolve_layers", exc.code, str(exc), base)
    events.append(make_event("resolve_layers", "resolved layers", base))
    try: runtime = load_runtime(snapshot, descriptor, workspace=workspace, state_dir=state_dir)
    except BootstrapRuntimeError as exc: return _terminal(events, "collect_source_state", exc.code, str(exc), base)
    events.append(make_event("collect_source_state", "collected source state", {"source_state": runtime.source_state.to_dict()}))
    try: return _run_checked(events, runtime, base)
    finally: runtime.state_root.close()


def _run_checked(events: list[BootstrapEvent], runtime: object, base: dict[str, object]) -> BootstrapReport:
    events.append(make_event("preflight", "preflight complete", base))
    try: cache = compile_or_reuse(runtime)
    except BootstrapRuntimeError as exc:
        return _terminal(events, "compile_or_reuse_capsule", exc.code, str(exc), base)
    events.append(make_event("compile_or_reuse_capsule", "compiled or reused capsule", compile_event_data(runtime, cache)))
    events.append(make_event("present_context", "context prepared", present_event_data(cache)))
    readiness = readiness_result(runtime, cache)
    observed = host_enforcement_observed(runtime, readiness)
    data = result_data(runtime, cache, readiness, observed=observed)
    if readiness.verdict != "pass" and (runtime.readiness_response is not None or runtime.tier == "enforced"):
        return _terminal(events, "readiness_probe", "readiness_failed", "readiness probe failed", data)
    events.append(make_event("readiness_probe", "readiness probe complete", data))
    return _emit_witness(events, runtime, cache, readiness, observed, data)


def _emit_witness(events: list[BootstrapEvent], runtime: object, cache: object, readiness: object, observed: bool, data: dict[str, object]) -> BootstrapReport:
    witness = build_witness(runtime, cache, readiness, observed=observed)
    try: write = write_bootstrap_witness(witness, workspace=runtime.workspace, state_dir=runtime.state_dir, state_root=runtime.state_root)
    except BootstrapWitnessStoreError as exc:
        return _terminal(events, "emit_witness", exc.code, "bootstrap witness write failed", data)
    data = result_data(runtime, cache, readiness, witness_path=write.relative_path, observed=observed)
    events.append(make_event("emit_witness", "witness emitted", {"witness_path": write.relative_path, "write_status": write.status}))
    events.append(make_event("release_to_work", "release to work", data))
    return make_report(True, "ok", "release to work", tuple(events), data)


def _snapshot_config(config: BootstrapConfig) -> dict[str, object]:
    if type(config) is not BootstrapConfig: raise BootstrapConfigError("invalid bootstrap config")
    snapshot = snapshot_config_values(
        workspace=config.workspace, state_dir=config.state_dir, target=config.target,
        tier=config.tier, profile=config.profile, offline=config.offline,
        run_id=config.run_id, readiness_response=config.readiness_response,
    )
    snapshot["records_path"] = _optional_path(config.records_path, "records_path")
    snapshot["atoms_path"] = _optional_path(config.atoms_path, "atoms_path")
    snapshot["readiness_response_path"] = _optional_path(config.readiness_response_path, "readiness_response_path")
    snapshot["started_at"] = _config_text(config.started_at, "started_at")
    if snapshot["readiness_response"] is not None and snapshot["readiness_response_path"] is not None:
        raise BootstrapConfigError("invalid bootstrap config")
    return snapshot


def _invalid_config_report(exc: BootstrapConfigError) -> BootstrapReport:
    if exc.code == "secret_quarantine":
        return _terminal([], "detect_entry", "secret_quarantine", "invalid bootstrap config", None)
    return make_report(False, "invalid_args", "invalid bootstrap config", (), None)


def _terminal(events: list[BootstrapEvent], state: str, code: str, message: str, data: dict[str, object] | None) -> BootstrapReport:
    event_data = {"state": state}
    if data is not None: event_data.update(data)
    events.append(BootstrapEvent(state, False, code, message, event_data))
    return make_report(False, code, message, tuple(events), data)


def _adapter_data(adapter_id: str, authoritative_tier: str, config: dict[str, object]) -> dict[str, object]:
    return {"adapter_id": adapter_id, "authoritative_tier": authoritative_tier,
            "offline": config["offline"], "profile": config["profile"],
            "requested_tier": config["tier"], "run_id": config["run_id"]}


def _optional_path(value: object, name: str) -> str | None:
    return None if value is None else _config_text(value, name)


def _config_text(value: object, name: str) -> str:
    try:
        return config_text(safe_text(value, name), name)
    except BootstrapConfigError:
        raise
    except TypeError:
        raise BootstrapConfigError("invalid bootstrap config") from None


__all__ = ["BOOTSTRAP_STATES", "BootstrapConfig", "BootstrapConfigError", "BootstrapEvent", "BootstrapReport", "run_bootstrap"]
