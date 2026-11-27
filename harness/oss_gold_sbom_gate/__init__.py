# SPDX-License-Identifier: MIT
"""Pure-stdlib fail-closed verifier for 15/15 Open-Source Gold Standard and SBOM V3."""

from harness.oss_gold_sbom_gate.sbom_v3_guards import (
    ALLOWED_OSI_LICENSES,
    EXPECTED_REPOS,
    EXPECTED_SBOM_FILES,
    FORBIDDEN_LICENSE_TOKENS,
    MIN_COMPONENTS,
    check_osi_policy,
    check_repo_entry,
    is_git_sha40,
    is_sha256_hex,
    is_strict_int,
)
from harness.oss_gold_sbom_gate.sbom_v3_oracle import (
    GoldSbomV3Policy,
    GoldSbomV3Report,
    verify_gold_sbom_v3_bundle,
    verify_gold_sbom_v3_file,
)
from harness.oss_gold_sbom_gate.sbom_v3_parser import (
    GoldSbomV3Bundle,
    RepoSbomRecord,
    parse_sbom_v3_manifest,
)

__all__ = [
    "ALLOWED_OSI_LICENSES",
    "EXPECTED_REPOS",
    "EXPECTED_SBOM_FILES",
    "FORBIDDEN_LICENSE_TOKENS",
    "GoldSbomV3Bundle",
    "GoldSbomV3Policy",
    "GoldSbomV3Report",
    "MIN_COMPONENTS",
    "RepoSbomRecord",
    "check_osi_policy",
    "check_repo_entry",
    "is_git_sha40",
    "is_sha256_hex",
    "is_strict_int",
    "parse_sbom_v3_manifest",
    "verify_gold_sbom_v3_bundle",
    "verify_gold_sbom_v3_file",
]
