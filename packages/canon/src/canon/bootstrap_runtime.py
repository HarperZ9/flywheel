from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .adapter import AdapterDescriptor
from .atom import CanonAtom
from .bootstrap_runtime_cache import BootstrapCacheResult, cache_entry_from_bundle, cache_failure, select_cache
from .bootstrap_runtime_error import BootstrapRuntimeError
from .bootstrap_runtime_inputs import load_bootstrap_inputs, source_item_dict
from .bootstrap_state_root import BootstrapStateRoot, BootstrapStateRootError, open_bootstrap_state_root
from .canonical_json import canonical_json_text, canonical_sha256, sha256_text
from .capsule import Budget, CapsuleBuildError, CapsuleCompileRequest, CapsuleTarget, SourceState, compile_capsule
from .cli_artifacts import ArtifactError, SourceBytes, WorkspaceRoot, checked_workspace
from .path_policy import PathPolicyError, assert_not_protected, is_reparse_point, resolve_under_root
from .readiness import ReadinessResult, evaluate_readiness_response
from .schema import Record
from .source_state import SourceStateItem
from .source_state_cache import SourceStateCache, SourceStateCacheError
from .witness import BootstrapCheck, BootstrapWitness

BOOTSTRAP_COMPILER_CONTRACT = "canon.bootstrap-runtime/2026-08-30"


@dataclass(frozen=True, slots=True)
class BootstrapRuntime:
    workspace: WorkspaceRoot
    state_dir: Path
    state_root: BootstrapStateRoot
    adapter: AdapterDescriptor
    target: CapsuleTarget
    source_state: SourceState
    source_items: tuple[SourceStateItem, ...]
    source_inputs: tuple[SourceBytes, ...]
    records: tuple[Record, ...]
    atoms: tuple[CanonAtom, ...]
    budget: Budget
    budget_key: str
    compiler_key: str
    cache_key: str
    readiness_response: dict[str, object] | None
    does_not_prove: tuple[str, ...]
    profile: str
    offline: bool
    run_id: str
    tier: str
    started_at: str


def resolve_workspace(raw_workspace: object, raw_state_dir: object) -> tuple[WorkspaceRoot, Path]:
    try:
        workspace = checked_workspace(raw_workspace)
        state_dir = resolve_under_root(raw_state_dir, root=workspace.path)
        assert_not_protected(state_dir)
        if is_reparse_point(state_dir): raise BootstrapRuntimeError("unsafe_path", "unsafe bootstrap path")
    except (ArtifactError, PathPolicyError, OSError) as exc:
        raise BootstrapRuntimeError("unsafe_path", "unsafe bootstrap path") from exc
    return workspace, state_dir


def load_runtime(snapshot: dict[str, object], descriptor: AdapterDescriptor, *, workspace: WorkspaceRoot, state_dir: Path) -> BootstrapRuntime:
    loaded = load_bootstrap_inputs(snapshot, workspace)
    try: state_root = open_bootstrap_state_root(workspace, state_dir)
    except BootstrapStateRootError as exc:
        raise BootstrapRuntimeError(exc.code, "unsafe bootstrap path") from exc
    target = CapsuleTarget(descriptor.adapter_id, "CANON.md", snapshot["tier"], False)  # type: ignore[arg-type]
    compiler_key = _compiler_key(descriptor)
    cache_key = SourceStateCache.key_for(
        loaded.source_items, adapter_id=descriptor.adapter_id, profile=snapshot["profile"],  # type: ignore[arg-type]
        budget=loaded.budget_key, compiler_version=compiler_key, offline=snapshot["offline"],  # type: ignore[arg-type]
    )
    return BootstrapRuntime(
        workspace, state_dir, state_root, descriptor, target, loaded.source_state, loaded.source_items,
        loaded.source_inputs, loaded.records, loaded.atoms, loaded.budget, loaded.budget_key,
        compiler_key, cache_key, loaded.readiness_response, _limitations(descriptor, snapshot["offline"]),
        snapshot["profile"], snapshot["offline"], snapshot["run_id"], snapshot["tier"], snapshot["started_at"],  # type: ignore[arg-type]
    )


