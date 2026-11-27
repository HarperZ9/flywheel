# SPDX-License-Identifier: MIT
"""Unit and adversarial tamper tests for harness.wasm_attest."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

from harness import wasm_attest as wa


def _enc_name(text: str) -> bytes:
    raw = text.encode("utf-8")
    return wa.encode_u32_leb128(len(raw)) + raw


def _section(sec_id: int, payload: bytes) -> bytes:
    return bytes([sec_id]) + wa.encode_u32_leb128(len(payload)) + payload


def _build_wasm(
    *,
    imports: list[tuple[str, str, int]] | None = None,
    exports: list[tuple[str, int, int]] | None = None,
    custom_padding: int = 0,
) -> bytes:
    out = bytearray(wa.WASM_MAGIC_VERSION)
    # Type section (1): one () -> () function type.
    out += _section(1, b"\x01\x60\x00\x00")
    if imports:
        imp_buf = bytearray(wa.encode_u32_leb128(len(imports)))
        for mod, name, kind in imports:
            imp_buf += _enc_name(mod) + _enc_name(name) + bytes([kind])
            if kind == 0:
                imp_buf += b"\x00"  # typeidx 0
            elif kind == 1:
                imp_buf += b"\x70\x00\x01"  # funcref table min=1
            elif kind == 2:
                imp_buf += b"\x00\x01"  # memory min=1
            elif kind == 3:
                imp_buf += b"\x7f\x00"  # i32 immutable global
        out += _section(2, bytes(imp_buf))
    if exports:
        exp_buf = bytearray(wa.encode_u32_leb128(len(exports)))
        for name, kind, idx in exports:
            exp_buf += _enc_name(name) + bytes([kind]) + wa.encode_u32_leb128(idx)
        out += _section(7, bytes(exp_buf))
    if custom_padding > 0:
        out += _section(0, _enc_name("pad") + (b"\x00" * custom_padding))
    return bytes(out)


def _write_bundle(root: Path, specs: list[tuple[str, bytes]]) -> Path:
    wasm_dir = root / "wasm"
    wasm_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    total = 0
    for slug, raw in specs:
        p = wasm_dir / f"{slug}.wasm"
        p.write_bytes(raw)
        total += len(raw)
        entries.append(
            {
                "slug": slug,
                "wasm_path": f"wasm/{slug}.wasm",
                "wasm_bytes": len(raw),
                "wasm_sha256": hashlib.sha256(raw).hexdigest(),
                "license": "MIT",
            }
        )
    manifest = {"module_count": len(entries), "total_bytes": total, "modules": entries}
    (root / "wasm_36pack_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_parse_valid_module_with_all_four_import_kinds_and_exports() -> None:
    raw = _build_wasm(
        imports=[("env", "f", 0), ("env", "t", 1), ("env", "m", 2), ("env", "g", 3)],
        exports=[("main", 0, 0), ("memory", 2, 0)],
    )
    info = wa.parse_wasm_module(raw)
    assert info.byte_length == len(raw)
    assert info.section_ids == (1, 2, 7)
    assert [(i.module, i.name, i.kind) for i in info.imports] == [
        ("env", "f", "func"),
        ("env", "t", "table"),
        ("env", "m", "memory"),
        ("env", "g", "global"),
    ]
    assert [(e.name, e.kind, e.index) for e in info.exports] == [("main", "func", 0), ("memory", "memory", 0)]
    assert info.to_dict()["byte_length"] == len(raw)


@pytest.mark.parametrize(
    "bad_bytes",
    [
        b"\xca\xfe\xba\xbe\x01\x00\x00\x00",
        b"\x00asm\x02\x00\x00\x00",
        b"\x00asm\x01\x00",
        wa.WASM_MAGIC_VERSION + b"\x01\x05\x00",
        wa.WASM_MAGIC_VERSION + b"\x1f\x00",
        wa.WASM_MAGIC_VERSION + _section(7, b"\x00") + _section(1, b"\x00"),
        wa.WASM_MAGIC_VERSION + b"\x00\x80\x80\x80\x80\x10",
    ],
)
def test_parser_rejects_malformed_and_corrupted_wasm(bad_bytes: bytes) -> None:
    with pytest.raises(wa.WasmParseError):
        wa.parse_wasm_module(bad_bytes)


def test_parser_rejects_trailing_bytes_and_invalid_utf8_in_imports() -> None:
    bad_trail = wa.WASM_MAGIC_VERSION + _section(2, b"\x00\xff")
    with pytest.raises(wa.WasmParseError):
        wa.parse_wasm_module(bad_trail)
    bad_utf8 = wa.WASM_MAGIC_VERSION + _section(7, b"\x01\x02\xff\xfe\x00\x00")
    with pytest.raises(wa.WasmParseError):
        wa.parse_wasm_module(bad_utf8)


def test_sandbox_policy_passes_all_five_allowed_env_print_stubs() -> None:
    allowed = [(m, n, 0) for m, n in sorted(wa.DEFAULT_ALLOWED_IMPORTS)]
    raw = _build_wasm(imports=allowed, exports=[("main", 0, 0)])
    rep = wa.audit_wasm_bytes(raw)
    assert rep.passed is True and rep.disallowed_imports == () and rep.reasons == ()
    assert rep.to_dict()["passed"] is True


@pytest.mark.parametrize(
    ("mod", "name", "kind", "code_prefix"),
    [
        ("wasi_snapshot_preview1", "fd_write", 0, "FORBIDDEN_IMPORT_MODULE:"),
        ("wasi_unstable", "proc_exit", 0, "FORBIDDEN_IMPORT_MODULE:"),
        ("env", "fetch", 0, "FORBIDDEN_IMPORT_NAME:"),
        ("fs", "open", 0, "FORBIDDEN_IMPORT_MODULE:"),
        ("env", "secret_host_call", 0, "UNLISTED_IMPORT:"),
        ("env", "print_i64", 2, "DISALLOWED_IMPORT_KIND:"),
    ],
)
def test_sandbox_policy_rejects_forbidden_or_unlisted_imports(
    mod: str, name: str, kind: int, code_prefix: str
) -> None:
    raw = _build_wasm(imports=[(mod, name, kind)], exports=[("main", 0, 0)])
    rep = wa.audit_wasm_bytes(raw)
    assert rep.passed is False
    assert f"{mod}.{name}" in rep.disallowed_imports
    assert any(r.startswith(code_prefix) for r in rep.reasons)


def test_sandbox_policy_enforces_size_ceiling_exports_and_parse_errors() -> None:
    oversize = _build_wasm(exports=[("main", 0, 0)], custom_padding=17000)
    assert any("SIZE_EXCEEDS_LIMIT:" in r for r in wa.audit_wasm_bytes(oversize).reasons)
    no_exports = _build_wasm()
    assert "EMPTY_EXPORTS" in wa.audit_wasm_bytes(no_exports).reasons
    bad_magic = wa.audit_wasm_bytes(b"\xca\xfe\xba\xbe\x00\x00\x00\x00")
    assert bad_magic.passed is False and any("WASM_PARSE_ERROR:" in r for r in bad_magic.reasons)


def test_bundle_gate_passes_clean_bundle_and_seals_attestation(tmp_path: Path) -> None:
    m1 = _build_wasm(imports=[("env", "print_i64", 0)], exports=[("main", 0, 0)])
    m2 = _build_wasm(exports=[("run", 0, 0)])
    _write_bundle(tmp_path, [("mod_one", m1), ("mod_two", m2)])
    rep = wa.verify_wasm_bundle(tmp_path, max_total_bytes=200000)
    assert rep.passed is True and rep.modules_checked == 2 and rep.modules_passed == 2
    assert len(rep.attestation_sha256) == 64 and rep.to_dict()["passed"] is True


def test_bundle_gate_catches_1bit_sha_tamper_and_byte_mismatch(tmp_path: Path) -> None:
    m1 = _build_wasm(exports=[("main", 0, 0)])
    _write_bundle(tmp_path, [("alpha", m1)])
    p = tmp_path / "wasm" / "alpha.wasm"
    raw = bytearray(p.read_bytes())
    raw[-1] ^= 1
    p.write_bytes(bytes(raw))
    rep = wa.verify_wasm_bundle(tmp_path)
    assert rep.passed is False and "SHA256_MISMATCH:alpha" in rep.reasons


def test_bundle_gate_catches_wasi_injection_traversal_and_license(tmp_path: Path) -> None:
    bad_wasi = _build_wasm(imports=[("wasi_snapshot_preview1", "fd_write", 0)], exports=[("main", 0, 0)])
    _write_bundle(tmp_path, [("evil", bad_wasi)])
    rep = wa.verify_wasm_bundle(tmp_path)
    assert rep.passed is False
    assert any("FORBIDDEN_IMPORT_MODULE:wasi_snapshot_preview1.fd_write" in r for r in rep.reasons)

    mp = tmp_path / "wasm_36pack_manifest.json"
    obj = json.loads(mp.read_text(encoding="utf-8"))
    obj["modules"][0]["wasm_path"] = "../escape.wasm"
    obj["modules"][0]["license"] = "Proprietary"
    mp.write_text(json.dumps(obj), encoding="utf-8")
    rep2 = wa.verify_wasm_bundle(tmp_path)
    assert rep2.passed is False
    assert "PATH_TRAVERSAL_REJECTED:evil" in rep2.reasons
    assert "LICENSE_MISMATCH:evil" in rep2.reasons


def test_bundle_gate_missing_manifest_and_total_limit(tmp_path: Path) -> None:
    assert wa.verify_wasm_bundle(tmp_path).passed is False
    m1 = _build_wasm(exports=[("main", 0, 0)], custom_padding=200)
    _write_bundle(tmp_path, [("big", m1)])
    rep = wa.verify_wasm_bundle(tmp_path, max_total_bytes=100)
    assert rep.passed is False and any("TOTAL_BYTES_EXCEEDS_LIMIT:" in r for r in rep.reasons)


@pytest.mark.parametrize("val", [0, 1, 127, 128, 16384, 0xFFFFFFFF])
def test_encode_u32_leb128_roundtrip(val: int) -> None:
    enc = wa.encode_u32_leb128(val)
    assert 1 <= len(enc) <= 5
    with pytest.raises(ValueError):
        wa.encode_u32_leb128(-1)


def test_package_hygiene_loc_spdx_stdlib_and_scope_limits() -> None:
    root = Path(__file__).resolve().parents[1]
    pkg_files = sorted((root / "harness" / "wasm_attest").glob("*.py"))
    assert len(pkg_files) == 4
    assert set(wa.HONEST_SCOPE_LIMITS) == {"wasm_parser", "sandbox_policy", "bundle_gate"}
    for path in [*pkg_files, Path(__file__).resolve()]:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 250, f"{path.name} has {len(lines)} lines (> 250)"
        assert lines[0] == "# SPDX-License-Identifier: MIT"
        assert "\u2014" not in text and "\u2013" not in text
    for path in pkg_files:
        text = path.read_text(encoding="utf-8")
        assert "HONEST_SCOPE_LIMIT" in text
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import):
                assert all(a.name.split(".")[0] in sys.stdlib_module_names for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                assert node.module.split(".")[0] in sys.stdlib_module_names
