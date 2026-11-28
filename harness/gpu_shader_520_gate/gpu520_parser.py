# SPDX-License-Identifier: MIT
"""Typed parsers for GPU 520-pack, RLVR v14, and Paper #8 manifests."""

from __future__ import annotations

from typing import Any

from harness.gpu_shader_520_gate.gpu520_guards import (
    Gpu520GateError,
    require_bool,
    require_dict,
    require_hex_64,
    require_int,
    require_list,
    require_prefixed_sha256,
    require_str,
    require_str_tuple,
)
from harness.gpu_shader_520_gate.gpu520_models import (
    Gpu520Manifest,
    Gpu520Report,
    Gpu520ShaderEntry,
    Paper8Manifest,
    RlvrArtifactEntry,
    RlvrV14Manifest,
)

GPU520_MANIFEST_SCHEMA = "buildlang-workstation-gpu-520pack/1"
GPU520_REPORT_SCHEMA = "wave163a-gpu-520pack-quingentennial/1"
RLVR_V14_SCHEMA = "jfc3p-rlvr-pack/v14"
PAPER8_SCHEMA = "harperz9.wave160a-arxiv-zenodo-paper8/1"


def parse_gpu_520_manifest(raw: dict[str, Any]) -> Gpu520Manifest:
    """Parse buildlang-workstation-gpu-520pack/1 manifest."""
    lbl = "gpu520_manifest"
    if require_str(raw, "schema", lbl) != GPU520_MANIFEST_SCHEMA:
        raise Gpu520GateError(f"{lbl}: unexpected schema")
    ptc_raw = require_dict(raw, "per_target_counts", lbl)
    ptc = {
        k: require_int(ptc_raw, k, f"{lbl}.per_target_counts", minimum=1)
        for k in ptc_raw
    }
    shaders: list[Gpu520ShaderEntry] = []
    for idx, entry in enumerate(require_list(raw, "shaders", lbl)):
        if not isinstance(entry, dict):
            raise Gpu520GateError(f"{lbl}: shaders[{idx}] must be an object")
        sl = f"{lbl}.shaders[{idx}]"
        shaders.append(
            Gpu520ShaderEntry(
                kernel=require_str(entry, "kernel", sl),
                target=require_str(entry, "target", sl),
                shader_bytes=require_int(entry, "shader_bytes", sl, minimum=1),
                shader_sha256=require_hex_64(entry, "shader_sha256", sl),
                cert_sha256=require_hex_64(entry, "cert_sha256", sl),
                rewrites=require_int(entry, "rewrites", sl, minimum=0),
                verify_cert=require_str(entry, "verify_cert", sl),
            )
        )
    return Gpu520Manifest(
        license=require_str(raw, "license", lbl),
        unique_kernels=require_int(raw, "unique_kernels", lbl, minimum=1),
        gpu_targets=require_int(raw, "gpu_targets", lbl, minimum=1),
        total_certified_shaders=require_int(
            raw, "total_certified_shaders", lbl, minimum=1
        ),
        per_target_counts=ptc,
        total_shader_bytes=require_int(raw, "total_shader_bytes", lbl, minimum=1),
        total_superopt_rewrites=require_int(
            raw, "total_superopt_rewrites", lbl, minimum=0
        ),
        shaders=tuple(shaders),
    )


def parse_gpu_520_report(raw: dict[str, Any]) -> Gpu520Report:
    """Parse wave163a-gpu-520pack-quingentennial/1 report."""
    lbl = "gpu520_report"
    if require_str(raw, "schema", lbl) != GPU520_REPORT_SCHEMA:
        raise Gpu520GateError(f"{lbl}: unexpected schema")
    vc_raw = require_dict(raw, "validation_counts", lbl)
    vc = {
        k: require_int(vc_raw, k, f"{lbl}.validation_counts", minimum=0) for k in vc_raw
    }
    pc_raw = require_dict(raw, "planted_controls", lbl)
    ctrl_flags: list[bool] = []
    for ck, cv in pc_raw.items():
        if not isinstance(cv, dict):
            raise Gpu520GateError(f"{lbl}: planted_controls.{ck} must be object")
        ctrl_flags.append(require_bool(cv, "rejected", f"{lbl}.planted_controls.{ck}"))
    return Gpu520Report(
        ok=require_bool(raw, "ok", lbl),
        verdict=require_str(raw, "verdict", lbl),
        new_kernels=require_int(raw, "new_kernels", lbl, minimum=1),
        targets=require_int(raw, "targets", lbl, minimum=1),
        new_certified_shaders=require_int(raw, "new_certified_shaders", lbl, minimum=1),
        combined_520pack_shaders=require_int(
            raw, "combined_520pack_shaders", lbl, minimum=1
        ),
        combined_unique_kernels=require_int(
            raw, "combined_unique_kernels", lbl, minimum=1
        ),
        combined_520pack_rewrites=require_int(
            raw, "combined_520pack_rewrites", lbl, minimum=0
        ),
        combined_520pack_bytes=require_int(
            raw, "combined_520pack_bytes", lbl, minimum=1
        ),
        validation_counts=vc,
        controls_rejected=tuple(ctrl_flags),
        controls_caught=require_int(raw, "controls_caught", lbl, minimum=0),
    )


