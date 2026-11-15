"""The in-memory WAL reader agrees with SQLite's own view of a WAL database."""
import os
import sqlite3
import struct

import pytest

from canon import sqlite_wal


def wal_database(tmp_path, commits=3):
    db = tmp_path / "w.db"
    conn = sqlite3.connect(db, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.execute("CREATE TABLE t(n INTEGER, body TEXT)")
    for n in range(commits):
        conn.execute("INSERT INTO t VALUES (?, ?)", (n, "x" * 3000))
    return db, conn


def rows(image):
    mem = sqlite3.connect(":memory:")
    try:
        mem.deserialize(image)
        return [r[0] for r in mem.execute("SELECT n FROM t ORDER BY n")]
    finally:
        mem.close()


def files(db):
    return db.read_bytes(), (db.parent / (db.name + "-wal")).read_bytes()


def frame_bytes(main):
    return 24 + sqlite_wal.page_size(main)


def test_committed_frames_match_sqlite(tmp_path):
    db, conn = wal_database(tmp_path)
    try:
        main, wal = files(db)
        assert len(wal) > 32
        assert rows(sqlite_wal.wal_image(main, wal)) == [0, 1, 2]
    finally:
        conn.close()


def test_a_torn_or_corrupt_last_commit_falls_back_to_the_previous_one(tmp_path):
    db, conn = wal_database(tmp_path)
    try:
        main, wal = files(db)
        torn = wal[:-10]
        assert rows(sqlite_wal.wal_image(main, torn)) == [0, 1]
        corrupt = bytearray(wal)
        corrupt[-5] ^= 0xFF
        assert rows(sqlite_wal.wal_image(main, bytes(corrupt))) == [0, 1]
    finally:
        conn.close()


def test_uncommitted_spilled_frames_are_ignored(tmp_path):
    db, conn = wal_database(tmp_path, commits=1)
    try:
        conn.execute("PRAGMA cache_size=2")
        conn.execute("BEGIN")
        for n in range(100, 140):
            conn.execute("INSERT INTO t VALUES (?, ?)", (n, "y" * 3000))
        main, wal = files(db)
        _, last_commit_pages = sqlite_wal.committed_frames(wal, sqlite_wal.page_size(main))
        assert len(wal) > 32 + 2 * frame_bytes(main)  # the open transaction spilled
        assert rows(sqlite_wal.wal_image(main, wal)) == [0]
        assert last_commit_pages is not None
        conn.execute("ROLLBACK")
    finally:
        conn.close()


def big_endian_copy(wal):
    """Re-encode a little-endian WAL with big-endian checksums."""
    out = bytearray(wal)
    out[0:4] = struct.pack(">I", 0x377F0683)
    s = sqlite_wal._checksum(bytes(out[:24]), 0, 0, True)
    out[24:32] = struct.pack(">2I", *s)
    size = struct.unpack(">I", out[8:12])[0]
    for offset in range(32, len(out) - (24 + size) + 1, 24 + size):
        s = sqlite_wal._checksum(bytes(out[offset:offset + 8]), *s, True)
        s = sqlite_wal._checksum(bytes(out[offset + 24:offset + 24 + size]), *s, True)
        out[offset + 16:offset + 24] = struct.pack(">2I", *s)
    return bytes(out)


def test_big_endian_checksums_are_read(tmp_path):
    db, conn = wal_database(tmp_path)
    try:
        main, wal = files(db)
        assert struct.unpack(">I", wal[:4])[0] in (0x377F0682, 0x377F0683)
        assert rows(sqlite_wal.wal_image(main, big_endian_copy(wal))) == [0, 1, 2]
    finally:
        conn.close()


def test_foreign_wal_bytes_leave_the_main_image(tmp_path):
    db, conn = wal_database(tmp_path, commits=0)
    conn.close()
    main = db.read_bytes()
    image = sqlite_wal.wal_image(main, b"synthetic external activity" * 4)
    assert image[18:20] == b"\x01\x01"
    assert rows(image) == []


def test_page_size_mismatch_is_refused(tmp_path):
    db, conn = wal_database(tmp_path)
    try:
        main, wal = files(db)
        other = bytearray(main)
        other[16:18] = struct.pack(">H", 1024)
        with pytest.raises(ValueError, match="page size"):
            sqlite_wal.wal_image(bytes(other), wal)
    finally:
        conn.close()


def test_open_shared_does_not_block_delete(tmp_path):
    target = tmp_path / "held.bin"
    target.write_bytes(b"held")
    with sqlite_wal.open_shared(target) as stream:
        os.remove(target)
        assert stream.read() == b"held"
    assert not target.exists()


def test_open_shared_reports_a_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        sqlite_wal.open_shared(tmp_path / "missing.bin")
