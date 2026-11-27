# SPDX-License-Identifier: MIT
"""Pure-stdlib Zero-C BuildOS Microkernel Triad attestation (Slices 17 to 20).

Verifies 5-ISA engine-receipt/1 envelopes, re-derives the Slice 20 triad
reference roots independently, and gates the triad oracle output including
4/4 cross-layer attack rejections to Slot A.
"""

from __future__ import annotations

from .receipt_check import (
    BUILDOS_SLICES,
    ENGINE_RECEIPT_SCHEMA,
    ISA_SUFFIXES,
    SliceReceiptReport,
    is_finite_number,
    is_hex64,
    is_prefixed_sha256,
    is_strict_int,
    verify_slice_receipt,
    verify_slice_receipt_file,
)
from .receipt_check import (
    HONEST_SCOPE_LIMIT as RECEIPT_HONEST_SCOPE_LIMIT,
)
from .triad_gate import (
    ATTACKS,
    CLEAN_STATE,
    REQUIRED_ISAS,
    ROOT_FIELDS,
    SLOT_A,
    TriadGateReport,
    verify_triad_oracle,
)
from .triad_gate import (
    HONEST_SCOPE_LIMIT as GATE_HONEST_SCOPE_LIMIT,
)
from .triad_reference import (
    HONEST_SCOPE_LIMIT as REFERENCE_HONEST_SCOPE_LIMIT,
)
from .triad_reference import (
    TriadReference,
    derive_boot_log_root,
    derive_sched_trace_sha,
    derive_triad_reference,
    derive_vfs_inode_root,
    leaf_hash,
    merkle_root_of_four,
    node_hash,
)

HONEST_SCOPE_LIMIT = (
    "Pure-Python stdlib verifier for Zero-C BuildOS Slice 17 to 20 receipts and "
    "the Slice 20 triad oracle output. Does not compile, execute, or emulate "
    "BuildOS binaries on any instruction set."
)

HONEST_SCOPE_LIMITS: dict[str, str] = {
    "receipt_check": RECEIPT_HONEST_SCOPE_LIMIT,
    "triad_reference": REFERENCE_HONEST_SCOPE_LIMIT,
    "triad_gate": GATE_HONEST_SCOPE_LIMIT,
}

__all__ = [
    "ATTACKS",
    "BUILDOS_SLICES",
    "CLEAN_STATE",
    "ENGINE_RECEIPT_SCHEMA",
    "HONEST_SCOPE_LIMIT",
    "HONEST_SCOPE_LIMITS",
    "ISA_SUFFIXES",
    "REQUIRED_ISAS",
    "ROOT_FIELDS",
    "SLOT_A",
    "SliceReceiptReport",
    "TriadGateReport",
    "TriadReference",
    "derive_boot_log_root",
    "derive_sched_trace_sha",
    "derive_triad_reference",
    "derive_vfs_inode_root",
    "is_finite_number",
    "is_hex64",
    "is_prefixed_sha256",
    "is_strict_int",
    "leaf_hash",
    "merkle_root_of_four",
    "node_hash",
    "verify_slice_receipt",
    "verify_slice_receipt_file",
    "verify_triad_oracle",
]
