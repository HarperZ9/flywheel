# SPDX-License-Identifier: MIT
"""Zero-egress and zero-WASI WebAssembly sandbox policy verifier.

Enforces module byte ceilings, explicit host import allowlists, and
fail-closed rejection of WASI, filesystem, process, and network imports.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .wasm_parser import (
    WasmExport,
    WasmImport,
    WasmParseError,
    parse_wasm_module,
)

HONEST_SCOPE_LIMIT = (
    "Enforces static WebAssembly import allowlists, forbidden capability "
    "denylists, export presence, and byte-size ceilings over parsed binary "
    "sections. Does not constrain host glue code or runtime CPU/memory fuel."
)

DEFAULT_MAX_MODULE_BYTES = 16384

DEFAULT_ALLOWED_IMPORTS: frozenset[tuple[str, str]] = frozenset(
    {
        ("env", "print_bool"),
        ("env", "print_f64"),
        ("env", "print_i64"),
        ("env", "print_str"),
        ("env", "print_u64"),
    }
)

FORBIDDEN_IMPORT_MODULES: frozenset[str] = frozenset(
    {
        "wasi_snapshot_preview1",
        "wasi_unstable",
        "fs",
        "node:fs",
        "net",
        "http",
        "https",
        "child_process",
        "os",
        "sys",
    }
)

FORBIDDEN_IMPORT_NAMES: frozenset[str] = frozenset(
    {
        "fetch",
        "xhr",
        "socket",
        "connect",
        "exec",
        "spawn",
        "open",
        "fd_write",
        "fd_read",
        "path_open",
        "proc_exit",
        "eval",
    }
)


@dataclass(frozen=True)
class SandboxPolicy:
    """Fail-closed static sandbox constraints for WebAssembly modules."""

    max_module_bytes: int = DEFAULT_MAX_MODULE_BYTES
    allowed_imports: frozenset[tuple[str, str]] = DEFAULT_ALLOWED_IMPORTS
    allowed_import_kinds: frozenset[str] = frozenset({"func"})
    require_nonempty_exports: bool = True


DEFAULT_POLICY = SandboxPolicy()


@dataclass(frozen=True)
class SandboxAuditReport:
    """Fail-closed sandbox audit outcome for a single WebAssembly module."""

    passed: bool
    byte_length: int
    sha256: str
    imports: tuple[WasmImport, ...]
    exports: tuple[WasmExport, ...]
    disallowed_imports: tuple[str, ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize audit report into a deterministic JSON-compatible dict."""
        return {
            "passed": self.passed,
            "byte_length": self.byte_length,
            "sha256": self.sha256,
            "imports": [f"{i.module}.{i.name}:{i.kind}" for i in self.imports],
            "exports": [f"{e.name}:{e.kind}" for e in self.exports],
            "disallowed_imports": list(self.disallowed_imports),
            "reasons": list(self.reasons),
        }


def _check_imports(
    imports: tuple[WasmImport, ...],
    policy: SandboxPolicy,
    reasons: list[str],
) -> list[str]:
    disallowed: list[str] = []
    for imp in imports:
        label = f"{imp.module}.{imp.name}"
        mod_lower, name_lower = imp.module.lower(), imp.name.lower()
        if mod_lower in FORBIDDEN_IMPORT_MODULES or mod_lower.startswith("wasi"):
            disallowed.append(label)
            reasons.append(f"FORBIDDEN_IMPORT_MODULE:{label}")
        elif name_lower in FORBIDDEN_IMPORT_NAMES:
            disallowed.append(label)
            reasons.append(f"FORBIDDEN_IMPORT_NAME:{label}")
        elif imp.kind not in policy.allowed_import_kinds:
            disallowed.append(label)
            reasons.append(f"DISALLOWED_IMPORT_KIND:{label}:{imp.kind}")
        elif (imp.module, imp.name) not in policy.allowed_imports:
            disallowed.append(label)
            reasons.append(f"UNLISTED_IMPORT:{label}")
    return disallowed


def audit_wasm_bytes(
    data: bytes,
    *,
    policy: SandboxPolicy = DEFAULT_POLICY,
) -> SandboxAuditReport:
    """Parse a WebAssembly binary and audit it against SandboxPolicy."""
    raw = bytes(data) if isinstance(data, (bytes, bytearray)) else b""
    digest = hashlib.sha256(raw).hexdigest()
    try:
        info = parse_wasm_module(data)
    except WasmParseError as exc:
        return SandboxAuditReport(False, len(raw), digest, (), (), (), (f"WASM_PARSE_ERROR:{exc}",))
    reasons: list[str] = []
    if info.byte_length > policy.max_module_bytes:
        reasons.append(f"SIZE_EXCEEDS_LIMIT:{info.byte_length}>{policy.max_module_bytes}")
    disallowed = _check_imports(info.imports, policy, reasons)
    if policy.require_nonempty_exports and not info.exports:
        reasons.append("EMPTY_EXPORTS")
    return SandboxAuditReport(not reasons, info.byte_length, info.sha256, info.imports, info.exports, tuple(disallowed), tuple(reasons))
