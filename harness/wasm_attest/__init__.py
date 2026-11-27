# SPDX-License-Identifier: MIT
"""Pure-stdlib WebAssembly binary parser and zero-egress sandbox gate.

Validates WebAssembly 1.0 binary framing, extracts exact import/export
tables with zero external tools, and enforces strict zero-WASI/zero-egress
sandbox and manifest SHA-256 attestation across module bundles.
"""

from __future__ import annotations

from .bundle_gate import (
    HONEST_SCOPE_LIMIT as BUNDLE_HONEST_SCOPE_LIMIT,
)
from .bundle_gate import (
    BundleModuleResult,
    WasmBundleReport,
    verify_wasm_bundle,
)
from .sandbox_policy import (
    DEFAULT_ALLOWED_IMPORTS,
    DEFAULT_MAX_MODULE_BYTES,
    DEFAULT_POLICY,
    FORBIDDEN_IMPORT_MODULES,
    FORBIDDEN_IMPORT_NAMES,
    SandboxAuditReport,
    SandboxPolicy,
    audit_wasm_bytes,
)
from .sandbox_policy import (
    HONEST_SCOPE_LIMIT as SANDBOX_HONEST_SCOPE_LIMIT,
)
from .wasm_parser import (
    HONEST_SCOPE_LIMIT as PARSER_HONEST_SCOPE_LIMIT,
)
from .wasm_parser import (
    KIND_NAMES,
    WASM_MAGIC_VERSION,
    WasmExport,
    WasmImport,
    WasmModuleInfo,
    WasmParseError,
    encode_u32_leb128,
    parse_wasm_module,
)

HONEST_SCOPE_LIMIT = (
    "Pure-Python stdlib static WebAssembly binary parser, import/export "
    "extractor, and bundle manifest verifier. Does not type-check function "
    "bodies or execute WebAssembly modules inside a host engine."
)

HONEST_SCOPE_LIMITS: dict[str, str] = {
    "wasm_parser": PARSER_HONEST_SCOPE_LIMIT,
    "sandbox_policy": SANDBOX_HONEST_SCOPE_LIMIT,
    "bundle_gate": BUNDLE_HONEST_SCOPE_LIMIT,
}

__all__ = [
    "BundleModuleResult",
    "DEFAULT_ALLOWED_IMPORTS",
    "DEFAULT_MAX_MODULE_BYTES",
    "DEFAULT_POLICY",
    "FORBIDDEN_IMPORT_MODULES",
    "FORBIDDEN_IMPORT_NAMES",
    "HONEST_SCOPE_LIMIT",
    "HONEST_SCOPE_LIMITS",
    "KIND_NAMES",
    "SandboxAuditReport",
    "SandboxPolicy",
    "WASM_MAGIC_VERSION",
    "WasmBundleReport",
    "WasmExport",
    "WasmImport",
    "WasmModuleInfo",
    "WasmParseError",
    "audit_wasm_bytes",
    "encode_u32_leb128",
    "parse_wasm_module",
    "verify_wasm_bundle",
]
