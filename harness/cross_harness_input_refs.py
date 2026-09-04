"""One authority on what a required-input reference is.

The manifest and the workspace builder both read `required_inputs`, and they
disagreed. `_input_hashes` accepted `workspace://public/mneme`, deliberately
recorded no hash for it, and moved on. `create_attempt_workspace` then rejected
the same string, because a scheme carries a colon and a colon is also how a
Windows drive letter and an NTFS alternate data stream are written.

Ten of the fourteen tasks in agentic-task-set-v1 carry at least one typed
reference, so fifty of the seventy attempts in the 2026-09-03 head-to-head were
discarded before any provider was called. The receipts recorded that as
`required input invalid`, which reads like a bad task and was in fact a seam.

Both halves call `classify_reference` now, so they cannot drift apart again.
The payload rules below are the ones `_input_hashes` already enforced. Nothing
here is more permissive than what the workspace builder allowed: a typed
reference is still never copied into a sealed workspace, it is reported as
declared and not provisioned.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

SCHEMES = ("workspace", "external", "operator")
REPO_RELATIVE = "repo_relative"
SEPARATOR = "://"


def _payload_invalid(payload: str) -> bool:
    """The rules a typed payload must satisfy to be a plain relative POSIX path."""
    typed = Path(payload)
    return bool(
        not payload
        or payload != payload.strip()
        or payload.startswith(("/", "\\"))
        or (len(payload) > 1 and payload[0].isalpha() and payload[1] == ":")
        or typed.is_absolute()
        or typed.drive
        or ".." in typed.parts
        or str(typed).replace("\\", "/") != payload
    )


def classify_reference(value: Any, *, label: str = "required input") -> tuple[str, str]:
    """Return (scheme, payload), where scheme is REPO_RELATIVE for a bare path.

    A bare path is returned unchanged for the caller to validate its own way,
    because the workspace builder and the manifest check different things about
    it: one copies the file, the other only hashes it.
    """
    reference = str(value)
    if SEPARATOR not in reference:
        return REPO_RELATIVE, reference
    scheme, _, payload = reference.partition(SEPARATOR)
    if scheme not in SCHEMES or _payload_invalid(payload):
        raise ValueError(f"{label} typed reference invalid: {reference}")
    return scheme, payload


def is_typed(value: Any) -> bool:
    """True when the reference names material outside the sealed workspace."""
    return classify_reference(value)[0] != REPO_RELATIVE


def partition_inputs(required_inputs: list[Any], *, label: str = "required input",
                     pilot: bool = False) -> tuple[list[str], list[dict[str, str]]]:
    """Split declared inputs into the ones a workspace can hold and the ones it cannot.

    `pilot` refuses a typed reference outright. A task with a registered oracle
    checker is scored against a sealed workspace, so material the workspace
    cannot hold would make the score unreadable.
    """
    provisioned: list[str] = []
    unprovisioned: list[dict[str, str]] = []
    for item in required_inputs:
        scheme, payload = classify_reference(item, label=label)
        if scheme == REPO_RELATIVE:
            provisioned.append(payload)
            continue
        if pilot:
            raise ValueError(f"{label} typed reference invalid: {item}")
        unprovisioned.append({"reference": str(item), "scheme": scheme, "payload": payload})
    return provisioned, unprovisioned
