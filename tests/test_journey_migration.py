import hashlib
import json
from pathlib import PurePosixPath

import pytest

import harness.journey_migration as migration
from harness.evidence_journey import new_journey
from harness.journey_migration import import_v1_snapshot, migrate_packet, migrate_store
from harness.journey_store import JourneyStore, JourneyStoreError


OWNER = "owner_import_aaaaaaaaaaaaaaaaaaaaaaaaaaaa"
IMPORTED_AT = "2026-08-14T19:00:00Z"
LEGACY_AT = "2026-08-12T12:00:00Z"


def _legacy_bytes():
    snapshot = new_journey(
        journey_id="legacy-journey", goal="Preserve source evidence",
        intake={"summary": "legacy", "receipt_refs": ["receipt:old"]},
        created_at=LEGACY_AT,
    )
    return snapshot, json.dumps(snapshot, indent=3, sort_keys=False).encode()


def _version_path(root):
    return root / "journeys" / "version.json"


def _write_version(root, version, *, indent=2):
    path = _version_path(root)
    path.parent.mkdir(parents=True)
    path.write_bytes(json.dumps({"schema": "flywheel.evidence-journey-store-version/v1",
                                 "version": version}, indent=indent).encode())
    return path


def test_import_cites_raw_snapshot_without_inventing_preimport_custody(tmp_path):
    """Dropping the source digest, custody null, or server import time must fail."""
    legacy, raw = _legacy_bytes()
    source = tmp_path / "legacy" / "journey-v1.json"
    source.parent.mkdir()
    source.write_bytes(raw)
    supplied = {
        "snapshot_ref": "legacy/journey-v1.json", "snapshot": legacy,
        "legacy_refs": {
            "chats": ["legacy/chats.json"], "workspaces": ["legacy/workspaces.json"],
            "settings": ["legacy/settings.json"], "receipts": ["legacy/receipts.json"],
        },
    }

    ack = import_v1_snapshot(
        supplied, actor_id=OWNER, store=JourneyStore(tmp_path), created_at=IMPORTED_AT,
    )

    event_path = next((tmp_path / "journeys" / "v2" / "owners" / OWNER /
                       ack.journey_ref / "events").glob("*.json"))
    event = json.loads(event_path.read_bytes())
    intake = event["payload"]["intake"]
    assert source.read_bytes() == raw
    assert event["occurred_at"] == IMPORTED_AT
    assert intake["snapshot_ref"] == "legacy/journey-v1.json"
    assert intake["snapshot_sha256"] == hashlib.sha256(raw).hexdigest()
    assert intake["custody_before_import"] is False
    assert intake["legacy_timestamp_facts"] == {"created_at": LEGACY_AT,
                                                  "event_occurred_at": []}
    assert intake["legacy_refs"] == supplied["legacy_refs"]
    assert all(key not in intake for key in ("chats", "workspaces", "settings", "receipts"))


@pytest.mark.parametrize("ref", ["../private.json", "/private.json", "C:/private.json", "a\\b.json"])
def test_import_rejects_snapshot_or_legacy_refs_that_are_not_safe_relative(tmp_path, ref):
    """Allowing host or traversal refs would expose data beyond the store root."""
    legacy, _ = _legacy_bytes()
    with pytest.raises(ValueError, match="safe relative"):
        import_v1_snapshot(
            {"snapshot_ref": ref, "snapshot": legacy, "legacy_refs": {}},
            actor_id=OWNER, store=JourneyStore(tmp_path), created_at=IMPORTED_AT,
        )


def test_packet_migration_derives_new_bytes_and_binds_the_immutable_source_tree(tmp_path):
    """Rewriting packet input or omitting a tree digest would sever provenance."""
    packet = tmp_path / "packet-v1"
    (packet / "raw").mkdir(parents=True)
    (packet / "manifest.json").write_bytes(b'{  "schema": "packet/v1" }\n')
    (packet / "raw" / "evidence.txt").write_bytes(b"source evidence\r\n")
    before = {path.relative_to(packet).as_posix(): path.read_bytes()
              for path in packet.rglob("*") if path.is_file()}

    result = migrate_packet(
        packet, target_schema="flywheel.evidence-packet/v2", out_root=tmp_path / "derived",
    )

    after = {path.relative_to(packet).as_posix(): path.read_bytes()
             for path in packet.rglob("*") if path.is_file()}
    descriptor = json.loads((tmp_path / "derived" / result["derived_packet_ref"] /
                             "migration.json").read_bytes())
    assert after == before
    assert descriptor["target_schema"] == "flywheel.evidence-packet/v2"
    assert descriptor["source_sha256"] == result["source_sha256"]
    assert PurePosixPath(result["derived_packet_ref"]).is_absolute() is False


def test_store_migration_writes_backup_and_journal_before_pointer_and_is_idempotent(
        tmp_path, monkeypatch):
    """Replacing the pointer before durable recovery records would make rollback unsafe."""
    pointer = _write_version(tmp_path, 1, indent=4)
    original = pointer.read_bytes()
    real_replace = migration._atomic_replace

    def assert_prepared(path, data):
        if path == pointer:
            assert (tmp_path / "journeys/migrations/v1-to-v2/version.backup.json").read_bytes() == original
            journal = json.loads((tmp_path / "journeys/migrations/v1-to-v2/journal.json").read_bytes())
            assert journal["status"] == "prepared"
        return real_replace(path, data)

    monkeypatch.setattr(migration, "_atomic_replace", assert_prepared)
    first = migrate_store(tmp_path, target_version=2)
    second = migrate_store(tmp_path, target_version=2)

    assert first["migrated"] is True and second["migrated"] is False
    assert json.loads(pointer.read_bytes())["version"] == 2
    assert first["backup_ref"] == "journeys/migrations/v1-to-v2/version.backup.json"
    assert first["journal_ref"] == "journeys/migrations/v1-to-v2/journal.json"
    assert second["backup_ref"] == first["backup_ref"]
    assert second["journal_ref"] == first["journal_ref"]


def test_failed_store_migration_restores_pointer_and_preserves_v1_bytes(tmp_path, monkeypatch):
    """A failed pointer swap must leave the exact prior version and legacy bytes readable."""
    pointer = _write_version(tmp_path, 1, indent=4)
    legacy = tmp_path / "journeys" / "v1" / "snapshot.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b'{ "legacy": true }\n')
    pointer_before, legacy_before = pointer.read_bytes(), legacy.read_bytes()
    real_replace, failed = migration._atomic_replace, False

    def fail_once(path, data):
        nonlocal failed
        if path == pointer and not failed:
            failed = True
            raise OSError(r"C:\private\secret")
        return real_replace(path, data)

    monkeypatch.setattr(migration, "_atomic_replace", fail_once)
    with pytest.raises(JourneyStoreError) as failure:
        migrate_store(tmp_path, target_version=2)

    assert failure.value.code == str(failure.value) == "STORE_COMMIT_FAILED"
    assert pointer.read_bytes() == pointer_before and legacy.read_bytes() == legacy_before
    journal = json.loads((tmp_path / "journeys/migrations/v1-to-v2/journal.json").read_bytes())
    assert journal["status"] == "rolled_back"


def test_newer_store_version_stays_read_only_and_reports_fixed_mutation_error(tmp_path):
    """Auto-downgrading a newer store would rewrite data under an older contract."""
    pointer = _write_version(tmp_path, 3)
    before = pointer.read_bytes()

    result = migrate_store(tmp_path, target_version=2)

    assert result["read_only"] is True
    assert result["mutation_error"] == "VERSION_MISMATCH"
    assert pointer.read_bytes() == before
