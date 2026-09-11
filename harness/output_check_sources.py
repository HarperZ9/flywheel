"""Source custody helpers for native output.check."""
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from pathlib import Path

from .domain_packs import PACKS


class OutputCheckError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PinnedAuthoritySource:
    data: bytes
    mode: int
    path: Path


@dataclass(frozen=True)
class PinnedAuthoritySources:
    sources: dict[str, PinnedAuthoritySource]

    @property
    def bytes_by_declared(self) -> dict[str, bytes]:
        return {declared: source.data
                for declared, source in self.sources.items()}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def contained(root: Path, rel: str, *, must_exist: bool) -> Path:
    if rel.startswith(("/", "\\")) or ":" in rel or "\\" in rel:
        raise OutputCheckError("INVALID_REQUEST")
    target = (root / rel).resolve()
    basis = root.resolve()
    if target != basis and basis not in target.parents:
        raise OutputCheckError("INVALID_REQUEST")
    if must_exist and not target.exists():
        raise OutputCheckError("SOURCE_CONTEXT_FAILED")
    return target


def source_file(spec: dict, root: Path) -> tuple[Path, bytes]:
    if spec.get("kind") != "workspace-file":
        raise OutputCheckError("INVALID_REQUEST")
    path = contained(root, spec.get("path", ""), must_exist=True)
    try:
        data = path.read_bytes()
    except OSError:
        raise OutputCheckError("SOURCE_CONTEXT_FAILED") from None
    if not path.is_file() or sha256_bytes(data) != spec.get("sha256"):
        raise OutputCheckError("SOURCE_DRIFT")
    return path, data


def workspace_dir(spec: dict, root: Path) -> Path:
    if spec.get("kind") != "workspace-dir":
        raise OutputCheckError("INVALID_REQUEST")
    path = contained(root, spec.get("path", ""), must_exist=True)
    if not path.is_dir():
        raise OutputCheckError("SOURCE_CONTEXT_FAILED")
    return path


def run_artifact(spec: dict, run_root: Path) -> Path:
    if spec.get("kind") != "run-artifact":
        raise OutputCheckError("INVALID_REQUEST")
    path = contained(run_root, spec.get("path", ""), must_exist=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _authority_path(base_dir: Path, rel: object, repo_root: Path,
                    *, must_exist: bool) -> Path | None:
    if type(rel) is not str:
        raise OutputCheckError("INVALID_REQUEST")
    try:
        path = contained(base_dir, rel, must_exist=must_exist)
    except OutputCheckError:
        if must_exist:
            raise
        return None
    repo = repo_root.resolve()
    resolved = path.resolve()
    if resolved != repo and repo not in resolved.parents:
        raise OutputCheckError("INVALID_REQUEST")
    if must_exist and not resolved.is_file():
        raise OutputCheckError("SOURCE_CONTEXT_FAILED")
    return resolved


def _maybe_authority_path(base_dir: Path, rel: object,
                          repo_root: Path) -> Path | None:
    path = _authority_path(base_dir, rel, repo_root, must_exist=False)
    return path if path is not None and path.is_file() else None


def _authority_source_bindings(contract_doc: dict, base_dir: Path,
                               repo_root: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    pack = contract_doc.get("pack", "")
    if type(pack) is str and pack and pack not in PACKS:
        pack_path = _maybe_authority_path(base_dir, pack, repo_root)
        if pack_path is not None:
            paths[pack] = pack_path
    authorities = contract_doc.get("authorities") or {}
    if type(authorities) is not dict:
        return paths
    for spec in authorities.values():
        if type(spec) is not dict:
            continue
        if spec.get("kind") == "table":
            declared = spec.get("path")
            paths[declared] = _authority_path(base_dir, declared, repo_root,
                                              must_exist=True)
        if spec.get("kind") == "command":
            argv = spec.get("argv")
            if type(argv) is list:
                for part in argv:
                    path = (_maybe_authority_path(base_dir, part, repo_root)
                            if type(part) is str else None)
                    if path is not None:
                        paths[part] = path
    return paths


def pinned_authority_sources(operation: dict, contract_doc: dict,
                             *, base_dir: Path,
                             repo_root: Path) -> PinnedAuthoritySources:
    supplied_refs = operation.get("authority_sources")
    if type(supplied_refs) is not list:
        raise OutputCheckError("INVALID_REQUEST")
    supplied_by_path: dict[Path, PinnedAuthoritySource] = {}
    for source in supplied_refs:
        path, data = source_file(source, repo_root)
        resolved = path.resolve()
        if resolved in supplied_by_path:
            raise OutputCheckError("INVALID_REQUEST")
        supplied_by_path[resolved] = PinnedAuthoritySource(
            data=data, mode=resolved.stat().st_mode & 0o777, path=resolved)
    bindings = _authority_source_bindings(contract_doc, base_dir, repo_root)
    if set(supplied_by_path) != set(bindings.values()):
        raise OutputCheckError("SOURCE_DRIFT")
    return PinnedAuthoritySources(
        {declared: supplied_by_path[path]
         for declared, path in bindings.items()})


def command_custody_contract(contract_doc: dict, *, base_dir: Path,
                             repo_root: Path, run_root: Path,
                             operation_ref: str,
                             pinned_sources: PinnedAuthoritySources) -> dict:
    copied = copy.deepcopy(contract_doc)
    authorities = copied.get("authorities") or {}
    if type(authorities) is not dict:
        return copied
    custody: dict[str, Path] = {}

    def copy_source(declared: str, source: PinnedAuthoritySource) -> Path:
        if declared not in custody:
            rel = source.path.relative_to(repo_root.resolve()).as_posix()
            digest = sha256_bytes(source.data)[:16]
            target = run_artifact({"kind": "run-artifact",
                                   "path": "output-check/"
                                   f"{operation_ref}/authority-sources/"
                                   f"{digest}/{rel}"}, run_root)
            target.write_bytes(source.data)
            try:
                target.chmod(source.mode)
            except OSError:
                pass
            custody[declared] = target
        return custody[declared]

    for spec in authorities.values():
        if type(spec) is not dict or spec.get("kind") != "command":
            continue
        argv = spec.get("argv")
        if type(argv) is not list:
            continue
        rewritten = []
        for part in argv:
            source = (pinned_sources.sources.get(part)
                      if type(part) is str else None)
            rewritten.append(str(copy_source(part, source))
                             if source is not None else str(part))
        spec["argv"] = rewritten
    return copied
