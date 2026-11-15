from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path

from .bootstrap_runtime_inputs import source_item_dict
from . import source_state_cache as _cache
from .atom import atoms_from_records
from .canonical_json import canonical_json_text, is_sha256_ref, sha256_text
from .canonmd import render_canon_md
from .capsule import Capsule, CapsuleBundle, validate_capsule
from .capsule_rules import atom_sort_key, critical_sets
from .readiness import CRITICAL_SET_KEYS, ReadinessProbe, validate_readiness_probe
from .secret_quarantine import SecretQuarantineError, scan_text
from .source_state_cache import SourceStateCache, SourceStateCacheError

BOOTSTRAP_CACHE_SCHEMA = "canon.bootstrap-cache-entry/v1"


@dataclass(frozen=True, slots=True)
class BootstrapCacheResult:
    cache_status: str
    cache_key: str
    capsule: Capsule
    readiness_probe: ReadinessProbe
    manifest_sha256: str
    canon_md_sha256: str
    does_not_prove: tuple[str, ...]


def select_cache(context: object, make_entry: Callable[[object], dict[str, object]]) -> BootstrapCacheResult:
    cache = _cache_store(context)
    current = cache.current()
    if current is not None and current.get("cache_key") == context.cache_key:  # type: ignore[attr-defined]
        return _cache_result(_validate_entry(current, context), "hit")
    existing = cache.get(context.cache_key)  # type: ignore[attr-defined]
    if existing is not None:
        return _cache_result(_validate_entry(existing, context), "hit")
    entry = make_entry(context)
    cache.put(context.cache_key, entry)  # type: ignore[attr-defined]
    return _cache_result(_validate_entry(entry, context), "miss")


def cache_entry_from_bundle(context: object, bundle: CapsuleBundle) -> dict[str, object]:
    entry = {
        "budget_key": context.budget_key, "cache_key": context.cache_key,  # type: ignore[attr-defined]
        "canon_md_sha256": sha256_text(bundle.canon_md), "capsule": bundle.capsule.to_dict(),
        "compiler_key": context.compiler_key, "does_not_prove": list(bundle.capsule.does_not_prove),  # type: ignore[attr-defined]
        "manifest_sha256": bundle.capsule.integrity.manifest_sha256,
        "readiness_probe": bundle.readiness_probe.to_dict(), "schema": BOOTSTRAP_CACHE_SCHEMA,
        "source_inputs": [source_item_dict(item) for item in context.source_items],  # type: ignore[attr-defined]
        "source_state": context.source_state.to_dict(), "target": context.target.to_dict(),  # type: ignore[attr-defined]
    }
    return _validate_entry(entry, context)


def cache_failure(exc: SourceStateCacheError) -> str:
    if exc.code == "semantic-cache-mismatch": return "conflict"
    if exc.code == "unsafe-cache-path": return "unsafe_path"
    return "io_error"


def _validate_entry(entry: dict[str, object], context: object) -> dict[str, object]:
    try:
        _validate_entry_fields(entry, context)
        capsule = Capsule.from_dict(entry["capsule"])  # type: ignore[arg-type]
        probe = ReadinessProbe.from_dict(entry["readiness_probe"])  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError) as exc:
        raise SourceStateCacheError("corrupt-cache-entry", "cache entry is corrupt") from exc
    if validate_capsule(capsule) or validate_readiness_probe(probe):
        raise SourceStateCacheError("corrupt-cache-entry", "cache entry is corrupt")
    if capsule.capsule_id != entry["manifest_sha256"] or probe.capsule_id != capsule.capsule_id:
        raise SourceStateCacheError("corrupt-cache-entry", "cache entry is corrupt")
    if capsule.source_state.to_dict() != context.source_state.to_dict():  # type: ignore[attr-defined]
        raise SourceStateCacheError("semantic-cache-mismatch", "cache entry does not match request")
    if capsule.target.to_dict() != context.target.to_dict():  # type: ignore[attr-defined]
        raise SourceStateCacheError("semantic-cache-mismatch", "cache entry does not match request")
    if capsule.records != context.records or capsule.atoms != _expected_atoms(context):  # type: ignore[attr-defined]
        raise SourceStateCacheError("semantic-cache-mismatch", "cache entry does not match request")
    if capsule.budget.to_dict() != context.budget.to_dict() or capsule.profile != context.profile:  # type: ignore[attr-defined]
        raise SourceStateCacheError("semantic-cache-mismatch", "cache entry does not match request")
    _validate_canon_md(entry, capsule)
    if probe.to_dict() != _expected_probe(context, capsule).to_dict():
        raise SourceStateCacheError("semantic-cache-mismatch", "cache entry does not match request")
    return entry


