"""Capture settings, with the gateway as the authority (7.2, SP-39, A12).

`FLYWHEEL_HOME/trace-capture.json` (schema `flywheel.trace-capture-settings/v1`)
holds `content`, `archive_transcripts` and `freeze_urls` (each off or on) and
`pending_ttl_hours`. The gateway runs the adopted copy under
`state/capture-settings/v1/owners/<owner>/adopted.json`. When the file's
digest differs from the adopted one, the change is pending: the gateway keeps
the adopted settings and the hello response says so, and the prompt hook
tells the owner. Adoption needs presence bound to the new settings' digest
and writes a custody ledger entry and a witness event. Hooks follow the
effective settings from the hello response and never read the file.
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
SUPPORTED = {"content": ("off", "on"), "archive_transcripts": ("off",),
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


def adopted(home, owner_ref: str) -> dict:
    try:
        return _valid(json.loads(_adopted_path(home, owner_ref).read_bytes())) or dict(DEFAULTS)
    except (OSError, ValueError):
        return dict(DEFAULTS)


def effective(home, owner_ref: str) -> dict:
    current = adopted(home, owner_ref)
    on_disk, valid = read_file(home)
    pending = (not valid) or (on_disk is not None and digest(on_disk) != digest(current))
    return {**current, "pending_change": pending, "file_valid": valid}


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


def data_flow(settings: dict) -> list[str]:
    """One sentence per setting: what gets stored where."""
    return [
        "Content capture " + ("on: prompts and final answers are sent to the local gateway "
                              "and kept encrypted." if settings["content"] == "on" else
                              "off: hooks send salted commitments only; no text leaves the "
                              "hook."),
        "Transcript archive " + ("on: each ended session is copied into encrypted custody."
                                 if settings["archive_transcripts"] == "on" else
                                 "off: transcripts stay only where the client keeps them."),
        "URL freezing " + ("on: URLs a prompt names are sent to the gateway and fetched."
                           if settings["freeze_urls"] == "on" else
                           "off: no URL leaves the hook and nothing is fetched."),
    ]
