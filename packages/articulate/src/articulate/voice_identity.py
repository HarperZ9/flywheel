"""The local identity a personal voice profile belongs to, and moving a
profile between the user's own computers.

identity.json in the voice store holds an owner_id (a random UUID made on this
computer the first time a profile is learned) and an optional display name.
Every profile records the owner_id it was learned under. compare, apply and
their MCP tools refuse a profile whose owner differs from the local identity.

This binding is a consent and provenance record. It guards against accidents
and casual reuse of someone else's profile; a local user who edits the JSON
can defeat it, so it is not access control.

Only the command line calls ensure_identity, export, import and delete_all.
"""
import hashlib
import json
import os
import pathlib
import tempfile
import uuid

from . import voice_store

EXPORT_SCHEMA = "articulate/voice-export/v1"
IDENTITY = "identity.json"


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def profile_sha256(profile):
    return "sha256:" + hashlib.sha256(_canonical(profile).encode("utf-8")).hexdigest()


def identity_path(directory=None):
    return voice_store.store_dir(directory) / IDENTITY


def load_identity(directory=None):
    try:
        with open(identity_path(directory), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("owner_id"), str):
        raise ValueError("identity.json in the voice store is damaged; see articulate voice identity")
    return data


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    ignore = path.parent / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
    fd, tmp = tempfile.mkstemp(prefix=".voice-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(value, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path


def ensure_identity(directory=None, display_name=None, owner_id=None):
    """The local identity, made on first use. Command line only."""
    current = load_identity(directory)
    if current is None:
        current = {"owner_id": owner_id or str(uuid.uuid4()), "display_name": display_name}
    elif display_name is not None:
        current["display_name"] = display_name
    _write_json(identity_path(directory), current)
    return current


def bind(profile, directory=None, when=None):
    """The profile with the local owner and the user's attestation attached."""
    ident = load_identity(directory)
    if ident is None:
        raise ValueError("no local identity; run articulate voice learn or voice identity first")
    out = dict(profile)
    out["owner"] = {"owner_id": ident["owner_id"], "display_name": ident.get("display_name")}
    out["attestation"] = {"mine": True, "at": when or _now()}
    return out


def _now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def check_owner(profile, directory=None):
    """Raise ValueError unless the profile belongs to the local identity."""
    ident = load_identity(directory)
    owner = (profile.get("owner") or {}).get("owner_id") if isinstance(profile, dict) else None
    if owner is None:
        raise ValueError("this profile has no owner; learn it again with articulate voice learn --mine")
    if ident is None or ident["owner_id"] != owner:
        raise ValueError("this profile belongs to a different owner than this computer's voice "
                         "identity, so it is not used. Learn your own with articulate voice learn")
    return True


def export_profile(name, directory=None):
    profile = voice_store.load(name, directory)
    check_owner(profile, directory)
    return {"schema": EXPORT_SCHEMA, "name": name, "owner": profile["owner"],
            "profile": profile, "profile_sha256": profile_sha256(profile)}


def import_profile(data, directory=None, adopt_identity=False):
    """Save an exported profile. Returns the saved path."""
    if not isinstance(data, dict) or data.get("schema") != EXPORT_SCHEMA:
        raise ValueError("not an articulate voice export")
    profile = data.get("profile")
    if not isinstance(profile, dict) or profile_sha256(profile) != data.get("profile_sha256"):
        raise ValueError("the export's profile does not match its hash; it was changed after export")
    owner = (profile.get("owner") or {}).get("owner_id")
    ident = load_identity(directory)
    if ident is None:
        if not adopt_identity:
            raise ValueError("this computer has no voice identity yet; pass --adopt-identity "
                             "to take the export's owner as yours")
        ensure_identity(directory, profile["owner"].get("display_name"), owner_id=owner)
    elif ident["owner_id"] != owner:
        raise ValueError("this export belongs to a different owner than this computer's voice "
                         "identity; a store holds one owner")
    return voice_store.save(profile, data.get("name") or "imported", directory)


def delete_all(directory=None):
    """Remove every profile, the identity file, the store .gitignore and the
    folder when it is empty. Returns each path removed."""
    folder = voice_store.store_dir(directory)
    removed = [voice_store.delete(n, directory) for n in voice_store.names(directory)]
    for name in (IDENTITY, ".gitignore"):
        path = folder / name
        if path.is_file():
            path.unlink()
            removed.append(path)
    if folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
        removed.append(pathlib.Path(folder))
    return removed