def _validate_entry_fields(entry: dict[str, object], context: object) -> None:
    expected = {"schema", "cache_key", "compiler_key", "budget_key", "source_state",
                "source_inputs", "target", "capsule", "canon_md_sha256",
                "manifest_sha256", "readiness_probe", "does_not_prove"}
    if set(entry) != expected or entry["schema"] != BOOTSTRAP_CACHE_SCHEMA:
        raise SourceStateCacheError("corrupt-cache-entry", "cache entry is corrupt")
    if entry["cache_key"] != context.cache_key or entry["compiler_key"] != context.compiler_key:  # type: ignore[attr-defined]
        raise SourceStateCacheError("semantic-cache-mismatch", "cache entry does not match request")
    if entry["budget_key"] != context.budget_key or entry["source_state"] != context.source_state.to_dict():  # type: ignore[attr-defined]
        raise SourceStateCacheError("semantic-cache-mismatch", "cache entry does not match request")
    expected_inputs = [source_item_dict(item) for item in context.source_items]  # type: ignore[attr-defined]
    if entry["source_inputs"] != expected_inputs or entry["target"] != context.target.to_dict():  # type: ignore[attr-defined]
        raise SourceStateCacheError("semantic-cache-mismatch", "cache entry does not match request")
    if not is_sha256_ref(entry["canon_md_sha256"]) or not is_sha256_ref(entry["manifest_sha256"]):
        raise SourceStateCacheError("corrupt-cache-entry", "cache entry is corrupt")
    _validate_does_not_prove(entry["does_not_prove"])


def _validate_canon_md(entry: dict[str, object], capsule: Capsule) -> None:
    try:
        expected = sha256_text(render_canon_md(capsule))
    except Exception as exc:
        raise SourceStateCacheError("corrupt-cache-entry", "cache entry is corrupt") from exc
    if entry["canon_md_sha256"] != expected:
        raise SourceStateCacheError("semantic-cache-mismatch", "cache entry does not match request")


def _validate_does_not_prove(value: object) -> None:
    if type(value) is not list:
        raise SourceStateCacheError("corrupt-cache-entry", "cache entry is corrupt")
    for item in value:
        if type(item) is not str or item == "":
            raise SourceStateCacheError("corrupt-cache-entry", "cache entry is corrupt")
        try:
            findings = scan_text(item, source_id="bootstrap-cache-does-not-prove")
        except SecretQuarantineError as exc:
            raise SourceStateCacheError("corrupt-cache-entry", "cache entry is corrupt") from exc
        if findings:
            raise SourceStateCacheError("corrupt-cache-entry", "cache entry is corrupt")


def _cache_result(entry: dict[str, object], status: str) -> BootstrapCacheResult:
    return BootstrapCacheResult(
        status, entry["cache_key"], Capsule.from_dict(entry["capsule"]),
        ReadinessProbe.from_dict(entry["readiness_probe"]), entry["manifest_sha256"],
        entry["canon_md_sha256"], tuple(entry["does_not_prove"]),  # type: ignore[arg-type]
    )


def _cache_store(context: object) -> object:
    state_root = getattr(context, "state_root", None)
    if state_root is None:
        return SourceStateCache(context.state_dir / "cache")  # type: ignore[attr-defined]
    return _BoundBootstrapCache(state_root)


