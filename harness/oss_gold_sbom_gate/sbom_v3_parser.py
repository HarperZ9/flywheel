# SPDX-License-Identifier: MIT
"""Strict fail-closed parser for 15-repo Open-Source Gold Standard + SBOM V3 manifests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harness.oss_gold_sbom_gate.sbom_v3_guards import is_strict_int, normalize_sha256


@dataclass(frozen=True)
class RepoSbomRecord:
    """Normalized repository entry from sbom_v3_manifest.json."""

    slug: str
    repo: str
    commit_sha: str
    license_id: str
    component_count: int
    spdx_file: str
    spdx_sha256: str
    cdx_file: str
    cdx_sha256: str


@dataclass(frozen=True)
class GoldSbomV3Bundle:
    """Normalized 15/15 Open-Source Gold Standard + SBOM V3 attestation bundle."""

    schema: str
    spdx_version: str
    cyclonedx_version: str
    declared_sbom_files: Any
    declared_repos: Any
    declared_components: Any
    gold_score: str
    gold_perfect_repos: str
    osi_policy_audit: dict[str, Any] | None
    repositories: tuple[RepoSbomRecord, ...]
    receipt_verdict: str | None = None
    receipt_exit_code: int | None = None
    parse_errors: tuple[str, ...] = ()


def _parse_repos(raw: Any, errs: list[str]) -> tuple[RepoSbomRecord, ...]:
    if not isinstance(raw, list):
        errs.append("repositories_not_list")
        return ()
    out: list[RepoSbomRecord] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"repo_not_dict_{idx}")
            continue
        cnt = item.get("component_count", -1)
        out.append(
            RepoSbomRecord(
                slug=str(item.get("slug", "")),
                repo=str(item.get("repo", "")),
                commit_sha=str(item.get("commit_sha", "")),
                license_id=str(item.get("license", "")),
                component_count=cnt if is_strict_int(cnt) else -1,
                spdx_file=str(item.get("spdx_file", "")),
                spdx_sha256=normalize_sha256(item.get("spdx_sha256", "")),
                cdx_file=str(item.get("cdx_file", "")),
                cdx_sha256=normalize_sha256(item.get("cdx_sha256", "")),
            )
        )
    return tuple(out)


def parse_sbom_v3_manifest(
    manifest: dict[str, Any],
    receipt: dict[str, Any] | None = None,
) -> GoldSbomV3Bundle:
    """Parse sbom_v3_manifest.json with optional engine-receipt/1 envelope."""
    errs: list[str] = []
    if not isinstance(manifest, dict):
        return GoldSbomV3Bundle(
            "", "", "", None, None, None, "", "", None, (), parse_errors=("manifest_not_dict",)
        )
    repos = _parse_repos(manifest.get("repositories"), errs)
    audit = manifest.get("osi_policy_audit")
    audit_map = audit if isinstance(audit, dict) else None
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
    return GoldSbomV3Bundle(
        schema=str(manifest.get("schema", "")),
        spdx_version=str(manifest.get("spdx_version", "")),
        cyclonedx_version=str(manifest.get("cyclonedx_version", "")),
        declared_sbom_files=manifest.get("total_sbom_files"),
        declared_repos=manifest.get("total_repos_covered"),
        declared_components=manifest.get("total_components_15repos"),
        gold_score=str(manifest.get("gold_standard_score", "")),
        gold_perfect_repos=str(manifest.get("gold_standard_perfect_repos", "")),
        osi_policy_audit=audit_map,
        repositories=repos,
        receipt_verdict=r_verdict,
        receipt_exit_code=r_exit,
        parse_errors=tuple(errs),
    )
