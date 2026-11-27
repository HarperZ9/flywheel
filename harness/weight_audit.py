"""weight_audit.py -- Local owner-rights binary & weight-manifest integrity scanner (stdlib only).

Audits a local model, container, or binary directory offline to enforce two owner-rights
invariants fail-closed:
  1. Every weight blob and native binary matches an explicit SHA-256 + RFC 6962 Merkle
     manifest (catching unhashed weight blobs, missing artifacts, and 1-byte tampering).
  2. Static AST and config inspection catches unauthorized outbound sockets, undocumented
     telemetry endpoints, and locked-firmware/audit-bypass paths outside loopback or an
     operator-declared host allowlist.
"""

from __future__ import annotations

import ast
import hashlib
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .merkle import merkle_root
from .receipt_fields import canonical

MANIFEST_SCHEMA = "flywheel.weight-manifest/v1"
AUDIT_SCHEMA = "flywheel.weight-audit-report/v1"

WEIGHT_AND_BINARY_EXTS = frozenset({
    ".safetensors", ".gguf", ".bin", ".pt", ".pth", ".onnx",
    ".ckpt", ".pb", ".tflite", ".so", ".dll", ".dylib", ".exe", ".wasm",
})
CODE_AND_CONFIG_EXTS = frozenset({
    ".py", ".sh", ".ps1", ".js", ".mjs", ".ts", ".json", ".toml", ".yaml", ".yml",
})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

_TELEMETRY_MODULES = frozenset({
    "posthog", "sentry_sdk", "mixpanel", "segment", "analytics", "telemetry", "opentelemetry",
})
_NETWORK_MODULES = frozenset({
    "socket", "urllib.request", "http.client", "requests", "httpx", "aiohttp", "ftplib", "smtplib",
})
_URL_RE = re.compile(r"\b(?:https?|wss?)://[^\s\"'<>`]+", re.IGNORECASE)
_SHELL_EGRESS_RE = re.compile(
    r"\b(?:curl|wget|nc|ncat|Invoke-WebRequest|Invoke-RestMethod)\b",
    re.IGNORECASE,
)
_LOCKED_FIRMWARE_RE = re.compile(
    r"\b(?:locked_firmware|disable_local_audit|bypass_weight_verify|phone_home)\b"
    r"|telemetry_opt_out\s*[:=]\s*false",
    re.IGNORECASE,
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _manifest_merkle(entries: list[dict[str, Any]]) -> str:
    leaves = [canonical(e).encode("utf-8") for e in sorted(entries, key=lambda item: item["path"])]
    return "sha256:" + merkle_root(leaves).hex()


def _iter_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in {".git", "__pycache__", ".venv", "venv"} for part in path.parts):
            continue
        out.append(path)
    return out


def _is_weight_or_binary(path: Path, extra_exts: frozenset[str]) -> bool:
    return path.suffix.lower() in (WEIGHT_AND_BINARY_EXTS | extra_exts)


def build_weight_manifest(
    root: Path,
    *,
    allow_hosts: Sequence[str] = (),
    extra_exts: Sequence[str] = (),
) -> dict[str, Any]:
    """Hash every weight blob and binary under `root` and seal an RFC 6962 manifest."""
    base = Path(root)
    extra = frozenset(e.lower() for e in extra_exts)
    entries: list[dict[str, Any]] = []
    for path in _iter_files(base):
        if not _is_weight_or_binary(path, extra):
            continue
        entries.append({
            "path": path.relative_to(base).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        })
    entries.sort(key=lambda item: item["path"])
    return {
        "schema": MANIFEST_SCHEMA,
        "allow_hosts": sorted({h.lower() for h in allow_hosts}),
        "file_count": len(entries),
        "entries": entries,
        "merkle_root": _manifest_merkle(entries),
    }


def _host_allowed(host: str | None, allow_hosts: frozenset[str]) -> bool:
    if not host:
        return False
    norm = host.strip().lower().strip("[]")
    return norm in LOOPBACK_HOSTS or norm in allow_hosts


