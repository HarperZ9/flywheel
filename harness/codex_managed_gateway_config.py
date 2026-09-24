"""Gateway-side glue for managed Codex composition."""
from __future__ import annotations

from pathlib import Path

from .codex_managed_composition import (
    build_managed_codex_components,
    managed_codex_server_config,
)


def managed_config_from_args(args, *, state_root: Path):
    managed_intent = any((
        args.managed_codex_executable,
        args.managed_codex_executable_sha256,
        args.managed_codex_model,
        args.managed_codex_version,
        args.managed_codex_policy_root,
    ))
    policy_root = None
    if managed_intent:
        policy_root = args.managed_codex_policy_root or state_root / "codex-managed-policy"
    return managed_codex_server_config(
        executable=args.managed_codex_executable,
        executable_sha256=args.managed_codex_executable_sha256,
        model=args.managed_codex_model,
        codex_version=args.managed_codex_version,
        version_provenance=args.managed_codex_version_provenance,
        policy_root=policy_root,
    )


def configure_managed_gateway_components(handler_cls, state_root):
    state = Path(state_root)
    lifecycle = _lifecycle_for(handler_cls, state)
    components = build_managed_codex_components(
        repo_root=Path(handler_cls.root),
        run_root=Path(handler_cls.run_root),
        state_root=state,
        clock=handler_cls.clock,
        config=handler_cls.native_codex_config,
        current=handler_cls.native_codex_components,
        lifecycle=lifecycle,
    )
    handler_cls.native_codex_components = components
    handler_cls.native_codex_lifecycle = lifecycle
    handler_cls.operation_service = components.operation_service
    handler_cls.operation_process_factory = components.operation_process_factory
    handler_cls.codex_account_manager = components.codex_account_manager
    return components


def _lifecycle_for(handler_cls, state_root: Path):
    cfg = handler_cls.native_codex_config
    if cfg is None:
        return None
    from .codex_managed_inventory_lifecycle import CodexManagedInventoryLifecycle
    state_root.mkdir(parents=True, exist_ok=True)
    cfg.policy_root.mkdir(parents=True, exist_ok=True)
    return CodexManagedInventoryLifecycle(
        state_root=state_root,
        policy_root=cfg.policy_root,
        workspace=Path(handler_cls.root),
        executable=cfg.executable,
        executable_sha256=cfg.executable_sha256,
        configured_version=cfg.codex_version,
        version_provenance=cfg.version_provenance,
        model=cfg.model,
    )
