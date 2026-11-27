# SPDX-License-Identifier: MIT
"""Strict fail-closed parser for Slice 31 QUIC-Lite + CAP_NET_PEER bundles and receipts."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from harness.quic_firewall_attest.quic_guards import is_strict_int, normalize_sha256

_ISA_SUFFIXES: tuple[tuple[str, str], ...] = (
    (".x64.elf", "x64-elf"),
    (".rv64.elf", "rv64-elf"),
    (".aarch64.elf", "aarch64-elf"),
    (".wasm", "wasm"),
    (".exe", "x64-pe"),
)

_HEX_FIELD_RE = {
    "quic_root_hex": re.compile(r'"quic_root_hex"\s*:\s*"([0-9a-fA-F]{64})"'),
    "tx_sha_hex": re.compile(r'"tx_sha_hex"\s*:\s*"([0-9a-fA-F]{64})"'),
    "fw_sha_hex": re.compile(r'"fw_sha_hex"\s*:\s*"([0-9a-fA-F]{64})"'),
}
_INT_FIELD_RE = {
    "cwnd": re.compile(r'"cwnd"\s*:\s*(\d+)'),
    "ssthresh": re.compile(r'"ssthresh"\s*:\s*(\d+)'),
    "max_pn": re.compile(r'"max_pn"\s*:\s*(\d+)'),
    "bmp_lo": re.compile(r'"bmp_lo"\s*:\s*(\d+)'),
}


@dataclass(frozen=True)
class QuicBinaryRecord:
    """Verified metadata for one Slice 31 zero-C binary."""

    isa: str
    rel_path: str
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class FirewallRuleRecord:
    """Single CAP_NET_PEER firewall policy rule."""

    capability: str
    peer_id: str
    action: str


@dataclass(frozen=True)
class NetAttackRecord:
    """Fail-closed rejection record for one network attack vector."""

    name: str
    rejected: Any
    committed: Any
    error_code: Any
    isas_rejected: Any


@dataclass(frozen=True)
class QuicFirewallBundle:
    """Normalized Slice 31 QUIC-Lite + CAP_NET_PEER attestation bundle."""

    schema: str
    verdict: str
    oracle_exit_code: int
    claim_sha256: str
    quic_root_hex: str
    tx_sha_hex: str
    fw_sha_hex: str
    cwnd: Any
    ssthresh: Any
    max_pn: Any
    bmp_lo: Any
    firewall_default: Any
    firewall_rules: tuple[FirewallRuleRecord, ...]
    packet_numbers: tuple[Any, ...] | None
    binaries: tuple[QuicBinaryRecord, ...]
    attacks: tuple[NetAttackRecord, ...]
    parse_errors: tuple[str, ...] = ()


def _infer_isa(rel_path: str) -> str:
    low = rel_path.lower()
    for suffix, isa in _ISA_SUFFIXES:
        if low.endswith(suffix):
            return isa
    return ""


def _parse_rules(raw: Any, errs: list[str]) -> tuple[FirewallRuleRecord, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        errs.append("firewall_rules_not_list")
        return ()
    out: list[FirewallRuleRecord] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"firewall_rule_not_dict_{idx}")
            continue
        out.append(FirewallRuleRecord(str(item.get("capability", "")), str(item.get("peer_id", "")), str(item.get("action", ""))))
    return tuple(out)


def _parse_attacks(raw: Any, errs: list[str]) -> tuple[NetAttackRecord, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        errs.append("attacks_not_list")
        return ()
    out: list[NetAttackRecord] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"attack_not_dict_{idx}")
            continue
        out.append(NetAttackRecord(str(item.get("name", "")), item.get("rejected"), item.get("committed"), item.get("error_code"), item.get("isas_rejected")))
    return tuple(out)


def _parse_bins(raw: Any, errs: list[str]) -> tuple[QuicBinaryRecord, ...]:
    if not isinstance(raw, list):
        errs.append("binaries_not_list")
        return ()
    out: list[QuicBinaryRecord] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"binary_not_dict_{idx}")
            continue
        size = item.get("bytes", item.get("byte_size", -1))
        out.append(QuicBinaryRecord(str(item.get("isa", "")), str(item.get("rel_path", "")), size if is_strict_int(size) else -1, normalize_sha256(item.get("sha256", ""))))
    return tuple(out)


def _extract_receipt_bins(artifacts: Any) -> tuple[QuicBinaryRecord, ...]:
    if not isinstance(artifacts, list):
        return ()
    out: list[QuicBinaryRecord] = []
    for art in artifacts:
        if not isinstance(art, dict):
            continue
        rel = str(art.get("rel_path", ""))
        isa = _infer_isa(rel)
        if isa:
            size = art.get("bytes", -1)
            out.append(
                QuicBinaryRecord(
                    isa=isa,
                    rel_path=rel,
                    byte_size=size if is_strict_int(size) else -1,
                    sha256=normalize_sha256(art.get("sha256", "")),
                )
            )
    return tuple(out)


def parse_quic_payload(data: dict[str, Any]) -> QuicFirewallBundle:
    """Parse a structured Slice 31 QUIC-Lite + CAP_NET_PEER JSON bundle."""
    errs: list[str] = []
    if not isinstance(data, dict):
        return QuicFirewallBundle(
            "", "REJECT", 1, "", "", "", "", None, None, None, None, None, (), None, (), (),
            ("payload_not_dict",),
        )
    pns = data.get("packet_numbers")
    pns_t = tuple(pns) if isinstance(pns, list) else pns
    ec = data.get("oracle_exit_code", 0)
    return QuicFirewallBundle(
        schema=str(data.get("schema", "")),
        verdict=str(data.get("verdict", "")),
        oracle_exit_code=ec if is_strict_int(ec) else -1,
        claim_sha256=normalize_sha256(data.get("claim_sha256", "")),
        quic_root_hex=normalize_sha256(data.get("quic_root_hex", "")),
        tx_sha_hex=normalize_sha256(data.get("tx_sha_hex", "")),
        fw_sha_hex=normalize_sha256(data.get("fw_sha_hex", "")),
        cwnd=data.get("cwnd"),
        ssthresh=data.get("ssthresh"),
        max_pn=data.get("max_pn"),
        bmp_lo=data.get("bmp_lo"),
        firewall_default=data.get("firewall_default"),
        firewall_rules=_parse_rules(data.get("firewall_rules"), errs),
        packet_numbers=pns_t,
        binaries=_parse_bins(data.get("binaries", []), errs),
        attacks=_parse_attacks(data.get("attacks"), errs),
        parse_errors=tuple(errs),
    )


def parse_quic_receipt(
    receipt: dict[str, Any],
    supplement: dict[str, Any] | None = None,
) -> QuicFirewallBundle:
    """Parse a canonical engine-receipt/1 JSON envelope for Slice 31 QUIC-Lite."""
    errs: list[str] = []
    if not isinstance(receipt, dict):
        return QuicFirewallBundle(
            "", "REJECT", 1, "", "", "", "", None, None, None, None, None, (), None, (), (),
            ("receipt_not_dict",),
        )
    oracle = receipt.get("oracle") if isinstance(receipt.get("oracle"), dict) else {}
    digests = receipt.get("digests") if isinstance(receipt.get("digests"), dict) else {}
    subject = receipt.get("subject") if isinstance(receipt.get("subject"), dict) else {}
    excerpt = str(oracle.get("stdout_excerpt", ""))
    hx = {k: (m.group(1).lower() if (m := pat.search(excerpt)) else "") for k, pat in _HEX_FIELD_RE.items()}
    iv = {k: (int(m.group(1)) if (m := pat.search(excerpt)) else None) for k, pat in _INT_FIELD_RE.items()}
    supp = supplement if isinstance(supplement, dict) else {}
    pns = supp.get("packet_numbers")
    ec = oracle.get("exit_code", -1)
    return QuicFirewallBundle(
        schema=str(receipt.get("schema", "")),
        verdict=str(receipt.get("verdict", "")),
        oracle_exit_code=ec if is_strict_int(ec) else -1,
        claim_sha256=normalize_sha256(digests.get("claim_sha256", "")),
        quic_root_hex=normalize_sha256(supp.get("quic_root_hex", hx["quic_root_hex"])),
        tx_sha_hex=normalize_sha256(supp.get("tx_sha_hex", hx["tx_sha_hex"])),
        fw_sha_hex=normalize_sha256(supp.get("fw_sha_hex", hx["fw_sha_hex"])),
        cwnd=supp.get("cwnd", iv["cwnd"]),
        ssthresh=supp.get("ssthresh", iv["ssthresh"]),
        max_pn=supp.get("max_pn", iv["max_pn"]),
        bmp_lo=supp.get("bmp_lo", iv["bmp_lo"]),
        firewall_default=supp.get("firewall_default"),
        firewall_rules=_parse_rules(supp.get("firewall_rules"), errs),
        packet_numbers=tuple(pns) if isinstance(pns, list) else pns,
        binaries=_extract_receipt_bins(subject.get("artifacts")),
        attacks=_parse_attacks(supp.get("attacks"), errs),
        parse_errors=tuple(errs),
    )