def parse_rlvr_v14_manifest(raw: dict[str, Any]) -> RlvrV14Manifest:
    """Parse jfc3p-rlvr-pack/v14 manifest."""
    lbl = "rlvr_v14"
    if require_str(raw, "schema", lbl) != RLVR_V14_SCHEMA:
        raise Gpu520GateError(f"{lbl}: unexpected schema")
    cnt = require_dict(raw, "counts", lbl)
    cc_raw = require_dict(raw, "category_counts", lbl)
    cc = {
        k: require_int(cc_raw, k, f"{lbl}.category_counts", minimum=1) for k in cc_raw
    }
    art_raw = require_dict(raw, "artifacts", lbl)
    arts: list[RlvrArtifactEntry] = []
    for name, info in art_raw.items():
        if not isinstance(info, dict):
            raise Gpu520GateError(f"{lbl}: artifacts.{name} must be object")
        al = f"{lbl}.artifacts.{name}"
        rows = require_int(info, "rows", al, minimum=1) if "rows" in info else None
        arts.append(
            RlvrArtifactEntry(
                name=name,
                size_bytes=require_int(info, "bytes", al, minimum=1),
                sha256=require_prefixed_sha256(info, "sha256", al),
                rows=rows,
            )
        )
    pins_raw = require_dict(raw, "immutable_pins", lbl)
    pins = {
        k: require_prefixed_sha256(pins_raw, k, f"{lbl}.immutable_pins")
        for k in pins_raw
    }
    return RlvrV14Manifest(
        license=require_str(raw, "license", lbl),
        push_to_hub=require_bool(raw, "push_to_hub", lbl),
        categories=require_int(cnt, "categories", f"{lbl}.counts", minimum=1),
        total_tasks=require_int(cnt, "total_tasks", f"{lbl}.counts", minimum=1),
        train_tasks=require_int(cnt, "train_tasks", f"{lbl}.counts", minimum=1),
        eval_tasks=require_int(cnt, "eval_tasks", f"{lbl}.counts", minimum=1),
        new_v14_tasks=require_int(cnt, "new_v14_tasks", f"{lbl}.counts", minimum=1),
        v13_preserved_tasks=require_int(
            cnt, "v13_preserved_tasks", f"{lbl}.counts", minimum=1
        ),
        category_counts=cc,
        artifacts=tuple(arts),
        immutable_pins=pins,
    )


def parse_paper8_manifest(raw: dict[str, Any]) -> Paper8Manifest:
    """Parse harperz9.wave160a-arxiv-zenodo-paper8/1 manifest."""
    lbl = "paper8"
    if require_str(raw, "schema", lbl) != PAPER8_SCHEMA:
        raise Gpu520GateError(f"{lbl}: unexpected schema")
    deliv = require_dict(raw, "deliverables", lbl)
    cids_raw = require_list(raw, "verified_catalogue_ids", lbl)
    cids: list[int] = []
    for item in cids_raw:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise Gpu520GateError(f"{lbl}: invalid catalogue id {item!r}")
        cids.append(item)
    return Paper8Manifest(
        paper_license=require_str(raw, "paper_license", lbl),
        code_licenses=require_str_tuple(raw, "code_licenses", lbl),
        orcid=require_str(raw, "orcid", lbl),
        send_policy=require_str(raw, "send_policy", lbl),
        prior_untouched=require_bool(raw, "prior_papers_and_packs_untouched", lbl),
        arxiv_categories=require_str_tuple(raw, "arxiv_categories", lbl),
        verified_catalogue_ids=tuple(cids),
        paper_words=require_int(deliv, "paper_words", f"{lbl}.deliverables", minimum=1),
        paper_pages=require_int(deliv, "paper_pages", f"{lbl}.deliverables", minimum=1),
        paper_bytes=require_int(deliv, "paper_bytes", f"{lbl}.deliverables", minimum=1),
        page_pngs=require_str_tuple(deliv, "page_pngs", f"{lbl}.deliverables"),
    )
