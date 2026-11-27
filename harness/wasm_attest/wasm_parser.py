# SPDX-License-Identifier: MIT
"""Pure-stdlib WebAssembly 1.0 binary section, import, and export parser.

Validates the 8-byte WebAssembly header (\\x00asm\\x01\\x00\\x00\\x00), unsigned
LEB128 section framing, standard section ordering, and UTF-8 import/export
tables with zero third-party dependencies or external CLI tools.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

HONEST_SCOPE_LIMIT = (
    "Validates WebAssembly 1.0 binary header, unsigned LEB128 section framing, "
    "canonical standard section ordering, and Import/Export section decoding. "
    "Does not type-check function bodies or execute WebAssembly bytecode."
)

WASM_MAGIC_VERSION = b"\x00asm\x01\x00\x00\x00"
KIND_NAMES: dict[int, str] = {0: "func", 1: "table", 2: "memory", 3: "global"}
_SECTION_ORDER: dict[int, int] = {
    1: 1,
    2: 2,
    3: 3,
    4: 4,
    5: 5,
    6: 6,
    7: 7,
    8: 8,
    9: 9,
    12: 10,
    10: 11,
    11: 12,
}


class WasmParseError(ValueError):
    """Raised fail-closed when a WebAssembly binary fails framing validation."""


@dataclass(frozen=True)
class WasmImport:
    """One decoded WebAssembly import entry."""

    module: str
    name: str
    kind: str


@dataclass(frozen=True)
class WasmExport:
    """One decoded WebAssembly export entry."""

    name: str
    kind: str
    index: int


@dataclass(frozen=True)
class WasmModuleInfo:
    """Structural summary of a parsed WebAssembly binary."""

    byte_length: int
    sha256: str
    section_ids: tuple[int, ...]
    imports: tuple[WasmImport, ...]
    exports: tuple[WasmExport, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize module info into a JSON-compatible dictionary."""
        return {
            "byte_length": self.byte_length,
            "sha256": self.sha256,
            "section_ids": list(self.section_ids),
            "imports": [
                {"module": i.module, "name": i.name, "kind": i.kind}
                for i in self.imports
            ],
            "exports": [
                {"name": e.name, "kind": e.kind, "index": e.index}
                for e in self.exports
            ],
        }


def encode_u32_leb128(value: int) -> bytes:
    """Encode an unsigned 32-bit integer into canonical LEB128 bytes."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 0xFFFFFFFF:
        raise ValueError("value must be an unsigned 32-bit integer")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _read_u32_leb128(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    for count in range(5):
        if pos >= len(buf):
            raise WasmParseError("truncated LEB128 integer")
        byte = buf[pos]
        pos += 1
        if count == 4 and (byte & 0xF0) != 0:
            raise WasmParseError("u32 LEB128 overflow")
        result |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            return result, pos
        shift += 7
    raise WasmParseError("u32 LEB128 exceeds 5 bytes")


def _read_name(buf: bytes, pos: int) -> tuple[str, int]:
    length, pos = _read_u32_leb128(buf, pos)
    end = pos + length
    if end > len(buf):
        raise WasmParseError("truncated UTF-8 name in WebAssembly section")
    try:
        text = buf[pos:end].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WasmParseError(f"invalid UTF-8 name: {exc}") from exc
    return text, end


def _skip_limits(buf: bytes, pos: int) -> int:
    if pos >= len(buf):
        raise WasmParseError("truncated limits descriptor")
    flags = buf[pos]
    pos += 1
    if flags not in (0, 1):
        raise WasmParseError(f"unsupported limits flags: {flags}")
    _, pos = _read_u32_leb128(buf, pos)
    if flags == 1:
        _, pos = _read_u32_leb128(buf, pos)
    return pos


def _parse_imports(payload: bytes) -> tuple[WasmImport, ...]:
    count, pos = _read_u32_leb128(payload, 0)
    imports: list[WasmImport] = []
    for _ in range(count):
        module, pos = _read_name(payload, pos)
        name, pos = _read_name(payload, pos)
        if pos >= len(payload):
            raise WasmParseError("truncated import kind byte")
        kind_byte = payload[pos]
        pos += 1
        kind = KIND_NAMES.get(kind_byte)
        if kind is None:
            raise WasmParseError(f"unknown import kind: {kind_byte}")
        if kind_byte == 0:
            _, pos = _read_u32_leb128(payload, pos)
        elif kind_byte == 1:
            if pos >= len(payload):
                raise WasmParseError("truncated table import elemtype")
            pos = _skip_limits(payload, pos + 1)
        elif kind_byte == 2:
            pos = _skip_limits(payload, pos)
        elif kind_byte == 3:
            if pos + 2 > len(payload) or payload[pos + 1] not in (0, 1):
                raise WasmParseError("invalid global import descriptor")
            pos += 2
        imports.append(WasmImport(module=module, name=name, kind=kind))
    if pos != len(payload):
        raise WasmParseError("trailing bytes in import section")
    return tuple(imports)


def _parse_exports(payload: bytes) -> tuple[WasmExport, ...]:
    count, pos = _read_u32_leb128(payload, 0)
    exports: list[WasmExport] = []
    for _ in range(count):
        name, pos = _read_name(payload, pos)
        if pos >= len(payload):
            raise WasmParseError("truncated export kind byte")
        kind_byte = payload[pos]
        pos += 1
        kind = KIND_NAMES.get(kind_byte)
        if kind is None:
            raise WasmParseError(f"unknown export kind: {kind_byte}")
        idx, pos = _read_u32_leb128(payload, pos)
        exports.append(WasmExport(name=name, kind=kind, index=idx))
    if pos != len(payload):
        raise WasmParseError("trailing bytes in export section")
    return tuple(exports)


def parse_wasm_module(data: bytes) -> WasmModuleInfo:
    """Parse and validate WebAssembly 1.0 binary framing, imports, and exports."""
    if not isinstance(data, (bytes, bytearray)):
        raise WasmParseError("WebAssembly payload must be bytes")
    raw = bytes(data)
    if len(raw) < len(WASM_MAGIC_VERSION) or raw[:8] != WASM_MAGIC_VERSION:
        raise WasmParseError("invalid WebAssembly magic or version header")

    pos = 8
    last_order = 0
    section_ids: list[int] = []
    imports: tuple[WasmImport, ...] = ()
    exports: tuple[WasmExport, ...] = ()

    while pos < len(raw):
        sec_id = raw[pos]
        pos += 1
        if sec_id != 0:
            order = _SECTION_ORDER.get(sec_id)
            if order is None:
                raise WasmParseError(f"unknown WebAssembly section id: {sec_id}")
            if order <= last_order:
                raise WasmParseError(f"duplicate or out-of-order section id: {sec_id}")
            last_order = order
        sec_size, pos = _read_u32_leb128(raw, pos)
        end = pos + sec_size
        if end > len(raw):
            raise WasmParseError(f"truncated section id {sec_id}")
        payload = raw[pos:end]
        pos = end
        section_ids.append(sec_id)
        if sec_id == 2:
            imports = _parse_imports(payload)
        elif sec_id == 7:
            exports = _parse_exports(payload)

    return WasmModuleInfo(
        byte_length=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        section_ids=tuple(section_ids),
        imports=imports,
        exports=exports,
    )
