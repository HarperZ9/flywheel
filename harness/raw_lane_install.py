"""Install and locate the raw lane's native binary, fail-closed on any digest mismatch.

The raw lane runs raw-native's release binary. Flywheel ships no copy of it:
``install`` fetches the release asset for this platform from the raw-native
GitHub release by URL, and accepts it only when three digests agree:

1. ``SHA256SUMS`` from the release hashes to the digest pinned here, so a
   rewritten sums file is refused;
2. the archive hashes to its row in that ``SHA256SUMS``;
3. the binary inside the archive hashes to the digest pinned here.

Anything else is refused with ``TOOLCHAIN_MISSING`` and nothing is written.
``resolve`` re-hashes the installed binary before every use, so a binary
swapped after install is refused the same way. raw-native is licensed
FSL-1.1-MIT by its author; the person installing the lane fetches it from the
author's release, and Flywheel redistributes nothing.
"""
from __future__ import annotations

import hashlib
import io
import os
import platform as _platform
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from .lane_workdir import flywheel_home

VERSION = "0.4.0"
RELEASE_URL = f"https://github.com/HarperZ9/raw-native/releases/download/v{VERSION}/"
TOOLCHAIN_MISSING = "TOOLCHAIN_MISSING"
MAX_DOWNLOAD = 64 * 1024 * 1024


@dataclass(frozen=True)
class Asset:
    archive: str
    member: str
    binary_sha256: str


@dataclass(frozen=True)
class Pins:
    """What an install must match. Tests pass their own; the lane uses PINS."""
    version: str
    base_url: str
    sums_sha256: str
    assets: Mapping[str, Asset] = field(default_factory=dict)


PINS = Pins(VERSION, RELEASE_URL,
            "7cbcd1ad2fcae3fdca01c1b9999186ff23f26b87ee510561271ef518af92c4a2", {
                "windows-x64": Asset(
                    "raw-native-0.4.0-windows-x64.zip",
                    "raw-native-0.4.0-windows-x64/raw_native_cli.exe",
                    "12e4942ad45bf6ca73c3058b08acdf8a0fb2d281a0248c5ee671bfff901ec162"),
                "linux-x64": Asset(
                    "raw-native-0.4.0-linux-x64.tar.gz",
                    "raw-native-0.4.0-linux-x64/raw_native_cli",
                    "e0e9c428f22a3eb33df0c019e327e0e998f6d9516034440bf7d0fae2039bccb8"),
            })


class Refused(Exception):
    """An install or a lookup that must not proceed; the message says why."""


def platform_key(system: str | None = None, machine: str | None = None) -> str | None:
    """``windows-x64`` or ``linux-x64``, or None where raw-native ships no build."""
    system = (system or _platform.system()).lower()
    machine = (machine or _platform.machine()).lower()
    if machine not in ("amd64", "x86_64"):
        return None
    return {"windows": "windows-x64", "linux": "linux-x64"}.get(system)


def install_dir(environ: Mapping[str, str] | None = None, pins: Pins = PINS,
                plat: str | None = None) -> Path:
    env = os.environ if environ is None else environ
    return flywheel_home(env) / "lanes" / "raw" / pins.version / (plat or platform_key() or "none")


def binary_path(environ=None, pins: Pins = PINS, plat: str | None = None) -> Path:
    plat = plat or platform_key()
    name = Path(pins.assets[plat].member).name if plat in pins.assets else "raw_native_cli"
    return install_dir(environ, pins, plat) / name


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def matches_pin(path: Path, digest: str) -> bool:
    """True when the file at ``path`` still hashes to ``digest``."""
    return sha256(path.read_bytes()) == digest


def https_fetch(url: str, timeout: float = 60.0) -> bytes:
    """The release download: https only, bounded in size."""
    if not url.startswith("https://"):
        raise Refused(f"refusing a non-https URL: {url}")
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (https only)
        data = resp.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise Refused(f"{url} is larger than {MAX_DOWNLOAD} bytes")
    return data


def parse_sums(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            out[parts[1].lstrip("*").strip()] = parts[0].lower()
    return out


def extract_member(archive: str, data: bytes, member: str) -> bytes:
    """Read exactly one named member; nothing else in the archive is touched."""
    if archive.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return zf.read(member)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        handle = tf.extractfile(member)
        if handle is None:
            raise Refused(f"{member} is not a regular file in {archive}")
        return handle.read()


def resolve(environ=None, pins: Pins = PINS, plat: str | None = None) -> Path:
    """The installed binary, re-hashed now. Raises Refused when it is absent,
    unsupported here, or no longer the pinned bytes."""
    plat = plat or platform_key()
    if plat not in pins.assets:
        raise Refused(f"raw-native {pins.version} ships no build for "
                      f"{_platform.system()} {_platform.machine()}")
    path = binary_path(environ, pins, plat)
    if not path.is_file():
        raise Refused(f"raw-native {pins.version} is not installed; run "
                      "`flywheel install --lanes raw`")
    if not matches_pin(path, pins.assets[plat].binary_sha256):
        raise Refused(f"{path.name} does not match its pinned SHA-256; the binary was "
                      "replaced after install. Reinstall the lane.")
    return path


def _verified_binary(pins: Pins, plat: str, fetch: Callable[[str], bytes]) -> bytes:
    asset = pins.assets[plat]
    sums_bytes = fetch(pins.base_url + "SHA256SUMS")
    if sha256(sums_bytes) != pins.sums_sha256:
        raise Refused("SHA256SUMS does not match the digest pinned for this release")
    expected = parse_sums(sums_bytes.decode("utf-8", "replace")).get(asset.archive)
    if not expected:
        raise Refused(f"SHA256SUMS has no row for {asset.archive}")
    archive = fetch(pins.base_url + asset.archive)
    if sha256(archive) != expected:
        raise Refused(f"{asset.archive} does not match its SHA256SUMS row")
    binary = extract_member(asset.archive, archive, asset.member)
    if sha256(binary) != asset.binary_sha256:
        raise Refused(f"{asset.member} does not match the binary digest pinned here")
    return binary


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".partial")
    tmp.write_bytes(data)
    os.chmod(tmp, 0o755)
    os.replace(tmp, path)


def install(environ=None, *, pins: Pins = PINS, plat: str | None = None,
            fetch: Callable[[str], bytes] = https_fetch) -> dict:
    """Fetch, check and place the binary. Returns the lane install row."""
    row = {"name": "raw", "version": pins.version}
    plat = plat or platform_key()
    if plat not in pins.assets:
        return {**row, "installed": False, "code": TOOLCHAIN_MISSING,
                "detail": f"raw-native {pins.version} ships no build for this platform"}
    try:
        return {**row, "installed": True, "code": "",
                "detail": f"already installed: {resolve(environ, pins, plat).name}"}
    except Refused:
        pass
    try:
        binary = _verified_binary(pins, plat, fetch)
    except Refused as e:
        return {**row, "installed": False, "code": TOOLCHAIN_MISSING, "detail": str(e)}
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, tarfile.TarError) as e:
        return {**row, "installed": False, "code": TOOLCHAIN_MISSING,
                "detail": f"release asset unreachable or unreadable: {type(e).__name__}: {e}"}
    path = binary_path(environ, pins, plat)
    _write(path, binary)
    return {**row, "installed": True, "code": "", "detail": f"installed {path.name} "
            f"({plat}), SHA-256 {pins.assets[plat].binary_sha256[:16]}..."}