def _literal_target_host(node: ast.Call) -> str | None:
    if not node.args:
        return None
    arg0 = node.args[0]
    if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
        val = arg0.value.strip()
        if "://" in val:
            return urlparse(val).hostname
        return val
    if isinstance(arg0, (ast.Tuple, ast.List)) and arg0.elts:
        first = arg0.elts[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value.strip()
    return None


def _dotted_name(node: ast.AST) -> str:
    parts: list[str] = []
    cur: ast.AST | None = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return ""


def _scan_python_ast(rel: str, text: str, allow_hosts: frozenset[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [{"code": "UNPARSEABLE_PYTHON", "path": rel, "line": exc.lineno or 1, "detail": str(exc)}]

    net_aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                if mod.split(".")[0] in _TELEMETRY_MODULES:
                    findings.append({"code": "UNDOCUMENTED_TELEMETRY", "path": rel, "line": node.lineno, "detail": f"telemetry import {mod}"})
                if mod in _NETWORK_MODULES or mod.split(".")[0] in _NETWORK_MODULES:
                    net_aliases[alias.asname or mod] = mod
                    net_aliases[alias.asname or mod.split(".")[0]] = mod
        elif isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module
            if mod.split(".")[0] in _TELEMETRY_MODULES:
                findings.append({"code": "UNDOCUMENTED_TELEMETRY", "path": rel, "line": node.lineno, "detail": f"telemetry import {mod}"})
            if mod in _NETWORK_MODULES or mod.split(".")[0] in _NETWORK_MODULES:
                for alias in node.names:
                    net_aliases[alias.asname or alias.name] = f"{mod}.{alias.name}"

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        raw_name = _dotted_name(node.func)
        if not raw_name:
            continue
        head = raw_name.split(".")[0]
        if raw_name in net_aliases:
            call_name = net_aliases[raw_name]
        elif head in net_aliases:
            call_name = net_aliases[head] + raw_name[len(head):]
        elif raw_name.rsplit(".", 1)[-1] in {"connect", "connect_ex", "create_connection"}:
            call_name = f"socket.{raw_name.rsplit('.', 1)[-1]}"
        else:
            continue

        if any(tok in call_name for tok in (
            "connect", "urlopen", "HTTPConnection", "HTTPSConnection",
            "requests.", "httpx.", "aiohttp.", "ftplib.", "smtplib.",
        )):
            host = _literal_target_host(node)
            if not _host_allowed(host, allow_hosts):
                findings.append({
                    "code": "UNAUTHORIZED_OUTBOUND_SOCKET", "path": rel,
                    "line": node.lineno, "detail": f"{call_name} target={host or '<dynamic>'}",
                })
    return findings


def _finding(code: str, path: str, line: int, detail: str) -> dict[str, Any]:
    return {"code": code, "path": path, "line": line, "detail": detail}


def scan_static_outbound_and_telemetry(
    root: Path, *, allow_hosts: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Statically scan code and config files under `root` for unauthorized egress or telemetry."""
    base = Path(root)
    allowed = frozenset(h.lower() for h in allow_hosts)
    findings: list[dict[str, Any]] = []

    for path in _iter_files(base):
        rel = path.relative_to(base).as_posix()
        suffix = path.suffix.lower()
        is_dockerfile = path.name.lower() == "dockerfile"
        if suffix not in CODE_AND_CONFIG_EXTS and not is_dockerfile:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".py":
            findings.extend(_scan_python_ast(rel, text, allowed))

        for lineno, line in enumerate(text.splitlines(), start=1):
            if _LOCKED_FIRMWARE_RE.search(line):
                findings.append(_finding("LOCKED_FIRMWARE_OR_AUDIT_BYPASS", rel, lineno, line.strip()[:120]))
            for match in _URL_RE.finditer(line):
                host = urlparse(match.group(0)).hostname
                if not _host_allowed(host, allowed):
                    findings.append(_finding("UNDOCUMENTED_OUTBOUND_URL", rel, lineno, f"host={host or '<unknown>'}"))
            if (suffix in {".sh", ".ps1"} or is_dockerfile) and _SHELL_EGRESS_RE.search(line):
                if not any(h in line.lower() for h in LOOPBACK_HOSTS):
                    findings.append(_finding("UNAUTHORIZED_OUTBOUND_SOCKET", rel, lineno, line.strip()[:120]))
    return findings


def audit_artifact_root(
    root: Path, manifest: dict[str, Any] | None = None, *,
    allow_hosts: Sequence[str] = (), extra_exts: Sequence[str] = (),
) -> dict[str, Any]:
    """Verify weight/binary manifest integrity and static egress/telemetry hygiene fail-closed."""
    base = Path(root)
    extra = frozenset(e.lower() for e in extra_exts)
    effective_hosts = sorted({h.lower() for h in allow_hosts} | {
        h.lower() for h in (manifest.get("allow_hosts", []) if manifest else [])
    })
    findings: list[dict[str, Any]] = []
    manifest_root = ""
    disk_blobs = {p.relative_to(base).as_posix(): p for p in _iter_files(base) if _is_weight_or_binary(p, extra)}

    if manifest is None:
        findings.extend(_finding("UNHASHED_WEIGHT_OR_BINARY", rel, 0, "no manifest") for rel in sorted(disk_blobs))
    else:
        if manifest.get("schema") != MANIFEST_SCHEMA:
            findings.append(_finding("MANIFEST_SCHEMA_MISMATCH", "<manifest>", 0, str(manifest.get("schema"))))
        entries = list(manifest.get("entries", []))
        manifest_root = _manifest_merkle(entries)
        if manifest.get("merkle_root") != manifest_root:
            findings.append(_finding("MANIFEST_MERKLE_TAMPER", "<manifest>", 0, "merkle root mismatch"))
        listed = {e["path"]: e for e in entries}
        for rel, entry in sorted(listed.items()):
            path = disk_blobs.get(rel)
            if path is None:
                findings.append(_finding("MISSING_MANIFEST_FILE", rel, 0, "listed file absent"))
                continue
            actual_sha = _sha256_file(path)
            if path.stat().st_size != entry.get("size_bytes") or actual_sha != entry.get("sha256"):
                findings.append(_finding("TAMPERED_WEIGHT_OR_BINARY", rel, 0, f"expected={entry.get('sha256')} actual={actual_sha}"))
        for rel in sorted(set(disk_blobs) - set(listed)):
            findings.append(_finding("UNHASHED_WEIGHT_OR_BINARY", rel, 0, "unlisted on disk"))

    findings.extend(scan_static_outbound_and_telemetry(base, allow_hosts=effective_hosts))
    ok = not findings
    body = {
        "schema": AUDIT_SCHEMA, "verdict": "PASS" if ok else "FAIL", "ok": ok,
        "weights_and_binaries_checked": len(disk_blobs), "manifest_merkle_root": manifest_root,
        "finding_counts": dict(Counter(f["code"] for f in findings)), "findings": findings,
    }
    return {**body, "report_sha256": "sha256:" + hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()}
