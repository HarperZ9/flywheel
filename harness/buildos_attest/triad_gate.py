# SPDX-License-Identifier: MIT
"""5-ISA BuildOS Microkernel Triad oracle gate with 4/4 attack rejection proofs.

Verifies Slice 20 oracle output: every ISA target commits the clean triad with
reference-identical boot, scheduler, and VFS roots, and every target rejects
all four cross-layer attacks fail-closed back to Slot A.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .receipt_check import ISA_SUFFIXES, is_hex64, is_strict_int
from .triad_reference import TriadReference, derive_triad_reference

HONEST_SCOPE_LIMIT = (
    "Validates serialized Slice 20 triad oracle output: strict integer state "
    "fields, constant-time root parity against an independent reference, "
    "cross-ISA consensus, and 4/4 attack rejections to Slot A. Does not run "
    "the BuildOS binaries or the ISA emulators itself."
)

REQUIRED_ISAS: tuple[str, ...] = tuple(ISA_SUFFIXES)
CLEAN_STATE: dict[str, int] = {
    "status": 1,
    "triad_committed": 1,
    "boot_slot": 2,
    "epoch": 20,
    "ticks": 9,
    "vfs_blocks": 4,
}
ROOT_FIELDS: tuple[str, ...] = ("boot_log_root_hex", "sched_trace_sha_hex", "vfs_inode_root_hex")
ATTACKS: dict[str, int] = {
    "boot_epoch_rollback": -101,
    "post_boot_wx_escalation": -201,
    "ipc_double_send_ownership_fault": -301,
    "vfs_silent_block_1bit_corruption": -401,
}
SLOT_A = 1


@dataclass(frozen=True)
class TriadGateReport:
    """Fail-closed verdict over the 5-ISA triad and 4/4 attack proofs."""

    passed: bool
    targets_committed: tuple[str, ...]
    attacks_rejected: int
    attacks_expected: int
    reasons: tuple[str, ...]
    triad_attestation_sha256: str

    def to_dict(self) -> dict[str, object]:
        """Serialize report into a JSON-compatible dictionary."""
        return {
            "passed": self.passed,
            "targets_committed": list(self.targets_committed),
            "attacks_rejected": self.attacks_rejected,
            "attacks_expected": self.attacks_expected,
            "reasons": list(self.reasons),
            "triad_attestation_sha256": self.triad_attestation_sha256,
        }


def _check_clean_target(isa: str, rec: object, ref: TriadReference, reasons: list[str]) -> bool:
    if not isinstance(rec, Mapping):
        reasons.append(f"MISSING_TARGET:{isa}")
        return False
    start = len(reasons)
    for field, expected in CLEAN_STATE.items():
        val = rec.get(field)
        if not is_strict_int(val):
            reasons.append(f"NON_INTEGER_FIELD:{isa}:{field}")
        elif val != expected:
            reasons.append(f"STATE_MISMATCH:{isa}:{field}:{val}!={expected}")
    expected_roots = ref.to_dict()
    for field in ROOT_FIELDS:
        val = rec.get(field)
        if not is_hex64(val):
            reasons.append(f"MALFORMED_ROOT:{isa}:{field}")
        elif not hmac.compare_digest(str(val), expected_roots[field]):
            reasons.append(f"ROOT_MISMATCH:{isa}:{field}")
    if not is_hex64(rec.get("sha256")):
        reasons.append(f"MALFORMED_BINARY_SHA256:{isa}")
    size = rec.get("bytes")
    if not is_strict_int(size) or int(size) <= 0:
        reasons.append(f"INVALID_BINARY_BYTES:{isa}")
    return len(reasons) == start


def _check_attack_target(attack: str, isa: str, rec: object, reasons: list[str]) -> bool:
    if not isinstance(rec, Mapping):
        reasons.append(f"MISSING_ATTACK_TARGET:{attack}:{isa}")
        return False
    start = len(reasons)
    status = rec.get("status")
    if not is_strict_int(status) or status != ATTACKS[attack]:
        reasons.append(f"ATTACK_STATUS_MISMATCH:{attack}:{isa}:{status}")
    if not is_strict_int(rec.get("triad_committed")) or rec.get("triad_committed") != 0:
        reasons.append(f"ATTACK_COMMITTED_TRIAD:{attack}:{isa}")
    if not is_strict_int(rec.get("fallback_slot")) or rec.get("fallback_slot") != SLOT_A:
        reasons.append(f"ATTACK_NOT_SLOT_A:{attack}:{isa}")
    if rec.get("rejected_fail_closed") is not True:
        reasons.append(f"ATTACK_NOT_FAIL_CLOSED:{attack}:{isa}")
    return len(reasons) == start


def _check_attacks(controls: object, isas: Sequence[str], reasons: list[str]) -> int:
    if not isinstance(controls, Mapping):
        reasons.append("MISSING_PLANTED_CONTROLS")
        return 0
    rejected = 0
    for attack in ATTACKS:
        per_isa = controls.get(attack)
        if not isinstance(per_isa, Mapping):
            reasons.append(f"MISSING_ATTACK:{attack}")
            continue
        for isa in isas:
            if _check_attack_target(attack, isa, per_isa.get(isa), reasons):
                rejected += 1
    return rejected


def _seal(committed: Sequence[str], rejected: int, reasons: Sequence[str], ref: TriadReference) -> str:
    payload = {
        "committed": list(committed),
        "attacks_rejected": rejected,
        "reasons": list(reasons),
        "reference": ref.to_dict(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def verify_triad_oracle(
    output: Mapping[str, object],
    *,
    reference: TriadReference | None = None,
    required_isas: Sequence[str] = REQUIRED_ISAS,
) -> TriadGateReport:
    """Verify Slice 20 oracle output across all ISAs and all four attacks."""
    ref = reference if reference is not None else derive_triad_reference()
    isas = tuple(required_isas)
    expected_attacks = len(ATTACKS) * len(isas)
    if not isinstance(output, Mapping):
        reasons = ("INVALID_ORACLE_OUTPUT",)
        return TriadGateReport(False, (), 0, expected_attacks, reasons, _seal((), 0, reasons, ref))
    reasons: list[str] = []
    if output.get("ok") is not True:
        reasons.append("ORACLE_NOT_OK")
    targets = output.get("targets")
    targets = targets if isinstance(targets, Mapping) else {}
    committed = tuple(isa for isa in isas if _check_clean_target(isa, targets.get(isa), ref, reasons))
    rejected = _check_attacks(output.get("planted_controls"), isas, reasons)
    unique = tuple(dict.fromkeys(reasons))
    passed = not unique and len(committed) == len(isas) and rejected == expected_attacks
    return TriadGateReport(passed, committed, rejected, expected_attacks, unique, _seal(committed, rejected, unique, ref))
