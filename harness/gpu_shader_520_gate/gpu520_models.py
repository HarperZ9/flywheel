# SPDX-License-Identifier: MIT
"""Typed data models for Quingentennial 520 GPU, RLVR v14, and Paper #8 verification."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Gpu520ShaderEntry:
    kernel: str
    target: str
    shader_bytes: int
    shader_sha256: str
    cert_sha256: str
    rewrites: int
    verify_cert: str


@dataclass(frozen=True)
class Gpu520Manifest:
    license: str
    unique_kernels: int
    gpu_targets: int
    total_certified_shaders: int
    per_target_counts: dict[str, int]
    total_shader_bytes: int
    total_superopt_rewrites: int
    shaders: tuple[Gpu520ShaderEntry, ...]


@dataclass(frozen=True)
class Gpu520Report:
    ok: bool
    verdict: str
    new_kernels: int
    targets: int
    new_certified_shaders: int
    combined_520pack_shaders: int
    combined_unique_kernels: int
    combined_520pack_rewrites: int
    combined_520pack_bytes: int
    validation_counts: dict[str, int]
    controls_rejected: tuple[bool, ...]
    controls_caught: int


@dataclass(frozen=True)
class RlvrArtifactEntry:
    name: str
    size_bytes: int
    sha256: str
    rows: int | None


@dataclass(frozen=True)
class RlvrV14Manifest:
    license: str
    push_to_hub: bool
    categories: int
    total_tasks: int
    train_tasks: int
    eval_tasks: int
    new_v14_tasks: int
    v13_preserved_tasks: int
    category_counts: dict[str, int]
    artifacts: tuple[RlvrArtifactEntry, ...]
    immutable_pins: dict[str, str]


@dataclass(frozen=True)
class Paper8Manifest:
    paper_license: str
    code_licenses: tuple[str, ...]
    orcid: str
    send_policy: str
    prior_untouched: bool
    arxiv_categories: tuple[str, ...]
    verified_catalogue_ids: tuple[int, ...]
    paper_words: int
    paper_pages: int
    paper_bytes: int
    page_pngs: tuple[str, ...]


@dataclass(frozen=True)
class QuingentennialBundle:
    gpu_manifest: Gpu520Manifest
    gpu_report: Gpu520Report
    rlvr_v14: RlvrV14Manifest
    paper8: Paper8Manifest
