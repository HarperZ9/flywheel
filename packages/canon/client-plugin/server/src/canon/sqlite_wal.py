"""Read a SQLite database and its write-ahead log without opening them in SQLite.

`open_shared` opens a file for reading only. On Windows it also allows other
processes to delete or rename the file while it is open, so a writer that ends
a transaction or leaves WAL mode is never blocked by a reader.

`wal_image` applies the committed frames of a WAL file to a database image by
the recovery rules in the SQLite file format: a frame counts only when its salts
match the WAL header and its running checksum verifies, and frames after the
last valid commit frame are ignored. The result is an image in rollback-journal
form for `sqlite3.Connection.deserialize`. Nothing is written to disk.
"""
import os
import struct

SQLITE_MAGIC = b"SQLite format 3\x00"
ROLLBACK_HEADER = b"\x01\x01"
WAL_HEADER = b"\x02\x02"
_WAL_MAGIC = (0x377F0682, 0x377F0683)
_WAL_VERSION = 3007000
_WAL_HEADER_BYTES = 32
_FRAME_HEADER_BYTES = 24
_GENERIC_READ = 0x80000000
_SHARE_READ_WRITE_DELETE = 0x7
_OPEN_EXISTING = 3
_ATTRIBUTE_NORMAL = 0x80


def open_shared(path):
    """Open `path` read-only without blocking another process's delete or rename."""
    if os.name != "nt":
        return open(path, "rb")
    import _winapi
    import msvcrt
    handle = _winapi.CreateFile(str(path), _GENERIC_READ, _SHARE_READ_WRITE_DELETE, 0,
                                _OPEN_EXISTING, _ATTRIBUTE_NORMAL, 0)
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        _winapi.CloseHandle(handle)
        raise
    return os.fdopen(fd, "rb")


def page_size(image):
    """The page size declared in a database header (the value 1 means 65536)."""
    size = struct.unpack(">H", image[16:18])[0]
    return 65536 if size == 1 else size


def _checksum(data, s0, s1, big_endian):
    words = struct.unpack((">" if big_endian else "<") + f"{len(data) // 4}I", data)
    for i in range(0, len(words), 2):
        s0 = (s0 + words[i] + s1) & 0xFFFFFFFF
        s1 = (s1 + words[i + 1] + s0) & 0xFFFFFFFF
    return s0, s1


def committed_frames(wal, size):
    """Map page number to frame offset for the last valid commit, and its page count.

    A missing, short or foreign WAL file holds no committed frames, as it does
    for SQLite's own recovery. A valid WAL whose page size differs from the
    database's is refused, since no consistent image exists.
    """
    if len(wal) < _WAL_HEADER_BYTES:
        return {}, None
    magic, version, wal_page, _seq, salt1, salt2, c0, c1 = struct.unpack(">8I", wal[:32])
    big_endian = bool(magic & 1)
    if magic not in _WAL_MAGIC or version != _WAL_VERSION:
        return {}, None
    if _checksum(wal[:24], 0, 0, big_endian) != (c0, c1):
        return {}, None
    if wal_page != size:
        raise ValueError("write-ahead log page size does not match the database")
    frame_bytes = _FRAME_HEADER_BYTES + size
    running, pending, committed, pages = (c0, c1), {}, {}, None
    for offset in range(_WAL_HEADER_BYTES, len(wal) - frame_bytes + 1, frame_bytes):
        pgno, commit, f_salt1, f_salt2, f0, f1 = struct.unpack(">6I", wal[offset:offset + 24])
        if pgno == 0 or (f_salt1, f_salt2) != (salt1, salt2):
            break
        running = _checksum(wal[offset:offset + 8], *running, big_endian)
        running = _checksum(wal[offset + 24:offset + frame_bytes], *running, big_endian)
        if running != (f0, f1):
            break
        pending[pgno] = offset + _FRAME_HEADER_BYTES
        if commit:
            committed.update(pending)
            pending, pages = {}, commit
    return committed, pages


def wal_image(main, wal):
    """The database image a WAL-mode reader would see, in rollback-journal form."""
    size = page_size(main)
    frames, pages = committed_frames(wal or b"", size)
    image = bytearray(main)
    if pages is not None:
        length = pages * size
        image = image[:length] + bytearray(max(0, length - len(image)))
        for pgno, offset in frames.items():
            if pgno <= pages:
                image[(pgno - 1) * size:pgno * size] = wal[offset:offset + size]
        image[28:32] = struct.pack(">I", pages)
        image[92:96] = image[24:28]
    if bytes(image[:16]) != SQLITE_MAGIC:
        raise ValueError("context database is not a SQLite database")
    image[18:20] = ROLLBACK_HEADER
    return bytes(image)
