"""Provider-neutral continuation preview construction."""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

from .continuation_context import (
    context_package, credential_reasons, public_context_projection,
    public_export_projection, runner_context, safe_public_text, safe_signal_text,
    scrub_credentials,
)
from .evidence_json import canonical_sha256
from .evidence_public import TransportError, public_metadata
from .import_adapters import import_config

PREVIEW_SCHEMA = "flywheel.native-continuation-preview/v1"
INTAKE_SCHEMA = "flywheel.native-continuation-intake/v1"
MAX_EXPORT_BYTES = 1_048_576
_MAX_SIGNALS = 12
_SIGNAL_PATTERNS = (
    ("user_direction", re.compile(r"\buser\s*:\s*(.+)", re.I)),
    ("summary", re.compile(r"\bsummary\s*:\s*(.+)", re.I)),
    ("artifact", re.compile(r"\bartifact\s*:\s*(.+)", re.I)),
    ("commit", re.compile(r"\bcommit\s*:\s*([0-9a-f]{7,40})", re.I)),
    ("unfinished", re.compile(r"\b(?:unfinished|todo|next action)\s*:\s*(.+)", re.I)),
)
_ATTACHMENT = re.compile(r"\battachment\s*:\s*(.+)", re.I)
_FATAL_OMISSIONS = frozenset(("MISSING_ATTACHMENT", "MISSING_EXPORT"))


