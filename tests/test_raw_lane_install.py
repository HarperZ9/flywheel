"""The raw lane's installer: fetch by URL, check every digest, refuse on any mismatch.

Claims under test, offline against archives built here:
- a release whose SHA256SUMS, archive and binary all match installs, for the
  zip (Windows) and the tar.gz (Linux) layout;
- a rewritten SHA256SUMS, an archive that is not its SHA256SUMS row, and a
  binary that is not its pin are each refused with TOOLCHAIN_MISSING, and
  nothing is written;
- an unreachable release is TOOLCHAIN_MISSING with the cause, not a crash;
- a binary swapped after install is refused by ``resolve`` and by the lane run;
- a platform with no raw-native build is TOOLCHAIN_MISSING;
- paired mutation: a resolve that skips the digest check lets the swap through;
and live: the real 0.4.0 release installs and matches its pins.
"""
from __future__ import annotations

import hashlib
import io
import tarfile
import zipfile

import pytest

from harness import raw_lane, raw_lane_install as inst
from harness.verdict import Execution, Verdict
from tests.raw_native_fixtures import installed_home  # noqa: F401 (fixture)

BINARY = b"\x7fELF fake raw-native binary"
BASE = "https://example.invalid/raw/"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _zip(member: str, data: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(member, data)
    return buf.getvalue()


def _tgz(member: str, data: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo(member)
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _release(binary: bytes = BINARY, pinned_binary: bytes = BINARY):
    """(pins, served files) for a release built here."""
    win, lin = _zip("p/raw_native_cli.exe", binary), _tgz("p/raw_native_cli", binary)
    sums = (f"{_sha(win)}  w.zip\n{_sha(lin)}  l.tar.gz\n").encode()
    pins = inst.Pins("9.9.9", BASE, _sha(sums), {
        "windows-x64": inst.Asset("w.zip", "p/raw_native_cli.exe", _sha(pinned_binary)),
        "linux-x64": inst.Asset("l.tar.gz", "p/raw_native_cli", _sha(pinned_binary))})
    return pins, {BASE + "SHA256SUMS": sums, BASE + "w.zip": win, BASE + "l.tar.gz": lin}


def _fetcher(served: dict):
    def fetch(url: str) -> bytes:
        if url not in served:
            raise OSError(f"404 {url}")
        return served[url]
    return fetch


@pytest.mark.parametrize("plat", ["windows-x64", "linux-x64"])
def test_a_matching_release_installs(tmp_path, plat):
    pins, served = _release()
    env = {"FLYWHEEL_HOME": str(tmp_path)}
    row = inst.install(env, pins=pins, plat=plat, fetch=_fetcher(served))
    assert row["installed"] is True, row
    assert inst.resolve(env, pins, plat).read_bytes() == BINARY
    again = inst.install(env, pins=pins, plat=plat, fetch=_fetcher({}))
    assert again["installed"] and again["detail"].startswith("already installed")


@pytest.mark.parametrize("break_it,why", [
    (lambda s: s.update({BASE + "SHA256SUMS": s[BASE + "SHA256SUMS"] + b"\n"}),
     "SHA256SUMS does not match"),
    (lambda s: s.update({BASE + "w.zip": _zip("p/raw_native_cli.exe", b"other")}),
     "does not match its SHA256SUMS row"),
    (lambda s: s.pop(BASE + "w.zip"), "unreachable"),
])
def test_a_mismatch_anywhere_is_refused_and_nothing_is_written(tmp_path, break_it, why):
    pins, served = _release()
    break_it(served)
    env = {"FLYWHEEL_HOME": str(tmp_path)}
    row = inst.install(env, pins=pins, plat="windows-x64", fetch=_fetcher(served))
    assert (row["installed"], row["code"]) == (False, "TOOLCHAIN_MISSING")
    assert why in row["detail"]
    assert not inst.binary_path(env, pins, "windows-x64").exists()


def test_a_binary_that_is_not_its_pin_is_refused(tmp_path):
    pins, served = _release(binary=b"a different program", pinned_binary=BINARY)
    row = inst.install({"FLYWHEEL_HOME": str(tmp_path)}, pins=pins, plat="linux-x64",
                       fetch=_fetcher(served))
    assert row["code"] == "TOOLCHAIN_MISSING" and "binary digest pinned" in row["detail"]


def _swap_known_answer(tmp_path) -> None:
    pins, served = _release()
    env = {"FLYWHEEL_HOME": str(tmp_path)}
    assert inst.install(env, pins=pins, plat="windows-x64", fetch=_fetcher(served))["installed"]
    inst.binary_path(env, pins, "windows-x64").write_bytes(b"swapped")
    with pytest.raises(inst.Refused, match="replaced after install"):
        inst.resolve(env, pins, "windows-x64")
    run = raw_lane.run({"width": 8, "height": 8}, environ=env, pins=pins, plat="windows-x64")
    assert run.execution is Execution.TOOLCHAIN_MISSING
    assert run.result.verdict_ is Verdict.UNVERIFIABLE
    assert run.result.unverifiable_reason == "TOOLCHAIN_MISSING"


def test_a_binary_swapped_after_install_is_refused(tmp_path):
    _swap_known_answer(tmp_path)


def test_paired_mutation_a_resolve_without_the_digest_check_is_caught(tmp_path, monkeypatch):
    monkeypatch.setattr(inst, "matches_pin", lambda path, digest: True)
    with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
        _swap_known_answer(tmp_path)


def test_a_platform_without_a_build_is_toolchain_missing(tmp_path):
    assert inst.platform_key("Darwin", "arm64") is None
    assert inst.platform_key("Windows", "AMD64") == "windows-x64"
    assert inst.platform_key("Linux", "x86_64") == "linux-x64"
    pins, served = _release()
    row = inst.install({"FLYWHEEL_HOME": str(tmp_path)}, pins=pins, plat="macos-arm64",
                       fetch=_fetcher(served))
    assert row["code"] == "TOOLCHAIN_MISSING"


def test_a_non_https_url_is_refused():
    with pytest.raises(inst.Refused):
        inst.https_fetch("http://github.com/HarperZ9/raw-native/releases/download/v0.4.0/x")


def test_the_real_release_installs_and_matches_its_pins(installed_home):  # noqa: F811
    path = inst.resolve(installed_home)
    assert _sha(path.read_bytes()) == inst.PINS.assets[inst.platform_key()].binary_sha256
