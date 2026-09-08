"""Private continuation context and public projection helpers."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .bundle import BundleError, safe_relative, scan_for_secrets
from .evidence_public import TransportError, public_metadata

PRIVATE_CONTEXT_SCHEMA = "flywheel.native-continuation-private-context/v1"
RUNNER_CONTEXT_SCHEMA = "flywheel.native-continuation-runner-context/v1"

_AUTH_BEARER = re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[^\s,;]+")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)\b(?:[a-z][a-z0-9_-]*[_-])?"
    r"(?:token|private[_ -]?key|credential|secret|password|passwd|"
    r"api[_ -]?key|access[_ -]?key|(?:access|refresh)[_ -]?token|"
    r"client[_ -]?secret)['\"]?\s*[:=]\s*"
    r"(?:\"(?:\\(?:[\s\S]|$)|[^\"\\])*(?:\"|$)|"
    r"'(?:\\(?:[\s\S]|$)|[^'\\])*(?:'|$)|[^\s,;]+)")
_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN ((?:[A-Z0-9]+ )*PRIVATE KEY)-----[\s\S]*?"
    r"(?:-----END \1-----|$)")
_HOST_PATH = re.compile(
    r"[A-Za-z]:[\\/]|(?:^|\s)/(?:Users|home|dev|tmp|var|etc|root)(?:/|\s|$)")


def safe_public_text(text: str) -> str | None:
    value = " ".join(text.strip().split())[:180]
    if not value or scan_for_secrets(value) or _HOST_PATH.search(value):
        return None
    try:
        public_metadata(value)
    except TransportError:
        return None
    return value


def credential_reasons(text: str) -> list[str]:
    hits = bool(_AUTH_BEARER.search(text) or _BEARER.search(text)
                or _PRIVATE_KEY_BLOCK.search(text)
                or _CREDENTIAL_ASSIGNMENT.search(text)
                or scan_for_secrets(text))
    return ["CREDENTIAL_EXCLUDED"] if hits else []


def scrub_credentials(text: str) -> str:
    """Remove known spans before parsing signals, retaining source line breaks."""
    def omitted(match: re.Match) -> str:
        # Keep a marker between separate CR and LF lines; concatenating their
        # endings would turn them into one CRLF and corrupt source positions.
        return re.sub(r"[^\n\r\v\f\x1c-\x1e\x85\u2028\u2029]+",
                      "[credential omitted]", match.group())

    value = _PRIVATE_KEY_BLOCK.sub(omitted, text)
    value = _AUTH_BEARER.sub(omitted, value)
    value = _BEARER.sub(omitted, value)
    value = _CREDENTIAL_ASSIGNMENT.sub(omitted, value)
    return value


def safe_signal_text(text: str) -> tuple[str | None, list[str]]:
    reasons = credential_reasons(text)
    value = scrub_credentials(text)
    if scan_for_secrets(value):
        return None, sorted(set([*reasons, "CREDENTIAL_EXCLUDED"]))
    value = " ".join(value.strip().split())[:180]
    if not value:
        return None, reasons
    if _HOST_PATH.search(value):
        return None, sorted(set([*reasons, "HOST_PATH_EXCLUDED"]))
    try:
        public_metadata(value)
    except TransportError:
        return None, reasons
    return value, reasons


def selected_file(text: str) -> str | None:
    try:
        return safe_relative(text).as_posix()
    except (BundleError, TypeError, ValueError):
        return None


def context_package(export: dict[str, Any], preview_ref: str) -> dict[str, Any]:
    tasks, summaries, files, commits = [], [], [], []
    for signal in export.get("signals", []):
        if not isinstance(signal, dict) or type(signal.get("text")) is not str:
            continue
        text = signal["text"]
        if signal.get("kind") in {"user_direction", "unfinished"}:
            tasks.append(text)
        elif signal.get("kind") == "summary":
            summaries.append(text)
        elif signal.get("kind") == "artifact":
            selected = selected_file(text)
            if selected:
                files.append(selected)
        elif signal.get("kind") == "commit":
            commits.append(text)
    return {"schema": "flywheel.native-continuation-context/v1",
            "retrieval": {"mode": "bounded_private_preview",
                          "preview_ref": preview_ref},
            "selected_tasks": tasks[:4], "selected_summaries": summaries[:4],
            "selected_files": files[:8], "commits": commits[:8],
            "does_not_prove": [
                "selected context is complete",
                "a future model loaded every selected item"]}


def public_context_projection(context: dict[str, Any]) -> dict[str, Any]:
    preview_ref = str(context.get("retrieval", {}).get("preview_ref", ""))
    ref = f"continuation-private/{preview_ref}/context"
    return {"schema": "flywheel.native-continuation-context-projection/v1",
            "retrieval": {"mode": "private_local_preview",
                          "private_context_ref": ref, "preview_ref": preview_ref},
            "private_context_ref": ref,
            "selected_task_count": len(context.get("selected_tasks", [])),
            "selected_summary_count": len(context.get("selected_summaries", [])),
            "selected_files": list(context.get("selected_files", [])),
            "commits": list(context.get("commits", [])),
            "private_text_policy": "selected task and summary text remains in local private preview storage",
            "does_not_prove": [
                "public projection contains enough text to continue the task",
                "a future model loaded every selected item"]}


def public_export_projection(export: dict[str, Any]) -> dict[str, Any]:
    projected = {key: export[key] for key in (
        "state", "sha256", "prefix_sha256", "bytes", "read_bytes", "truncated")
        if key in export}
    projected["signals"] = [{key: signal[key] for key in (
        "kind", "line", "sha256", "redacted", "redaction_reasons")
        if key in signal}
        for signal in export.get("signals", []) if isinstance(signal, dict)]
    projected["private_text_policy"] = (
        "signal text is stored only in the private preview record")
    return projected


def runner_context(root: Path, context: dict[str, Any],
                   source_state_sha256: str) -> dict[str, Any]:
    tasks = [str(item) for item in context.get("selected_tasks", []) if str(item).strip()]
    summaries = [str(item) for item in context.get("selected_summaries", []) if str(item).strip()]
    files = [str(item) for item in context.get("selected_files", []) if str(item).strip()]
    parts = ["Continue this provider-neutral Flywheel continuation from the private local context."]
    if tasks:
        parts.append("Selected task context:\n" + "\n".join(f"- {item}" for item in tasks))
    if summaries:
        parts.append("Selected prior summaries:\n" + "\n".join(f"- {item}" for item in summaries))
    if files:
        parts.append("Selected files to inspect before editing:\n" + "\n".join(f"- {item}" for item in files))
    parts.append("Preserve fresh grants, verify source state before work, and report omissions explicitly.")
    parts.append("This is portable local continuation; it is not provider-native web session resume.")
    return {"schema": RUNNER_CONTEXT_SCHEMA, "source_state_sha256": source_state_sha256,
            "root": str(root), "goal": "\n\n".join(parts), "selected_files": files,
            "retrieval": context["retrieval"], "does_not_prove": [
                "provider-native web session resume",
                "selected context is complete",
                "a future model executed the task"]}
