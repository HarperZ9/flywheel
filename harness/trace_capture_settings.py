"""Capture settings, with the gateway as the authority (7.2, SP-39, A12).

`FLYWHEEL_HOME/trace-capture.json` (schema `flywheel.trace-capture-settings/v1`)
holds `content`, `archive_transcripts` and `freeze_urls` (each off or on) and
`pending_ttl_hours`. The gateway runs the adopted copy under
`state/capture-settings/v1/owners/<owner>/adopted.json`. When the file's
digest differs from the adopted one, the change is pending: the gateway keeps
the adopted settings and the hello response says so, and the prompt hook
tells the owner. Adoption needs presence bound to the new settings' digest
and writes a custody ledger entry and a witness event. An adopted file whose
digest is not the latest capture adoption in the verified custody ledger is
SETTINGS_TAMPERED: the gateway runs the defaults (everything off) and the
hello response says so. Hooks follow the effective settings from the hello
response and never read the file.
"""
from __future__ import annotations

import json
from pathlib import Path

from .evidence_json import canonical_bytes, canonical_sha256

SCHEMA = "flywheel.trace-capture-settings/v1"
FILENAME = "trace-capture.json"
DEFAULTS = {"content": "off", "archive_transcripts": "off", "freeze_urls": "off",
            "pending_ttl_hours": 24}
SWITCHES = ("content", "archive_transcripts", "freeze_urls")
#: Values this version can act on. A switch whose feature is not built yet
#: accepts only "off", so no file can advertise a behavior that does not run.
SUPPORTED = {"content": ("off", "on"), "archive_transcripts": ("off", "on"),
             "freeze_urls": ("off", "on")}


def _valid(doc) -> dict | None:
    if type(doc) is not dict or set(doc) - set(DEFAULTS) - {"schema"}:
        return None
    merged = {**DEFAULTS, **{k: v for k, v in doc.items() if k != "schema"}}
    if any(merged[k] not in SUPPORTED[k] for k in SWITCHES):
        return None
    ttl = merged["pending_ttl_hours"]
    if type(ttl) is not int or not 1 <= ttl <= 24 * 30:
        return None
    return merged


def digest(settings: dict) -> str:
    return canonical_sha256({"schema": SCHEMA, **settings})


def _adopted_path(home, owner_ref: str) -> Path:
    return Path(home) / "state" / "capture-settings" / "v1" / "owners" / owner_ref / "adopted.json"


def read_file(home) -> tuple[dict | None, bool]:
    """(settings in the file or None, whether the file is valid)."""
    path = Path(home) / FILENAME
    try:
        doc = json.loads(path.read_bytes())
    except FileNotFoundError:
        return None, True
    except (OSError, ValueError):
        return None, False
    merged = _valid(doc)
    return merged, merged is not None


def _adopted(home, owner_ref: str) -> tuple[dict, bool]:
    """(settings in effect, whether the adopted file failed the ledger check)."""
    from .trace_settings_guard import matches
    try:
        doc = _valid(json.loads(_adopted_path(home, owner_ref).read_bytes()))
    except (OSError, ValueError):
        return dict(DEFAULTS), False
    if doc is None:
        return dict(DEFAULTS), False
    if not matches(home, owner_ref, "capture", digest(doc)):
        return dict(DEFAULTS), True
    return doc, False


def adopted(home, owner_ref: str) -> dict:
    return _adopted(home, owner_ref)[0]


def effective(home, owner_ref: str) -> dict:
    current, tampered = _adopted(home, owner_ref)
    on_disk, valid = read_file(home)
    pending = (not valid) or (on_disk is not None and digest(on_disk) != digest(current))
    return {**current, "pending_change": pending or tampered, "file_valid": valid,
            "tampered": tampered}


def write_file(home, changes: dict) -> dict:
    """Write the settings file with `changes` applied; nothing takes effect
    until `adopt`."""
    base, valid = read_file(home)
    merged = _valid({**(base if valid and base else DEFAULTS), **changes})
    if merged is None:
        raise ValueError("SETTINGS_INVALID")
    path = Path(home) / FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes({"schema": SCHEMA, **merged}))
    return merged


def adopt(home, owner_ref: str, presence_ref, *, sink=None) -> dict:
    """Adopt the file's settings after presence bound to their digest."""
    from .trace_presence import PresenceError, require
    from .trace_witness import record_custody_event
    on_disk, valid = read_file(home)
    if not valid or on_disk is None:
        raise PresenceError("SETTINGS_INVALID")
    value = digest(on_disk)
    method = require(Path(home) / "state", owner_ref, "capture_settings", value, presence_ref)
    path = _adopted_path(home, owner_ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("adopted.json.tmp")
    temporary.write_bytes(canonical_bytes({"schema": SCHEMA, **on_disk}))
    temporary.replace(path)
    return record_custody_event(Path(home), owner_ref, "settings_adopted",
                                {"settings": "capture", "digest": value}, method, sink=sink)


def kept() -> str:
    """How custody keeps content on this machine: encrypted, or plaintext."""
    from .trace_enc import default_provider
    return ("kept encrypted" if default_provider().name != "none" else
            "kept in plaintext (no OS key store; status says so)")


def data_flow(settings: dict, *, home=None) -> list[str]:
    """One sentence per setting: what gets stored where."""
    how = kept()
    return [
        "Content capture " + (f"on: prompts and final answers are sent to the local gateway "
                              f"and {how}." if settings["content"] == "on" else
                              "off: hooks send salted commitments only; no text leaves the "
                              "hook."),
        "Transcript archive " + (f"on: each ended Claude Code session's transcript is "
                                 f"imported into custody and {how}."
                                 if settings["archive_transcripts"] == "on" else
                                 "off: transcripts stay only where the client keeps them."),
        "URL freezing " + (f"on: URLs a prompt names are sent to the gateway and fetched; "
                           f"the pages are {how}, and the URLs with their sha256 digests go "
                           f"into the model context, so to the model provider."
                           if settings["freeze_urls"] == "on" else
                           "off: no URL leaves the hook and nothing is fetched."),
    ]
