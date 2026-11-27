# SPDX-License-Identifier: MIT
"""Strict fail-closed parser for Slice 32 Capability Sandbox VM bundles and receipts."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from harness.cap_sandbox_vm_gate.vm_guards import is_strict_int, normalize_sha256

_ISA_SUFFIXES: tuple[tuple[str, str], ...] = (
    (".x64.elf", "x64-elf"),
    (".rv64.elf", "rv64-elf"),
    (".aarch64.elf", "aarch64-elf"),
    (".wasm", "wasm"),
    (".exe", "x64-pe"),
)

_HEX_RE = {
    "guest_sha_hex": re.compile(r'"guest_sha_hex"\s*:\s*"([0-9a-fA-F]{64})"'),
    "trace_sha_hex": re.compile(r'"trace_sha_hex"\s*:\s*"([0-9a-fA-F]{64})"'),
    "vm_root_hex": re.compile(r'"vm_root_hex"\s*:\s*"([0-9a-fA-F]{64})"'),
}
_INT_RE = {
    "fuel_budget": re.compile(r'"fuel_budget"\s*:\s*(\d+)'),
    "fuel_used": re.compile(r'"fuel_used"\s*:\s*(\d+)'),
    "cap_mask": re.compile(r'"cap_mask"\s*:\s*(\d+)'),
    "host_out": re.compile(r'"host_out"\s*:\s*(\d+)'),
}


@dataclass(frozen=True)
class VmBinaryRecord:
    """Verified metadata for one Slice 32 zero-C binary."""

    isa: str
    rel_path: str
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class HostcallRecord:
    """Single guest hostcall capability check."""

    hostcall_id: int
    required_cap: Any
    allowed: Any


@dataclass(frozen=True)
class VmAttackRecord:
    """Fail-closed rejection record for one sandbox-escape attack control."""

    name: str
    rejected: Any
    committed: Any
    error_code: Any
    isas_rejected: Any


@dataclass(frozen=True)
class CapSandboxVmBundle:
    """Normalized Slice 32 Fuel-Metered Capability Sandbox VM bundle."""

    schema: str
    verdict: str
    oracle_exit_code: int
    claim_sha256: str
    fuel_budget: Any
    fuel_used: Any
    cap_mask: Any
    guest_sha_hex: str
    trace_sha_hex: str
    vm_root_hex: str
    mem_writes: tuple[Any, ...]
    hostcalls: tuple[HostcallRecord, ...]
    binaries: tuple[VmBinaryRecord, ...]
    attacks: tuple[VmAttackRecord, ...]
    parse_errors: tuple[str, ...] = ()


def _infer_isa(rel_path: str) -> str:
    low = rel_path.lower()
    for suffix, isa in _ISA_SUFFIXES:
        if low.endswith(suffix):
            return isa
    return ""


def _parse_hostcalls(raw: Any, errs: list[str]) -> tuple[HostcallRecord, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        errs.append("hostcalls_not_list")
        return ()
    out: list[HostcallRecord] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"hostcall_not_dict_{idx}")
            continue
        hid = item.get("hostcall_id", idx)
        out.append(HostcallRecord(hid if is_strict_int(hid) else -1, item.get("required_cap"), item.get("allowed")))
    return tuple(out)


def _parse_attacks(raw: Any, errs: list[str]) -> tuple[VmAttackRecord, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        errs.append("attacks_not_list")
        return ()
    out: list[VmAttackRecord] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"attack_not_dict_{idx}")
            continue
        out.append(VmAttackRecord(str(item.get("name", "")), item.get("rejected"), item.get("committed"), item.get("error_code"), item.get("isas_rejected")))
    return tuple(out)


def _parse_bins(raw: Any, errs: list[str]) -> tuple[VmBinaryRecord, ...]:
    if not isinstance(raw, list):
        errs.append("binaries_not_list")
        return ()
    out: list[VmBinaryRecord] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            errs.append(f"binary_not_dict_{idx}")
            continue
        sz = item.get("bytes", item.get("byte_size", -1))
        out.append(VmBinaryRecord(str(item.get("isa", "")), str(item.get("rel_path", "")), sz if is_strict_int(sz) else -1, normalize_sha256(item.get("sha256", ""))))
    return tuple(out)


def _extract_receipt_bins(artifacts: Any) -> tuple[VmBinaryRecord, ...]:
    if not isinstance(artifacts, list):
        return ()
    out: list[VmBinaryRecord] = []
    for art in artifacts:
        if not isinstance(art, dict):
            continue
        rel = str(art.get("rel_path", ""))
        isa = _infer_isa(rel)
        if isa:
            sz = art.get("bytes", -1)
            out.append(VmBinaryRecord(isa, rel, sz if is_strict_int(sz) else -1, normalize_sha256(art.get("sha256", ""))))
    return tuple(out)


def parse_vm_payload(data: dict[str, Any]) -> CapSandboxVmBundle:
    """Parse a structured Slice 32 Capability Sandbox VM JSON bundle."""
    errs: list[str] = []
    if not isinstance(data, dict):
        return CapSandboxVmBundle("", "REJECT", 1, "", None, None, None, "", "", "", (), (), (), (), ("payload_not_dict",))
    writes = data.get("mem_writes", [])
    if not isinstance(writes, list):
        errs.append("mem_writes_not_list")
        writes = []
    ec = data.get("oracle_exit_code", 0)
    return CapSandboxVmBundle(
        schema=str(data.get("schema", "")),
        verdict=str(data.get("verdict", "")),
        oracle_exit_code=ec if is_strict_int(ec) else -1,
        claim_sha256=normalize_sha256(data.get("claim_sha256", "")),
        fuel_budget=data.get("fuel_budget"),
        fuel_used=data.get("fuel_used"),
        cap_mask=data.get("cap_mask"),
        guest_sha_hex=normalize_sha256(data.get("guest_sha_hex", "")),
        trace_sha_hex=normalize_sha256(data.get("trace_sha_hex", "")),
        vm_root_hex=normalize_sha256(data.get("vm_root_hex", "")),
        mem_writes=tuple(writes),
        hostcalls=_parse_hostcalls(data.get("hostcalls"), errs),
        binaries=_parse_bins(data.get("binaries", []), errs),
        attacks=_parse_attacks(data.get("attacks"), errs),
        parse_errors=tuple(errs),
    )


def parse_vm_receipt(
    receipt: dict[str, Any],
    supplement: dict[str, Any] | None = None,
) -> CapSandboxVmBundle:
    """Parse a canonical engine-receipt/1 JSON envelope for Slice 32 Sandbox VM."""
    errs: list[str] = []
    if not isinstance(receipt, dict):
        return CapSandboxVmBundle("", "REJECT", 1, "", None, None, None, "", "", "", (), (), (), (), ("receipt_not_dict",))
    oracle = receipt.get("oracle") if isinstance(receipt.get("oracle"), dict) else {}
    digests = receipt.get("digests") if isinstance(receipt.get("digests"), dict) else {}
    subject = receipt.get("subject") if isinstance(receipt.get("subject"), dict) else {}
    excerpt = str(oracle.get("stdout_excerpt", ""))
    hx = {k: (m.group(1).lower() if (m := pat.search(excerpt)) else "") for k, pat in _HEX_RE.items()}
    iv = {k: (int(m.group(1)) if (m := pat.search(excerpt)) else None) for k, pat in _INT_RE.items()}
    supp = supplement if isinstance(supplement, dict) else {}
    writes = supp.get("mem_writes", [])
    ec = oracle.get("exit_code", -1)
    return CapSandboxVmBundle(
        schema=str(receipt.get("schema", "")),
        verdict=str(receipt.get("verdict", "")),
        oracle_exit_code=ec if is_strict_int(ec) else -1,
        claim_sha256=normalize_sha256(digests.get("claim_sha256", "")),
        fuel_budget=supp.get("fuel_budget", iv["fuel_budget"]),
        fuel_used=supp.get("fuel_used", iv["fuel_used"]),
        cap_mask=supp.get("cap_mask", iv["cap_mask"]),
        guest_sha_hex=normalize_sha256(supp.get("guest_sha_hex", hx["guest_sha_hex"])),
        trace_sha_hex=normalize_sha256(supp.get("trace_sha_hex", hx["trace_sha_hex"])),
        vm_root_hex=normalize_sha256(supp.get("vm_root_hex", hx["vm_root_hex"])),
        mem_writes=tuple(writes) if isinstance(writes, list) else (),
        hostcalls=_parse_hostcalls(supp.get("hostcalls"), errs),
        binaries=_extract_receipt_bins(subject.get("artifacts")),
        attacks=_parse_attacks(supp.get("attacks"), errs),
        parse_errors=tuple(errs),
    )
