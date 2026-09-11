# Flywheel metadata upgrade quarantine

The Windows installer quarantines only Flywheel-owned Python package metadata
before copying the new frozen engine payload. It scans direct children of
`{app}\engine\_internal` whose names end in `.dist-info` or `.egg-info`, reads
`METADATA` or `PKG-INFO`, and moves only entries whose normalized `Name:` is
`flywheel-verify`.

Successful upgrades keep the quarantined metadata under the install parent:
`FlywheelMetadataQuarantine\metadata-<app-version>-<timestamp>\`. This is
intentional preservation, not runtime state. The app does not read it. Each
quarantine has `metadata-quarantine-receipt.json` with relative source and
quarantine roots, package name and version, file sizes, SHA-256 hashes, and the
candidate metadata root that replaced it.

The uninstaller does not remove the sibling quarantine today. That avoids a
destructive cleanup path until exact schema-and-hash cleanup is separately
reviewed. The retained footprint is bounded to metadata roots listed in the
receipt plus the receipt files themselves. No wildcard deletion owns this
directory.

If setup fails after metadata moves, the installer attempts same-volume rollback
without overwriting a recreated source path or following a reparse-point parent.
When rollback cannot prove restoration, the receipt status is `repair_required`
and the `rollback` object records `unresolved_conflict`. Manual restoration must
follow the receipt's relative paths and hashes and must stop if the target source
path already exists, an ancestor is a reparse point, or hashes do not match.
