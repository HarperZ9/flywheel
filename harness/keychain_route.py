"""Gateway helpers for keychain roster, set, and delete routes."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def keychain_get() -> dict[str, Any]:
    """Return credential presence metadata only."""
    from harness.key_roster import keychain_entries
    from harness.keychain import credential_source, keychain_available

    return {
        "schema": "flywheel.keychain/v1",
        "available": keychain_available(),
        "entries": keychain_entries(credential_source),
        "note": "presence and source only; values never leave resolution inside a routed call",
    }


def keychain_set_post(req: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Validate and route a generic keychain set request."""
    from harness.key_roster import generic_keychain_set_error
    from harness.keychain import keychain_name_error, keychain_set

    name = (req.get("name") or "").strip()
    out = keychain_name_error(name)
    if out is not None:
        return out, 400
    out = generic_keychain_set_error(name)
    if out is not None:
        return out, 400
    out = keychain_set(name, req.get("value") or "")
    return out, 400 if "error" in out else 200


def keychain_delete_post(req: dict[str, Any], flywheel_home: Path) -> tuple[dict[str, Any], int]:
    """Validate and route a keychain delete request."""
    from harness.key_roster import BULLETIN_CREDENTIAL_NAME, protected_keychain_name
    from harness.keychain import keychain_delete, keychain_name_error

    name = (req.get("name") or "").strip()
    out = keychain_name_error(name)
    if out is not None:
        return out, 400
    if protected_keychain_name(name) == BULLETIN_CREDENTIAL_NAME:
        from harness.bulletin_identity_store import delete_identity_keychain_slot

        out = delete_identity_keychain_slot(keychain_lock_root=flywheel_home / "state")
        return out, 400 if "error" in out else 200
    out = keychain_delete(name)
    return out, 400 if "error" in out else 200
