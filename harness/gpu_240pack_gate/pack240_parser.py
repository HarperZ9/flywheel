# SPDX-License-Identifier: MIT
"""Strict fail-closed parser for GPU 240-pack manifests, reports, and receipts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harness.gpu_240pack_gate.pack240_guards import is_strict_int, normalize_sha256


@dataclass(frozen=True)
class Shader240Record:
    """Normalized record for one certified shader in the 240-pack."""

    batch: str
    kernel: str
    target: str
    shader_bytes: int
    shader_sha256: str
    cert_sha256: str
    rewrites: int
    verify_cert: str


@dataclass(frozen=True)
class Gpu240Bundle:
    """Normalized GPU 240-pack attestation bundle."""

    schema: str
    license_id: str
    declared_unique_kernels: Any
    declared_total_shaders: Any
    declared_total_bytes: Any
    declared_total_rewrites: Any
    shaders: tuple[Shader240Record, ...]
    report_ok: Any = None
    report_verdict: str | None = None
    validation_counts: dict[str, Any] | None = None
    planted_controls: dict[str, Any] | None = None
    receipt_verdict: str | None = None
    receipt_exit_code: int | None = None
    parse_errors: tuple[str, ...] = ()


def _parse_shaders(raw: Any, errs: list[str]) -> tuple[Shader240Record, ...]:
    if not isinstance(raw, list):
        errs.append("shaders_not_list")
        return ()
    out: list[Shader240Record] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"shader_not_dict_{idx}")
            continue
        sb = item.get("shader_bytes", -1)
        rw = item.get("rewrites", -1)
        out.append(
            Shader240Record(
                batch=str(item.get("batch", "")),
                kernel=str(item.get("kernel", "")),
                target=str(item.get("target", "")),
                shader_bytes=sb if is_strict_int(sb) else -1,
                shader_sha256=normalize_sha256(item.get("shader_sha256", "")),
                cert_sha256=normalize_sha256(item.get("cert_sha256", "")),
                rewrites=rw if is_strict_int(rw) else -1,
                verify_cert=str(item.get("verify_cert", "")),
            )
        )
    return tuple(out)


def parse_gpu_240pack_manifest(
    manifest: dict[str, Any],
    report: dict[str, Any] | None = None,
    receipt: dict[str, Any] | None = None,
) -> Gpu240Bundle:
    """Parse gpu_240pack_manifest.json with optional report and engine-receipt/1."""
    errs: list[str] = []
    if not isinstance(manifest, dict):
        return Gpu240Bundle("", "", None, None, None, None, (), parse_errors=("manifest_not_dict",))
    shaders = _parse_shaders(manifest.get("shaders"), errs)
    rep_ok: Any = None
    rep_verdict: str | None = None
    val_counts: dict[str, Any] | None = None
    planted: dict[str, Any] | None = None
    if report is not None:
        if not isinstance(report, dict):
            errs.append("report_not_dict")
        else:
            rep_ok = report.get("ok")
            rep_verdict = str(report.get("verdict", ""))
            vc = report.get("validation_counts")
            val_counts = vc if isinstance(vc, dict) else {}
            pc = report.get("planted_controls")
            planted = pc if isinstance(pc, dict) else {}
    rec_verdict: str | None = None
    rec_exit: int | None = None
    if receipt is not None:
        if not isinstance(receipt, dict):
            errs.append("receipt_not_dict")
        else:
            rec_verdict = str(receipt.get("verdict", ""))
            oracle = receipt.get("oracle") if isinstance(receipt.get("oracle"), dict) else {}
            ec = oracle.get("exit_code", -1)
            rec_exit = ec if is_strict_int(ec) else -1
    return Gpu240Bundle(
        schema=str(manifest.get("schema", "")),
        license_id=str(manifest.get("license", "")),
        declared_unique_kernels=manifest.get("unique_kernels"),
        declared_total_shaders=manifest.get("total_certified_shaders"),
        declared_total_bytes=manifest.get("total_shader_bytes"),
        declared_total_rewrites=manifest.get("total_superopt_rewrites"),
        shaders=shaders,
        report_ok=rep_ok,
        report_verdict=rep_verdict,
        validation_counts=val_counts,
        planted_controls=planted,
        receipt_verdict=rec_verdict,
        receipt_exit_code=rec_exit,
        parse_errors=tuple(errs),
    )
