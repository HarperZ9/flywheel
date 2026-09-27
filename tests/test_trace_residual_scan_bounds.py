"""The residual scan decompresses .gz files and zip members through a bounded
stream: a member larger than the read bound is counted as compressed and not
searched, and is never inflated whole into memory."""
import gzip
import io
import zipfile

from harness import trace_residual_scan as scan
from harness.trace_residual_scan import Needles, scan_paths

CANARY = b"PLANTED-RESIDUE-CANARY-" + b"q" * 64


def _needles():
    return Needles.build([CANARY.decode()])


def test_a_gz_over_the_bound_is_counted_not_inflated(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, "MAX_READ", 4096)
    monkeypatch.setattr(gzip, "decompress", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("inflated whole")))
    path = tmp_path / "big.log.gz"
    path.write_bytes(gzip.compress(b"\0" * 1_000_000))
    report = scan_paths([path], _needles())
    assert report["unsearched"]["compressed"] == 1


def test_a_zip_member_over_the_bound_is_counted_not_inflated(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, "MAX_READ", 4096)
    monkeypatch.setattr(zipfile.ZipFile, "read", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("inflated whole")))
    path = tmp_path / "big.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("a.txt", b"\0" * 1_000_000)
    report = scan_paths([path], _needles())
    assert report["unsearched"]["compressed"] == 1


def test_small_compressed_files_are_still_searched(tmp_path):
    gz, zp = tmp_path / "s.gz", tmp_path / "s.zip"
    gz.write_bytes(gzip.compress(b"x" + CANARY + b"y"))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("m.txt", b"x" + CANARY)
    zp.write_bytes(buffer.getvalue())
    report = scan_paths([gz, zp], _needles())
    assert report["total"] >= 2 and report["unsearched"]["compressed"] == 0