def compile_or_reuse(context: BootstrapRuntime) -> BootstrapCacheResult:
    try: return select_cache(context, _entry_from_bundle)
    except SourceStateCacheError as exc:
        raise BootstrapRuntimeError(cache_failure(exc), "bootstrap cache failed") from exc
    except CapsuleBuildError as exc:
        raise BootstrapRuntimeError(_build_failure(exc), "capsule compile failed") from exc


def readiness_result(context: BootstrapRuntime, cache: BootstrapCacheResult) -> ReadinessResult:
    if context.readiness_response is not None:
        return evaluate_readiness_response(cache.readiness_probe, context.readiness_response)
    if context.tier == "enforced":
        return _unknown_readiness(cache, ("No readiness response was supplied for an enforced bootstrap.",))
    return _unknown_readiness(cache, ("No readiness response was supplied; host acknowledgement is unknown.",))


def host_enforcement_observed(context: BootstrapRuntime, result: ReadinessResult) -> bool:
    return (context.tier == "enforced" and result.verdict == "pass"
            and context.adapter.bootstrap.get("can_block_before_work") is True
            and bool(context.adapter.evidence_refs))


def build_witness(context: BootstrapRuntime, cache: BootstrapCacheResult, result: ReadinessResult, *, observed: bool) -> BootstrapWitness:
    limits = _witness_limitations(context, result, observed)
    return BootstrapWitness(
        context.run_id, cache.capsule.capsule_id, cache.manifest_sha256,
        cache.capsule.source_state.to_dict(), cache.capsule.target.to_dict(),
        context.tier, observed, context.started_at, _checks(context, cache, result, observed),
        cache.capsule.omissions, cache.capsule.lossy_transforms, result, limits,
    )


def result_data(context: BootstrapRuntime, cache: BootstrapCacheResult, result: ReadinessResult, *, observed: bool, witness_path: str | None = None) -> dict[str, object]:
    data = {
        "adapter_id": context.adapter.adapter_id, "authoritative_tier": context.adapter.integration_tier,
        "cache_key": cache.cache_key, "cache_status": cache.cache_status,
        "canon_md_sha256": cache.canon_md_sha256, "capsule_id": cache.capsule.capsule_id,
        "does_not_prove": list(_witness_limitations(context, result, observed)),
        "host_enforcement_observed": observed, "manifest_sha256": cache.manifest_sha256,
        "missing_ids": list(result.missing_ids), "mismatched_ids": list(result.mismatched_ids),
        "offline": context.offline, "profile": context.profile,
        "readiness_probe_id": cache.readiness_probe.probe_id,
        "readiness_response_hash": None if context.readiness_response is None else result.response_hash,
        "readiness_verdict": result.verdict, "requested_tier": context.tier,
        "run_id": context.run_id, "source_state": context.source_state.to_dict(),
        "witness_path": witness_path,
    }
    return data


def compile_event_data(context: BootstrapRuntime, cache: BootstrapCacheResult) -> dict[str, object]:
    return {
        "cache_key": context.cache_key, "cache_status": cache.cache_status,
        "capsule_id": cache.capsule.capsule_id, "manifest_sha256": cache.manifest_sha256,
        "readiness_probe_id": cache.readiness_probe.probe_id,
        "source_state_sha256": context.source_state.records_digest,
    }


def present_event_data(cache: BootstrapCacheResult) -> dict[str, object]:
    return {"canon_md_sha256": cache.canon_md_sha256, "capsule_id": cache.capsule.capsule_id,
            "manifest_sha256": cache.manifest_sha256}


def _entry_from_bundle(context: BootstrapRuntime) -> dict[str, object]:
    return cache_entry_from_bundle(context, compile_capsule(_compile_request(context)))


def _compile_request(context: BootstrapRuntime) -> CapsuleCompileRequest:
    return CapsuleCompileRequest(
        profile=context.profile, target=context.target, source_state=context.source_state,
        budget=context.budget, atoms=context.atoms, records=context.records,
        receipts=(_source_receipt(context),), does_not_prove=context.does_not_prove,
        required_atom_ids=_critical_atom_ids(context.atoms),
        readiness_probe_id=_probe_id(context.target, context.source_state, context.profile),
        readiness_target=_readiness_target(context.adapter, context.target),
    )


