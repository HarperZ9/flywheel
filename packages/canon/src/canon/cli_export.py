from __future__ import annotations

from pathlib import Path
from typing import TextIO

from .adapter import descriptor_for, validate_adapter_descriptor
from .canonical_json import canonical_json_text, sha256_bytes, sha256_text
from .capsule import CapsuleBuildError
from .cli_artifacts import ARTIFACT_NAMES, ArtifactError, WorkspaceRoot, checked_workspace, output_relative, publish_artifacts
from .cli_export_support import (
    ExportCliError,
    checked_output_path,
    checked_region_path,
    relative_path,
    write_stdout,
)
from .cli_compile import CompileCliError, bundle_artifacts, compile_bundle_for_cli
from .export_output import write_output_file
from .cli_format import make_result, write_result
from .region import RegionError, extract_region, splice_region
from .registry import ROOT_WORKSPACE, Surface, pool_for
from .secret_quarantine import scan_text
from .surface import SurfaceError, render_surface
from .textblock import RenderRefused
from .undo import UndoError, UndoReceipt, UndoStore
from .undo_io import read_workspace_file, replace_workspace_file

_FORMATS = frozenset({"canon-md", "capsule-json", "readiness-json", "bundle", "region"})
_LOCAL_SURFACES = {
    "codex-cli": Surface("codex", "workspace", ROOT_WORKSPACE, "AGENTS.md"),
    "claude-code": Surface("claude-code", "workspace", ROOT_WORKSPACE, "CLAUDE.md"),
}


def run_export_command(
    parsed: object,
    *,
    stdin: TextIO | None,
    stdout: TextIO,
    stderr: TextIO,
    color: bool,
) -> int:
    try:
        fmt = _validated_format(parsed)
        _validate_sinks(parsed, fmt)
        descriptor = _descriptor(parsed.target)  # type: ignore[attr-defined]
        if fmt == "region" and descriptor.adapter_id not in _LOCAL_SURFACES:
            raise ExportCliError("unsupported_lifecycle")
        workspace = checked_workspace(parsed.workspace)  # type: ignore[attr-defined]
        bundle, data = compile_bundle_for_cli(parsed, workspace=workspace, stdin=stdin, scan_sources=True)
        result = _run_export(parsed, fmt, bundle, data, workspace, stdout)
        if result is None:
            return 0
        return write_result(result, stdout=stdout, stderr=stderr, json_output=parsed.json_output, color=color)  # type: ignore[attr-defined]
    except (ArtifactError, CompileCliError, CapsuleBuildError, ExportCliError, UndoError) as exc:
        code = _failure_code(exc)
        result = make_result(ok=False, command="export", failure_code=code, message=_failure_message(code))
        return write_result(result, stdout=stdout, stderr=stderr, json_output=_json_output(parsed), color=color)


def run_undo_command(parsed: object, *, stdout: TextIO, stderr: TextIO, color: bool) -> int:
    try:
        workspace = checked_workspace(parsed.workspace)  # type: ignore[attr-defined]
        store = UndoStore(workspace)
        if parsed.undo_command == "list":  # type: ignore[attr-defined]
            data = {"command": "undo", "receipts": store.list_metadata(), "workspace": "."}
            result = make_result(ok=True, command="undo", failure_code="ok", message="undo receipts", data=data)
        else:
            applied = store.apply(parsed.receipt_id, workspace=workspace)  # type: ignore[attr-defined]
            data = {"command": "undo", "workspace": ".", **applied.to_metadata()}
            result = make_result(ok=True, command="undo", failure_code="ok", message="undo applied", data=data)
        return write_result(result, stdout=stdout, stderr=stderr, json_output=parsed.json_output, color=color)  # type: ignore[attr-defined]
    except (ArtifactError, UndoError) as exc:
        code = _failure_code(exc)
        result = make_result(ok=False, command="undo", failure_code=code, message=_failure_message(code))
        return write_result(result, stdout=stdout, stderr=stderr, json_output=_json_output(parsed), color=color)


def render_region_inner(bundle: object, surface: Surface) -> str:
    pool = list(bundle.capsule.records)  # type: ignore[attr-defined]
    return render_surface(pool_for(surface, pool), surface.scope)


