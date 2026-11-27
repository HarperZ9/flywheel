# SPDX-License-Identifier: MIT
"""Strict fail-closed parser for GPU 400-pack manifests, RLVR v12, and receipts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harness.gpu_400pack_gate.pack400_guards import is_strict_int, normalize_sha256


@dataclass(frozen=True)
class Shader400Record:
    """Normalized record for one certified shader in the 400-pack."""

    batch: str
    kernel: str
    target: str
    shader_bytes: int
    shader_sha256: str
    cert_sha256: str
    rewrites: int
    verify_cert: str


@dataclass(frozen=True)
class Gpu400RlvrBundle:
    """Normalized Quadricentennial GPU 400-pack + optional RLVR v12 bundle."""

    schema: str
    license_id: str
    declared_unique_kernels: Any
    declared_total_shaders: Any
    declared_total_bytes: Any
    declared_total_rewrites: Any
    shaders: tuple[Shader400Record, ...]
    rlvr_manifest: dict[str, Any] | None = None
    receipt_verdict: str | None = None
    receipt_exit_code: int | None = None
    parse_errors: tuple[str, ...] = ()


def _parse_shaders(raw: Any, errs: list[str]) -> tuple[Shader400Record, ...]:
    if not isinstance(raw, list):
        errs.append("shaders_not_list")
        return ()
    out: list[Shader400Record] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"shader_not_dict_{idx}")
            continue
        sb = item.get("shader_bytes", -1)
        rw = item.get("rewrites", -1)
        out.append(
            Shader400Record(
                str(item.get("batch", "")),
                str(item.get("kernel", "")),
                str(item.get("target", "")),
                sb if is_strict_int(sb) else -1,
                normalize_sha256(item.get("shader_sha256", "")),
                normalize_sha256(item.get("cert_sha256", "")),
                rw if is_strict_int(rw) else -1,
                str(item.get("verify_cert", "")),
            )
        )
    return tuple(out)


def parse_gpu_400pack_bundle(
    manifest: dict[str, Any],
    rlvr_manifest: dict[str, Any] | None = None,
    receipt: dict[str, Any] | None = None,
) -> Gpu400RlvrBundle:
    """Parse gpu_400pack_manifest.json with optional v12_rlvr_manifest.json and receipt."""
    errs: list[str] = []
    if not isinstance(manifest, dict):
        return Gpu400RlvrBundle("", "", None, None, None, None, (), parse_errors=("manifest_not_dict",))
    shaders = _parse_shaders(manifest.get("shaders"), errs)
    rlvr_map: dict[str, Any] | None = None
    if rlvr_manifest is not None:
        if isinstance(rlvr_manifest, dict):
            rlvr_map = rlvr_manifest
        else:
            errs.append("rlvr_manifest_not_dict")
    r_verdict: str | None = None
    r_exit: int | None = None
    if receipt is not None:
        if not isinstance(receipt, dict):
            errs.append("receipt_not_dict")
        else:
            r_verdict = str(receipt.get("verdict", ""))
            oracle = receipt.get("oracle") if isinstance(receipt.get("oracle"), dict) else {}
            ec = oracle.get("exit_code", -1)
            r_exit = ec if is_strict_int(ec) else -1
    return Gpu400RlvrBundle(
        schema=str(manifest.get("schema", "")),
        license_id=str(manifest.get("license", "")),
        declared_unique_kernels=manifest.get("unique_kernels"),
        declared_total_shaders=manifest.get("total_certified_shaders"),
        declared_total_bytes=manifest.get("total_shader_bytes"),
        declared_total_rewrites=manifest.get("total_superopt_rewrites"),
        shaders=shaders,
        rlvr_manifest=rlvr_map,
        receipt_verdict=r_verdict,
        receipt_exit_code=r_exit,
        parse_errors=tuple(errs),
    )