def _file_sha(path: Path) -> str | None:
    try:
        if not path.is_file():
            return None
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _run_git(root: Path, *args: str, strip: bool = True) -> tuple[int, str]:
    try:
        proc = subprocess.run(["git", "-C", str(root), *args], check=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", timeout=5)
        out = proc.stdout.strip() if strip else proc.stdout.rstrip("\r\n")
        return proc.returncode, out
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def _dirty_path(root: Path, rel: str) -> dict[str, Any]:
    clean = rel.split(" -> ")[-1].strip().strip('"')
    row: dict[str, Any] = {"path": clean}
    digest = _file_sha(root / clean)
    if digest is not None:
        row["sha256"] = digest
    return row


def repo_state(root: Path) -> dict[str, Any]:
    code, inside = _run_git(root, "rev-parse", "--is-inside-work-tree")
    if code != 0 or inside.lower() != "true":
        return {"state": "not_git", "branch": None, "head": None,
                "dirty_files": []}
    _, branch = _run_git(root, "branch", "--show-current")
    head_code, head = _run_git(root, "rev-parse", "HEAD")
    status_code, status = _run_git(root, "status", "--porcelain=v1", strip=False)
    rows = []
    if status_code == 0:
        for line in status.splitlines():
            if len(line) < 4:
                continue
            row = _dirty_path(root, line[3:])
            row["status"] = line[:2]
            rows.append(row)
    return {"state": "git", "branch": branch or "detached",
            "head": head if head_code == 0 else None,
            "dirty_files": sorted(rows, key=lambda item: item["path"])}


def _path_hint(text: str) -> str:
    return Path(text.replace("\\", "/").strip().strip('"')).name or "attachment"


def _exists_attachment(root: Path, export: Path, text: str) -> bool:
    value = text.strip().strip('"')
    candidate = Path(value)
    candidates = [candidate] if candidate.is_absolute() else [root / value, export.parent / value]
    return any(path.exists() for path in candidates)


def export_state(root: Path, export_path: Path | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    omissions: list[dict[str, Any]] = []
    if export_path is None:
        return {"state": "not_selected", "sha256": None, "signals": []}, omissions
    try:
        resolved = export_path.resolve(strict=True)
        stat = resolved.stat()
        with resolved.open("rb") as stream:
            raw = stream.read(MAX_EXPORT_BYTES + 1)
    except OSError:
        omissions.append({"code": "MISSING_EXPORT", "source": "local_export",
                          "detail": "selected export was not readable"})
        return {"state": "missing", "sha256": None, "signals": []}, omissions
    truncated = len(raw) > MAX_EXPORT_BYTES or stat.st_size > MAX_EXPORT_BYTES
    prefix = raw[:MAX_EXPORT_BYTES]
    digest = hashlib.sha256(prefix).hexdigest() if not truncated else None
    text = prefix.decode("utf-8", errors="replace")
    signals: list[dict[str, Any]] = []
    lines = zip(text.splitlines(), scrub_credentials(text).splitlines(), strict=True)
    for index, (original, line) in enumerate(lines, start=1):
        line_has_credential = original != line or bool(credential_reasons(original))
        if line_has_credential:
            omissions.append({
                "code": "CREDENTIAL_EXCLUDED",
                "source": "local_export",
                "line": index,
                "detail": "known credential-shaped text was excluded from continuation context",
            })
        attach = _ATTACHMENT.search(line)
        if attach and not _exists_attachment(root, resolved, attach.group(1)):
            omissions.append({"code": "MISSING_ATTACHMENT", "source": "local_export",
                              "line": index, "path_hint": _path_hint(attach.group(1)),
                              "detail": "attachment referenced by export was not found"})
        if len(signals) >= _MAX_SIGNALS:
            continue
        for kind, pattern in _SIGNAL_PATTERNS:
            match = pattern.search(line)
            if match:
                snippet, reasons = safe_signal_text(match.group(1))
                if line_has_credential:
                    reasons = sorted(set([*reasons, "CREDENTIAL_EXCLUDED"]))
                if "CREDENTIAL_EXCLUDED" in reasons and not line_has_credential:
                    omissions.append({
                        "code": "CREDENTIAL_EXCLUDED",
                        "source": "local_export",
                        "line": index,
                        "detail": "known credential-shaped text was excluded from continuation context",
                    })
                signals.append({"kind": kind, "line": index,
                                "sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
                                **({"text": snippet} if snippet else {"redacted": True}),
                                **({"redaction_reasons": reasons} if reasons else {})})
                break
    if truncated:
        omissions.append({"code": "EXPORT_TRUNCATED", "source": "local_export",
                          "detail": "export preview read the first bounded byte window"})
    return {"state": "read", "sha256": digest,
            "prefix_sha256": hashlib.sha256(prefix).hexdigest(),
            "bytes": stat.st_size, "read_bytes": len(prefix),
            "truncated": truncated, "signals": signals}, omissions


def _safe_mapping(row: dict[str, Any]) -> dict[str, Any]:
    allowed = {"source", "mapped_to", "status", "sha256", "servers_extracted"}
    return {key: row[key] for key in allowed if key in row}


def _safe_drop(row: dict[str, Any]) -> dict[str, Any]:
    source = safe_public_text(str(row.get("source", "source"))) or "source"
    reason = safe_public_text(str(row.get("reason", "carried nowhere"))) or "carried nowhere"
    return {"source": source, "reason": reason}


def sanitized_import(root: Path) -> dict[str, Any]:
    manifest = import_config(root)
    servers = manifest.get("profile", {}).get("mcp_servers", {})
    names = sorted(str(name) for name in servers) if isinstance(servers, dict) else []
    return {"schema": manifest["schema"],
            "mappings": [_safe_mapping(row) for row in manifest["mappings"]],
            "dropped": [_safe_drop(row) for row in manifest["dropped"]],
            "mcp_server_count": len(names), "mcp_server_names": names,
            "note": manifest["note"]}


def health_state(omissions: list[dict[str, Any]]) -> dict[str, Any]:
    blockers = sorted({row["code"] for row in omissions
                       if row.get("code") in _FATAL_OMISSIONS})
    return {"state": "blocked" if blockers else "ready",
            "blocking_omissions": blockers}


def build_continuation(root: Path, *, export_path: Path | None = None) -> tuple[dict, dict]:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise TransportError("ROOT_UNAVAILABLE", "workspace root is unavailable")
    repo = repo_state(root)
    imp = sanitized_import(root)
    export, omissions = export_state(root, export_path)
    provider = {"state": "unavailable", "reason": "no connector proved read, list, resume, or fork support"}
    source_state = {"root_sha256": hashlib.sha256(str(root).encode("utf-8")).hexdigest(),
                    "repo": repo, "import": imp, "export": export,
                    "omissions": omissions, "provider_native_resume": provider}
    source_sha = canonical_sha256(source_state)
    preview_ref = f"cpv_{source_sha[:32]}"
    context = context_package(export, preview_ref)
    run_context = runner_context(root, context, source_sha)
    health = health_state(omissions)
    intake = {"schema": INTAKE_SCHEMA, "mode": "provider_neutral",
              "preview_ref": preview_ref, "source_state_sha256": source_sha,
              "workspace": {"label": root.name, "root_sha256": source_state["root_sha256"]},
              "repo": repo, "import": imp,
              "export": public_export_projection(export),
              "context_package": public_context_projection(context), "health": health,
              "provider_native_resume": provider, "omissions": omissions,
              "does_not_prove": [
                  "native provider web session resume is unavailable",
                  "public projection contains enough text to continue the task",
                  "durable context does not prove a future model loaded it",
                  "fresh grants are required before any follow-up work"]}
    public_metadata(intake)
    intake_ref = f"continuation/{preview_ref}.intake.json"
    preview = {"schema": PREVIEW_SCHEMA, "preview_ref": preview_ref,
               "source_state_sha256": source_sha, "intake_ref": intake_ref,
               "source": {"root": str(root), "export_path": str(export_path.resolve()) if export_path else None},
               "repo": repo, "import": imp, "export": export,
               "context_package": context, "runner_context": run_context,
               "health": health,
               "provider_native_resume": provider, "omissions": omissions,
               "next_action": "start a provider-neutral Evidence Journey with fresh grants"}
    preview["preview_sha256"] = canonical_sha256(preview)
    intake["preview_sha256"] = preview["preview_sha256"]
    public_metadata(intake)
    return preview, intake
