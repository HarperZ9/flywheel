# SPDX-License-Identifier: MIT
"""Pure-stdlib fail-closed verifier for Slice 31 Zero-C QUIC-Lite and CAP_NET_PEER firewall."""

from harness.quic_firewall_attest.quic_guards import (
    REPLAY_WINDOW_BITS,
    REQUIRED_ISAS,
    REQUIRED_NET_ATTACKS,
    check_cap_net_peer_rules,
    check_net_attacks,
    check_replay_window_sequence,
    is_sha256_hex,
    is_strict_int,
)
from harness.quic_firewall_attest.quic_oracle import (
    QuicFirewallPolicy,
    QuicFirewallReport,
    verify_quic_firewall_bundle,
    verify_quic_firewall_file,
)
from harness.quic_firewall_attest.quic_parser import (
    FirewallRuleRecord,
    NetAttackRecord,
    QuicBinaryRecord,
    QuicFirewallBundle,
    parse_quic_payload,
    parse_quic_receipt,
)

__all__ = [
    "FirewallRuleRecord",
    "NetAttackRecord",
    "QuicBinaryRecord",
    "QuicFirewallBundle",
    "QuicFirewallPolicy",
    "QuicFirewallReport",
    "REPLAY_WINDOW_BITS",
    "REQUIRED_ISAS",
    "REQUIRED_NET_ATTACKS",
    "check_cap_net_peer_rules",
    "check_net_attacks",
    "check_replay_window_sequence",
    "is_sha256_hex",
    "is_strict_int",
    "parse_quic_payload",
    "parse_quic_receipt",
    "verify_quic_firewall_bundle",
    "verify_quic_firewall_file",
]
