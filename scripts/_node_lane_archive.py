"""Hashing, checksum listings, safe extraction and fetching for the Node lane stager.

Nothing here trusts an archive before its bytes match a pin. Extraction takes
only regular files and folders, and only inside the one prefix the caller names,
so a member such as ``package/../x`` or a link can never land outside the stage.
"""
from __future__ import annotations

import base64
import hashlib
import tarfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

USER_AGENT = "flywheel-stage-node-lanes/1"
FETCH_TIMEOUT_S = 300


class StageError(RuntimeError):
    """A pin, checksum or archive check failed; nothing from it is staged."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_sha256(path: Path, expected: str, label: str) -> None:
    actual = sha256_file(path)
    if actual != expected.lower():
        raise StageError(f"{label} sha256 {actual} does not match the pin {expected}")


def check_integrity(path: Path, integrity: str, label: str) -> None:
    """Check an npm ``sha512-<base64>`` subresource integrity string."""
    algorithm, _, encoded = integrity.partition("-")
    if algorithm != "sha512" or not encoded:
        raise StageError(f"{label} integrity must be sha512-<base64>")
    actual = base64.b64encode(hashlib.sha512(Path(path).read_bytes()).digest()).decode()
    if actual != encoded:
        raise StageError(f"{label} integrity sha512-{actual} does not match the pin")


def listed_sha256(listing: str, file_name: str) -> str | None:
    """The hash a ``<hex>  <name>`` or ``<hex> *<name>`` listing gives a file."""
    for line in listing.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and parts[1].lstrip("*") == file_name:
            return parts[0].lower()
    return None


def cross_check(listing_path: Path, file_name: str, pinned: str) -> None:
    """A published checksum file must list the archive with the pinned hash."""
    listed = listed_sha256(Path(listing_path).read_text(encoding="utf-8"), file_name)
    if listed is None:
        raise StageError(f"{Path(listing_path).name} does not list {file_name}")
    if listed != pinned.lower():
        raise StageError(
            f"{Path(listing_path).name} lists {file_name} as {listed}, not the pin {pinned}")


def _member_path(name: str, prefix: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (name.startswith(("/", "\\")) or "\\" in name or ".." in path.parts
            or ":" in name or not path.parts or path.parts[0] != prefix):
        raise StageError(f"unsafe archive member {name!r}")
    return PurePosixPath(*path.parts[1:])


def extract_npm_tgz(archive: Path, dest: Path, prefix: str = "package") -> int:
    """Extract ``<prefix>/...`` of an npm tarball into ``dest``; return the file count."""
    count = 0
    with tarfile.open(archive, mode="r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            if not (member.isfile() or member.isdir()):
                raise StageError(f"unsafe archive member {member.name!r} (not a file)")
            _member_path(member.name, prefix)
        for member in members:
            rel = _member_path(member.name, prefix)
            if not rel.parts:
                continue
            target = dest.joinpath(*rel.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                raise StageError(f"unreadable archive member {member.name!r}")
            target.write_bytes(source.read())
            count += 1
    return count


def extract_zip_members(archive: Path, root: str, members: dict[str, str],
                        dest: Path) -> None:
    """Extract ``<root>/<name>`` for each pinned member, checking each hash."""
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for name, pinned in members.items():
            if "/" in name or "\\" in name or name in ("", ".", ".."):
                raise StageError(f"unsafe archive member {name!r}")
            try:
                data = zf.read(f"{root}/{name}")
            except KeyError:
                raise StageError(f"{Path(archive).name} has no {root}/{name}") from None
            actual = hashlib.sha256(data).hexdigest()
            if actual != pinned.lower():
                raise StageError(f"{name} sha256 {actual} does not match the pin {pinned}")
            (dest / name).write_bytes(data)


def fetch(url: str, dest: Path) -> None:
    """Download ``url`` to ``dest`` over https; the caller checks the bytes."""
    if not url.startswith("https://"):
        raise StageError(f"refusing to fetch a non-https url: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    partial = Path(str(dest) + ".part")
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_S) as response, \
            partial.open("wb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)
    partial.replace(dest)


def tree_bytes(folder: Path) -> tuple[int, int]:
    """(file count, total bytes) under a folder."""
    files = [path for path in Path(folder).rglob("*") if path.is_file()]
    return len(files), sum(path.stat().st_size for path in files)