class _BoundBootstrapCache:
    def __init__(self, state_root: object) -> None:
        self._state_root = state_root

    def current(self) -> dict[str, object] | None:
        root = self._open_cache(create=False)
        if root is None: return None
        try:
            pointer = _cache._read_object(root.ref, (), _cache._CURRENT, "current-pointer", required=False)
            if pointer is None: return None
            key = _cache._current_key(pointer)
            entry = _cache._read_object(root.ref, (_cache._BUNDLES,), _entry_name(key), "cache-entry", required=False)
            if entry is None: raise SourceStateCacheError("missing-current-entry", "current entry is missing")
            _verify_handle(root)
            return entry
        finally: root.close()

    def get(self, cache_key: str) -> dict[str, object] | None:
        root = self._open_cache(create=False)
        if root is None: return None
        try:
            entry = _cache._read_object(root.ref, (_cache._BUNDLES,), _entry_name(cache_key), "cache-entry", required=False)
            _verify_handle(root)
            return entry
        finally: root.close()

    def put(self, cache_key: str, entry: object) -> Path:
        root = self._open_cache(create=True)
        if root is None: raise SourceStateCacheError("unsafe-cache-path", "cache path is unsafe")
        body = _cache._canonical_text(_cache._snapshot_bundle(entry), code="invalid-cache-bundle")
        pointer = _cache._canonical_text({"cache_key": cache_key}, code="invalid-cache-bundle")
        entry_name = _entry_name(cache_key)
        try:
            _verify_handle(root)
            if os.name == "nt":
                _cache._win_put(root.ref, root.path, root.path / _cache._BUNDLES / entry_name, body, pointer)
            else:
                _cache._posix_put(root.ref, entry_name, body, pointer)
            try:
                _verify_handle(root)
            except SourceStateCacheError:
                _cleanup_written(root, entry_name)
                raise
            return root.path / _cache._BUNDLES / entry_name
        finally: root.close()

    def _open_cache(self, *, create: bool) -> object | None:
        try: return self._state_root.open_child_dir("cache", create=create)
        except Exception as exc:
            code = getattr(exc, "code", "unsafe-cache-path")
            raise SourceStateCacheError(code if code != "unsafe_path" else "unsafe-cache-path", "cache path is unsafe") from exc


def _verify_handle(root: object) -> None:
    try: root.verify_live()
    except Exception as exc:
        raise SourceStateCacheError("unsafe-cache-path", "cache path is unsafe") from exc


def _cleanup_written(root: object, entry_name: str) -> None:
    try:
        if os.name == "nt":
            _cleanup_win(root.path, entry_name)
        else:
            _cleanup_posix(root.ref, entry_name)
    except Exception as exc:
        raise SourceStateCacheError("unsafe-cache-path", "cache path is unsafe") from exc


def _cleanup_posix(root_fd: int, entry_name: str) -> None:
    _cache._posix_unlink(root_fd, _cache._CURRENT)
    bundles_fd = _cache._posix_open_dir(_cache._BUNDLES, root_fd)
    try: _cache._posix_unlink(bundles_fd, entry_name)
    finally: os.close(bundles_fd)


def _cleanup_win(root: Path, entry_name: str) -> None:
    for path in (root / _cache._CURRENT, root / _cache._BUNDLES / entry_name):
        try: path.unlink(missing_ok=True)
        except OSError: pass


def _entry_name(cache_key: object) -> str:
    return _cache._cache_digest(cache_key) + ".json"


def _expected_atoms(context: object) -> tuple[object, ...]:
    try:
        atoms = tuple(context.atoms) + tuple(atoms_from_records(tuple(context.records)))  # type: ignore[attr-defined]
        return tuple(sorted(atoms, key=atom_sort_key))
    except Exception as exc:
        raise SourceStateCacheError("semantic-cache-mismatch", "cache entry does not match request") from exc


def _expected_probe(context: object, capsule: Capsule) -> ReadinessProbe:
    return ReadinessProbe(
        _probe_id(context.target, context.source_state, context.profile),  # type: ignore[attr-defined]
        capsule.capsule_id,
        _readiness_target(context.adapter, context.target),  # type: ignore[attr-defined]
        critical_sets(capsule.atoms),
        {"format": "json", "required_fields": list(CRITICAL_SET_KEYS)},
        {"method": "exact-id-set-and-status-match", "pass_threshold": "all-critical"},
    )


def _probe_id(target: object, source_state: object, profile: str) -> str:
    payload = {"profile": profile, "source_state": source_state.to_dict(), "target": target.to_dict()}
    return "probe-" + sha256_text(canonical_json_text(payload)).removeprefix("sha256:")[:16]


def _readiness_target(descriptor: object, target: object) -> dict[str, object]:
    return {"adapter": target.adapter, "bootstrap": descriptor.bootstrap,
            "host_enforcement_observed": target.host_enforcement_observed,
            "integration_tier": target.integration_tier,
            "known_unknowns": list(descriptor.known_unknowns), "surface": target.surface}


__all__ = ["BOOTSTRAP_CACHE_SCHEMA", "BootstrapCacheResult", "cache_entry_from_bundle", "cache_failure", "select_cache"]