def replace_region_file(
    path: Path,
    expected_hash: str,
    postimage: bytes,
    *,
    workspace: WorkspaceRoot | None = None,
    relative: str | None = None,
) -> None:
    _ = path
    if workspace is None or relative is None:
        raise UndoError("unsafe_path")
    replace_workspace_file(workspace, relative, expected_hash, postimage)


def _run_export(parsed: object, fmt: str, bundle: object, data: dict, workspace: WorkspaceRoot, stdout: TextIO):
    if fmt in {"canon-md", "capsule-json", "readiness-json"} and parsed.out is None:  # type: ignore[attr-defined]
        if parsed.json_output:  # type: ignore[attr-defined]
            return _success_result(fmt, bundle, data)
        write_stdout(stdout, _payload_text(fmt, bundle))
        return None
    if fmt in {"canon-md", "capsule-json", "readiness-json"}:
        return _write_file_result(parsed.out, fmt, bundle, data, workspace)  # type: ignore[attr-defined]
    if fmt == "bundle":
        artifacts = bundle_artifacts(bundle)
        status = publish_artifacts(parsed.out, workspace=workspace, artifacts=artifacts)  # type: ignore[attr-defined]
        meta = _metadata(fmt, bundle, data)
        meta["out"] = output_relative(parsed.out, workspace=workspace)  # type: ignore[attr-defined]
        meta["write_status"] = status
        return make_result(ok=True, command="export", failure_code="ok", message="export complete", data=meta)
    return _apply_region_result(parsed, bundle, data, workspace)


def _write_file_result(raw_out: object, fmt: str, bundle: object, data: dict, workspace: WorkspaceRoot):
    payload = _payload_text(fmt, bundle).encode("utf-8")
    path = checked_output_path(raw_out, workspace)
    relative = relative_path(path, workspace.path)
    status = write_output_file(workspace, relative, payload)
    meta = _metadata(fmt, bundle, data)
    meta["out"] = relative
    meta["write_status"] = status
    return make_result(ok=True, command="export", failure_code="ok", message="export complete", data=meta)


def _apply_region_result(parsed: object, bundle: object, data: dict, workspace: WorkspaceRoot):
    surface = _LOCAL_SURFACES[bundle.capsule.target.adapter]  # type: ignore[attr-defined]
    target = checked_region_path(parsed.apply_region, workspace, expected=surface.relative_path)  # type: ignore[attr-defined]
    preimage = read_workspace_file(workspace, surface.relative_path)
    pre_hash = sha256_bytes(preimage)
    try:
        host = preimage.decode("utf-8")
        region = extract_region(host)
        if not region.present or region.scope != surface.scope:
            raise ExportCliError("conflict")
        inner = render_region_inner(bundle, surface)
        post_text = splice_region(host, inner)
    except UnicodeDecodeError as exc:
        raise ExportCliError("invalid_args") from exc
    except (RegionError, SurfaceError, RenderRefused) as exc:
        raise ExportCliError("conflict") from exc
    _scan_host(host, post_text)
    postimage = post_text.encode("utf-8")
    post_hash = sha256_bytes(postimage)
    meta = _metadata("region", bundle, data)
    meta["changed"] = post_hash != pre_hash
    meta["target_path"] = surface.relative_path
    if post_hash == pre_hash:
        meta["already_current"] = True
        return make_result(ok=True, command="export", failure_code="ok", message="export complete", data=meta)
    receipt = _receipt(bundle, data, surface, host, post_hash, sha256_text(inner))
    meta["receipt_id"] = receipt.receipt_id
    meta["receipt_status"] = UndoStore(workspace).write(receipt)
    replace_region_file(target, pre_hash, postimage, workspace=workspace, relative=surface.relative_path)
    return make_result(ok=True, command="export", failure_code="ok", message="export complete", data=meta)


def _receipt(bundle: object, data: dict, surface: Surface, preimage: str, post_hash: str, region_hash: str) -> UndoReceipt:
    return UndoReceipt.for_region(
        target_path=surface.relative_path,
        target_adapter=bundle.capsule.target.adapter,  # type: ignore[attr-defined]
        target_surface=surface.relative_path,
        scope=surface.scope,
        preimage_text=preimage,
        postimage_sha256=post_hash,
        postimage_region_sha256=region_hash,
        capsule_id=bundle.capsule.capsule_id,  # type: ignore[attr-defined]
        manifest_sha256=sha256_bytes(bundle.manifest_bytes),  # type: ignore[attr-defined]
        source_state=bundle.capsule.source_state.to_dict(),  # type: ignore[attr-defined]
    )


