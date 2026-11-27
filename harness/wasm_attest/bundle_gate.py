# SPDX-License-Identifier: MIT
"""Manifest-backed WebAssembly showcase bundle verifier.

Verifies every WebAssembly module in a staged drop-in bundle against its
declared SHA-256 digest, byte size, license tag, path containment, aggregate
bundle byte ceiling, and zero-egress/zero-WASI sandbox policy.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .sandbox_policy import DEFAULT_POLICY, SandboxPolicy, audit_wasm_bytes

HONEST_SCOPE_LIMIT = (
    "Verifies manifest SHA-256 parity, declared byte lengths, path "
    "containment, license metadata, aggregate size ceilings, and static "
    "sandbox policy across a WebAssembly bundle directory. Does not execute "
    "the modules in a browser or JavaScript runtime."
)

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class BundleModuleResult:
    """Verification outcome for one manifest entry in a WASM bundle."""

    slug: str
    wasm_path: str
    passed: bool
    byte_length: int
    sha256: str
    import_count: int
    export_count: int
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize module verification outcome into JSON-compatible dict."""
        return {
            "slug": self.slug,
            "wasm_path": self.wasm_path,
            "passed": self.passed,
            "byte_length": self.byte_length,
            "sha256": self.sha256,
            "import_count": self.import_count,
            "export_count": self.export_count,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class WasmBundleReport:
    """Fail-closed attestation report for an entire WebAssembly bundle."""

    passed: bool
    modules_checked: int
    modules_passed: int
    total_bytes: int
    max_module_bytes: int
    results: tuple[BundleModuleResult, ...]
    reasons: tuple[str, ...]
    attestation_sha256: str

    def to_dict(self) -> dict[str, object]:
        """Serialize bundle report into a deterministic JSON-compatible dict."""
        return {
            "passed": self.passed,
            "modules_checked": self.modules_checked,
            "modules_passed": self.modules_passed,
            "total_bytes": self.total_bytes,
            "max_module_bytes": self.max_module_bytes,
            "results": [r.to_dict() for r in self.results],
            "reasons": list(self.reasons),
            "attestation_sha256": self.attestation_sha256,
        }


def _seal_bundle(results: Sequence[BundleModuleResult], passed: bool, reasons: Sequence[str]) -> str:
    payload = {
        "passed": passed,
        "reasons": list(reasons),
        "results": [r.to_dict() for r in results],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _safe_resolve_under(bundle_dir: Path, rel_path: str) -> Path | None:
    if not rel_path or rel_path.startswith(("/", "\\")) or ".." in Path(rel_path).parts:
        return None
    base = bundle_dir.resolve()
    candidate = (base / rel_path).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def _audit_bundle_entry(
    bundle_dir: Path,
    idx: int,
    entry: Mapping[str, object],
    seen_slugs: set[str],
    seen_paths: set[str],
    policy: SandboxPolicy,
    required_license: str | None,
) -> BundleModuleResult:
    slug = str(entry.get("slug", f"entry_{idx}"))
    rel_path = str(entry.get("wasm_path", ""))
    m_reasons: list[str] = []
    if slug in seen_slugs:
        m_reasons.append(f"DUPLICATE_SLUG:{slug}")
    seen_slugs.add(slug)
    if rel_path in seen_paths:
        m_reasons.append(f"DUPLICATE_WASM_PATH:{rel_path}")
    seen_paths.add(rel_path)
    if required_license is not None and entry.get("license") != required_license:
        m_reasons.append(f"LICENSE_MISMATCH:{slug}")
    resolved = _safe_resolve_under(bundle_dir, rel_path)
    if resolved is None:
        m_reasons.append(f"PATH_TRAVERSAL_REJECTED:{slug}")
    elif not resolved.is_file():
        m_reasons.append(f"MISSING_WASM_FILE:{slug}")
    byte_len, digest, imp_cnt, exp_cnt = 0, "", 0, 0
    if resolved is not None and resolved.is_file():
        raw = resolved.read_bytes()
        byte_len, digest = len(raw), hashlib.sha256(raw).hexdigest()
        declared_bytes = entry.get("wasm_bytes")
        if isinstance(declared_bytes, int) and not isinstance(declared_bytes, bool):
            if declared_bytes != byte_len:
                m_reasons.append(f"BYTE_LENGTH_MISMATCH:{slug}:{byte_len}!={declared_bytes}")
        else:
            m_reasons.append(f"MISSING_DECLARED_BYTES:{slug}")
        declared_sha = entry.get("wasm_sha256")
        if not isinstance(declared_sha, str) or not _HEX64_RE.fullmatch(declared_sha):
            m_reasons.append(f"MALFORMED_DECLARED_SHA256:{slug}")
        elif not hmac.compare_digest(digest, declared_sha):
            m_reasons.append(f"SHA256_MISMATCH:{slug}")
        audit = audit_wasm_bytes(raw, policy=policy)
        imp_cnt, exp_cnt = len(audit.imports), len(audit.exports)
        if not audit.passed:
            m_reasons.extend(f"{slug}:{r}" for r in audit.reasons)
    return BundleModuleResult(slug, rel_path, not m_reasons, byte_len, digest, imp_cnt, exp_cnt, tuple(m_reasons))


def _load_manifest(bundle_dir: Path, manifest_name: str) -> tuple[Mapping[str, object] | None, str | None]:
    manifest_path = bundle_dir / manifest_name
    if not bundle_dir.is_dir() or not manifest_path.is_file():
        return None, "MISSING_BUNDLE_OR_MANIFEST"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "INVALID_MANIFEST_JSON"
    if not isinstance(manifest, Mapping) or not isinstance(manifest.get("modules"), list) or not manifest["modules"]:
        return None, "EMPTY_MANIFEST_MODULES"
    return manifest, None


def verify_wasm_bundle(
    bundle_dir: Path,
    manifest_name: str = "wasm_36pack_manifest.json",
    *,
    policy: SandboxPolicy = DEFAULT_POLICY,
    max_total_bytes: int | None = None,
    required_license: str | None = "MIT",
) -> WasmBundleReport:
    """Verify every WASM module listed in manifest_name under bundle_dir."""
    manifest, load_err = _load_manifest(bundle_dir, manifest_name)
    if manifest is None:
        reasons = (load_err or "INVALID_MANIFEST_JSON",)
        return WasmBundleReport(False, 0, 0, 0, 0, (), reasons, _seal_bundle((), False, reasons))
    modules = manifest["modules"]
    reasons_list: list[str] = []
    declared_count = manifest.get("module_count")
    if isinstance(declared_count, int) and declared_count != len(modules):
        reasons_list.append(f"MODULE_COUNT_MISMATCH:{declared_count}!={len(modules)}")
    seen_slugs: set[str] = set()
    seen_paths: set[str] = set()
    results: list[BundleModuleResult] = []
    total_bytes, max_seen, passed_count = 0, 0, 0
    for idx, entry in enumerate(modules):
        if not isinstance(entry, Mapping):
            reasons_list.append(f"INVALID_MODULE_ENTRY:{idx}")
            continue
        res = _audit_bundle_entry(bundle_dir, idx, entry, seen_slugs, seen_paths, policy, required_license)
        total_bytes += res.byte_length
        max_seen = max(max_seen, res.byte_length)
        if res.passed:
            passed_count += 1
        results.append(res)
        reasons_list.extend(res.reasons)
    declared_total = manifest.get("total_bytes")
    if isinstance(declared_total, int) and not isinstance(declared_total, bool) and declared_total != total_bytes:
        reasons_list.append(f"TOTAL_BYTES_MISMATCH:{total_bytes}!={declared_total}")
    if max_total_bytes is not None and total_bytes > max_total_bytes:
        reasons_list.append(f"TOTAL_BYTES_EXCEEDS_LIMIT:{total_bytes}>{max_total_bytes}")
    passed = not reasons_list and passed_count == len(modules)
    return WasmBundleReport(
        passed, len(results), passed_count, total_bytes, max_seen,
        tuple(results), tuple(reasons_list), _seal_bundle(results, passed, reasons_list),
    )
