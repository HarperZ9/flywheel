# SPDX-License-Identifier: MIT
"""Fail-closed oracle for 15/15 = 165/165 Open-Source Gold Standard and SBOM V3."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence

from harness.oss_gold_sbom_gate.sbom_v3_guards import (
    EXPECTED_REPOS,
    EXPECTED_SBOM_FILES,
    MIN_COMPONENTS,
    check_osi_policy,
    check_repo_entry,
    is_strict_int,
)
from harness.oss_gold_sbom_gate.sbom_v3_parser import (
    GoldSbomV3Bundle,
    parse_sbom_v3_manifest,
)


@dataclass(frozen=True)
class GoldSbomV3Policy:
    """Configurable thresholds for the 15-repo Gold Standard + SBOM V3 gate."""

    expected_repos: int = EXPECTED_REPOS
    expected_sbom_files: int = EXPECTED_SBOM_FILES
    min_components: int = MIN_COMPONENTS
    require_gold_165: bool = True
    check_on_disk: bool = False


@dataclass(frozen=True)
class GoldSbomV3Report:
    """Deterministic fail-closed verdict emitted by oss_gold_sbom_gate."""

    ok: bool
    verdict: str
    repos_verified: int
    sbom_files_verified: int
    total_components: int
    gold_score: str
    errors: tuple[str, ...]
    report_sha256: str


def _seal(
    ok: bool,
    repos: int,
    sboms: int,
    comps: int,
    gold: str,
    errs: list[str],
) -> GoldSbomV3Report:
    verdict = "PASS" if ok else "REJECT"
    body = {
        "ok": ok,
        "verdict": verdict,
        "repos_verified": repos,
        "sbom_files_verified": sboms,
        "total_components": comps,
        "gold_score": gold,
        "errors": list(errs),
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return GoldSbomV3Report(
        ok=ok,
        verdict=verdict,
        repos_verified=repos,
        sbom_files_verified=sboms,
        total_components=comps,
        gold_score=gold,
        errors=tuple(errs),
        report_sha256=digest,
    )


def _check_header(bundle: GoldSbomV3Bundle, pol: GoldSbomV3Policy, errs: list[str]) -> None:
    if bundle.schema != "harper-15repo-post-merge-sbom-v3-manifest/1":
        errs.append(f"invalid_schema:{bundle.schema}")
    if bundle.spdx_version != "SPDX-2.3":
        errs.append(f"invalid_spdx_version:{bundle.spdx_version}")
    if bundle.cyclonedx_version != "1.5":
        errs.append(f"invalid_cyclonedx_version:{bundle.cyclonedx_version}")
    if pol.require_gold_165:
        if bundle.gold_score != "165/165":
            errs.append(f"gold_score_incomplete:{bundle.gold_score}")
        if bundle.gold_perfect_repos != "15/15":
            errs.append(f"gold_repos_incomplete:{bundle.gold_perfect_repos}")
    if bundle.receipt_verdict is not None and bundle.receipt_verdict != "MATCH":
        errs.append(f"receipt_verdict_not_match:{bundle.receipt_verdict}")
    if bundle.receipt_exit_code is not None and bundle.receipt_exit_code != 0:
        errs.append(f"receipt_nonzero_exit:{bundle.receipt_exit_code}")
    errs.extend(check_osi_policy(bundle.osi_policy_audit))


def verify_gold_sbom_v3_bundle(
    bundle: GoldSbomV3Bundle,
    policy: GoldSbomV3Policy | None = None,
    sbom_root: Path | None = None,
) -> GoldSbomV3Report:
    """Verify the 15-repo Open-Source Gold Standard + SBOM V3 manifest fail-closed."""
    pol = policy or GoldSbomV3Policy()
    errs: list[str] = list(bundle.parse_errors)
    _check_header(bundle, pol, errs)
    seen: set[str] = set()
    repos_ok = 0
    total_comps = 0
    for rec in bundle.repositories:
        if rec.slug in seen:
            errs.append(f"duplicate_repo:{rec.slug}")
            continue
        seen.add(rec.slug)
        r_errs = check_repo_entry(rec, sbom_root=sbom_root, check_on_disk=pol.check_on_disk)
        if r_errs:
            errs.extend(r_errs)
            continue
        repos_ok += 1
        total_comps += rec.component_count
    sboms_ok = repos_ok * 2
    effective_comps = total_comps
    if is_strict_int(bundle.declared_components):
        if bundle.declared_components in (total_comps, total_comps + repos_ok):
            effective_comps = bundle.declared_components
        else:
            errs.append(f"declared_components_mismatch:{bundle.declared_components}!={total_comps}")
    if repos_ok != pol.expected_repos:
        errs.append(f"repo_count_mismatch:{repos_ok}!={pol.expected_repos}")
    if sboms_ok != pol.expected_sbom_files:
        errs.append(f"sbom_file_count_mismatch:{sboms_ok}!={pol.expected_sbom_files}")
    if effective_comps < pol.min_components:
        errs.append(f"component_count_below_min:{effective_comps}<{pol.min_components}")
    return _seal(not errs, repos_ok, sboms_ok, effective_comps, bundle.gold_score, errs)


def verify_gold_sbom_v3_file(
    manifest_path: Path,
    receipt_path: Path | None = None,
    policy: GoldSbomV3Policy | None = None,
    sbom_root: Path | None = None,
) -> GoldSbomV3Report:
    """Load and verify sbom_v3_manifest.json and optional engine-receipt/1 from disk."""
    man = json.loads(manifest_path.read_text(encoding="utf-8"))
    rec = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path else None
    root = sbom_root if sbom_root is not None else manifest_path.parent
    return verify_gold_sbom_v3_bundle(parse_sbom_v3_manifest(man, rec), policy=policy, sbom_root=root)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning 0 on PASS and 2 on REJECT."""
    parser = argparse.ArgumentParser(description="Verify 15/15 Gold Standard and SBOM V3.")
    parser.add_argument("manifest_json", type=Path)
    parser.add_argument("--receipt", type=Path, default=None)
    parser.add_argument("--sbom-root", type=Path, default=None)
    parser.add_argument("--check-on-disk", action="store_true")
    args = parser.parse_args(argv)
    pol = GoldSbomV3Policy(check_on_disk=args.check_on_disk)
    rep = verify_gold_sbom_v3_file(args.manifest_json, args.receipt, pol, args.sbom_root)
    print(json.dumps(asdict(rep), indent=2, sort_keys=True))
    return 0 if rep.ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
