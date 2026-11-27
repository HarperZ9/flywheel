# SPDX-License-Identifier: MIT
"""Pure-stdlib fail-closed verifier for Slice 34 ZK Pedersen and Slice 35 BuildOS-2.1."""

from harness.zk_pedersen_attest.zk_guards import (
    CLUSTER_CURVE_EQS,
    CLUSTER_PILLARS,
    REQUIRED_CLUSTER_ATTACKS,
    REQUIRED_ISAS,
    REQUIRED_ZK_ATTACKS,
    check_attack_controls,
    check_cluster_pillars,
    check_pedersen_conservation,
    is_sha256_hex,
    is_strict_int,
    rfc6962_mth,
)
from harness.zk_pedersen_attest.zk_oracle import (
    ZkPedersenPolicy,
    ZkPedersenReport,
    verify_zk_pedersen_bundle,
    verify_zk_pedersen_file,
)
from harness.zk_pedersen_attest.zk_parser import (
    ZkAttackRecord,
    ZkBinaryRecord,
    ZkPedersenBundle,
    parse_zk_payload,
    parse_zk_receipt,
)

__all__ = [
    "CLUSTER_CURVE_EQS",
    "CLUSTER_PILLARS",
    "REQUIRED_CLUSTER_ATTACKS",
    "REQUIRED_ISAS",
    "REQUIRED_ZK_ATTACKS",
    "ZkAttackRecord",
    "ZkBinaryRecord",
    "ZkPedersenBundle",
    "ZkPedersenPolicy",
    "ZkPedersenReport",
    "check_attack_controls",
    "check_cluster_pillars",
    "check_pedersen_conservation",
    "is_sha256_hex",
    "is_strict_int",
    "parse_zk_payload",
    "parse_zk_receipt",
    "rfc6962_mth",
    "verify_zk_pedersen_bundle",
    "verify_zk_pedersen_file",
]
