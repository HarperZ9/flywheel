# SPDX-License-Identifier: MIT
"""Pure-stdlib fail-closed verifier for Slice 32 Zero-C Fuel-Metered Capability Sandbox VM."""

from harness.cap_sandbox_vm_gate.vm_guards import (
    CAP_CRYPTO,
    CAP_LOG,
    CODE_SEG_BASE,
    DEFAULT_MAX_FUEL,
    DEFAULT_MEM_WORDS,
    REQUIRED_ISAS,
    REQUIRED_VM_ATTACKS,
    VM_ROOT_HEX,
    check_vm_attacks,
    check_vm_execution_trace,
    is_sha256_hex,
    is_strict_int,
)
from harness.cap_sandbox_vm_gate.vm_oracle import (
    CapVmPolicy,
    CapVmReport,
    verify_cap_vm_bundle,
    verify_cap_vm_file,
)
from harness.cap_sandbox_vm_gate.vm_parser import (
    CapSandboxVmBundle,
    HostcallRecord,
    VmAttackRecord,
    VmBinaryRecord,
    parse_vm_payload,
    parse_vm_receipt,
)

__all__ = [
    "CAP_CRYPTO",
    "CAP_LOG",
    "CODE_SEG_BASE",
    "CapSandboxVmBundle",
    "CapVmPolicy",
    "CapVmReport",
    "DEFAULT_MAX_FUEL",
    "DEFAULT_MEM_WORDS",
    "HostcallRecord",
    "REQUIRED_ISAS",
    "REQUIRED_VM_ATTACKS",
    "VM_ROOT_HEX",
    "VmAttackRecord",
    "VmBinaryRecord",
    "check_vm_attacks",
    "check_vm_execution_trace",
    "is_sha256_hex",
    "is_strict_int",
    "parse_vm_payload",
    "parse_vm_receipt",
    "verify_cap_vm_bundle",
    "verify_cap_vm_file",
]