def _payload_text(fmt: str, bundle: object) -> str:
    if fmt == "canon-md":
        return bundle.canon_md  # type: ignore[return-value,attr-defined]
    if fmt == "capsule-json":
        return bundle.manifest_bytes.decode("utf-8")  # type: ignore[attr-defined]
    return canonical_json_text(bundle.readiness_probe.to_dict())  # type: ignore[attr-defined]


def _metadata(fmt: str, bundle: object, data: dict) -> dict[str, object]:
    readiness = canonical_json_text(bundle.readiness_probe.to_dict()).encode("utf-8")  # type: ignore[attr-defined]
    canon_md = bundle.canon_md.encode("utf-8")  # type: ignore[attr-defined]
    manifest = bundle.manifest_bytes  # type: ignore[attr-defined]
    return {
        "adapter": bundle.capsule.target.adapter,  # type: ignore[attr-defined]
        "artifacts": list(ARTIFACT_NAMES),
        "canon_md_bytes": len(canon_md),
        "canon_md_sha256": sha256_bytes(canon_md),
        "capsule_id": bundle.capsule.capsule_id,  # type: ignore[attr-defined]
        "capsule_json_bytes": len(manifest),
        "capsule_json_sha256": sha256_bytes(manifest),
        "command": "export",
        "format": fmt,
        "manifest_sha256": sha256_bytes(manifest),
        "profile": data["profile"],
        "readiness_json_bytes": len(readiness),
        "readiness_json_sha256": sha256_bytes(readiness),
        "source_state_sha256": bundle.capsule.source_state.records_digest,  # type: ignore[attr-defined]
        "target": bundle.capsule.target.adapter,  # type: ignore[attr-defined]
        "workspace": ".",
    }


def _success_result(fmt: str, bundle: object, data: dict):
    return make_result(ok=True, command="export", failure_code="ok", message="export complete", data=_metadata(fmt, bundle, data))


def _validated_format(parsed: object) -> str:
    fmt = getattr(parsed, "format", None)
    if type(fmt) is not str or fmt not in _FORMATS:
        raise ExportCliError("invalid_args")
    return fmt


def _validate_sinks(parsed: object, fmt: str) -> None:
    out = getattr(parsed, "out", None)
    apply_region = getattr(parsed, "apply_region", None)
    if out is not None and apply_region is not None:
        raise ExportCliError("invalid_args")
    if fmt == "bundle" and out is None:
        raise ExportCliError("invalid_args")
    if fmt == "region" and apply_region is None:
        raise ExportCliError("invalid_args")
    if fmt != "region" and apply_region is not None:
        raise ExportCliError("invalid_args")
    if fmt == "bundle" and apply_region is not None:
        raise ExportCliError("invalid_args")


def _descriptor(target_id: object):
    if type(target_id) is not str:
        raise ExportCliError("invalid_args")
    try:
        descriptor = descriptor_for(target_id)
    except KeyError as exc:
        raise ExportCliError("invalid_args") from exc
    if validate_adapter_descriptor(descriptor) or "CANON.md" not in descriptor.target_surfaces:
        raise ExportCliError("invalid_args")
    if descriptor.integration_tier == "unsupported":
        raise ExportCliError("unsupported_lifecycle")
    return descriptor


def _scan_host(preimage: str, postimage: str) -> None:
    try:
        findings = tuple(scan_text(preimage, source_id="host-preimage"))
        findings += tuple(scan_text(postimage, source_id="host-postimage"))
    except Exception as exc:
        raise ExportCliError("invalid_args") from exc
    if findings:
        raise ExportCliError("secret_quarantine")


def _failure_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    return code if type(code) is str else "invalid_args"


def _failure_message(code: str) -> str:
    return {
        "conflict": "export conflict",
        "io_error": "export I/O failed",
        "secret_quarantine": "export source quarantined",
        "unsafe_path": "unsafe export path",
        "unsupported_lifecycle": "unsupported export target",
    }.get(code, "invalid export input")


def _json_output(parsed: object) -> bool:
    return getattr(parsed, "json_output", False) is True


__all__ = ["render_region_inner", "replace_region_file", "run_export_command", "run_undo_command"]