def _checks(context: BootstrapRuntime, cache: BootstrapCacheResult, result: ReadinessResult, observed: bool) -> tuple[BootstrapCheck, ...]:
    if observed:
        refs = (context.source_state.records_digest, cache.capsule.capsule_id,
                result.response_hash, *context.adapter.evidence_refs)
        return tuple(BootstrapCheck(name, "pass", refs) for name in ("freshness", "conflicts", "secrets", "budget", "reachability", "readiness"))
    return (
        BootstrapCheck("freshness", "pass", (context.source_state.records_digest,)),
        BootstrapCheck("conflicts", "pass" if not cache.capsule.conflicts else "blocked", (cache.capsule.capsule_id,)),
        BootstrapCheck("secrets", "pass", tuple(item.sha256 for item in context.source_items)),
        BootstrapCheck("budget", "pass", (cache.capsule.capsule_id,)),
        BootstrapCheck("reachability", "unknown", (), {"offline": context.offline}),
        BootstrapCheck("readiness", result.verdict, (result.response_hash,)),
    )


def _unknown_readiness(cache: BootstrapCacheResult, limits: tuple[str, ...]) -> ReadinessResult:
    return ReadinessResult(cache.readiness_probe.probe_id, cache.capsule.capsule_id,
                           "unknown", {}, (), (), canonical_sha256({"readiness_response": "absent"}), limits)


def _witness_limitations(context: BootstrapRuntime, result: ReadinessResult, observed: bool) -> tuple[str, ...]:
    limits = list(context.does_not_prove) + list(result.does_not_prove)
    if not observed: limits.append("This bootstrap does not prove host-level enforcement before work.")
    return tuple(dict.fromkeys(limits))


def _limitations(descriptor: AdapterDescriptor, offline: object) -> tuple[str, ...]:
    limits = list(descriptor.known_unknowns)
    limits.append("Task 9 does not execute a model, provider API, browser, MCP server, subprocess, or network probe.")
    if offline is True: limits.append("Offline mode records provider reachability as unknown.")
    return tuple(dict.fromkeys(limits))


def _readiness_target(descriptor: AdapterDescriptor, target: CapsuleTarget) -> dict[str, object]:
    return {"adapter": target.adapter, "bootstrap": descriptor.bootstrap,
            "host_enforcement_observed": target.host_enforcement_observed,
            "integration_tier": target.integration_tier,
            "known_unknowns": list(descriptor.known_unknowns), "surface": target.surface}


def _probe_id(target: CapsuleTarget, source_state: SourceState, profile: str) -> str:
    payload = {"profile": profile, "source_state": source_state.to_dict(), "target": target.to_dict()}
    return "probe-" + sha256_text(canonical_json_text(payload)).removeprefix("sha256:")[:16]


def _source_receipt(context: BootstrapRuntime) -> dict[str, object]:
    return {"kind": "bootstrap-source-state", "source_state_sha256": context.source_state.records_digest,
            "source_inputs": [source_item_dict(item) for item in context.source_items]}


def _critical_atom_ids(atoms: tuple[CanonAtom, ...]) -> tuple[str, ...]:
    return tuple(atom.id for atom in atoms if atom.critical is True)


def _compiler_key(descriptor: AdapterDescriptor) -> str:
    payload = {"adapter_descriptor_sha256": sha256_text(descriptor.to_json()),
               "adapter_version": descriptor.version, "contract": BOOTSTRAP_COMPILER_CONTRACT}
    return canonical_json_text(payload).removesuffix("\n")


def _build_failure(exc: CapsuleBuildError) -> str:
    return "critical_atom_loss" if "required atom" in str(exc) else "invalid_args"


__all__ = [
    "BootstrapRuntime", "BootstrapRuntimeError", "BootstrapCacheResult", "build_witness",
    "compile_event_data", "compile_or_reuse", "host_enforcement_observed", "load_runtime",
    "present_event_data", "readiness_result", "resolve_workspace", "result_data",
]
