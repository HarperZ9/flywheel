"""License texts the frozen engine ships under ``_internal/licenses/``.

The engine folder redistributes the Python runtime (and OpenSSL through it) and
every manifest lane frozen from pinned source. Each one ships its license text
beside it:

    licenses/python/LICENSE.txt       the LICENSE.txt of the Python that froze the
                                      engine: the PSF license plus the texts the
                                      Windows build appends (OpenSSL's Apache
                                      License 2.0, libffi, bzip2, Tcl/Tk and the
                                      Microsoft Distributable Code conditions)
    licenses/python/incorporated/     the Python 3.12 documentation's texts for
                                      the code compiled into the runtime that
                                      LICENSE.txt does not carry (expat, zlib,
                                      libmpdec and the rest)
    licenses/python-lanes/<lane>/     each lane's license, hash-checked against
                                      the pin in packaging/python-lane-payloads.jsonl

A missing or drifted text raises, so a freeze cannot ship a component without
its license.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.frozen_payload_datas import FreezeInputError, _hash_file

REPO = Path(__file__).resolve().parents[1]
PYTHON_LICENSE_DEST = "licenses/python"
INCORPORATED_DEST = "licenses/python/incorporated"
LANE_LICENSE_DEST = "licenses/python-lanes"
INCORPORATED_DIR = REPO / "packaging" / "licenses" / "python-incorporated"


def incorporated_license_files(folder: Path = INCORPORATED_DIR) -> list[Path]:
    """The reviewed incorporated-software texts, sorted by name."""
    return sorted(path for path in Path(folder).glob("*.txt") if path.is_file())


def python_runtime_license_datas(base_prefix: Path | str | None = None, *,
                                 incorporated_dir: Path = INCORPORATED_DIR
                                 ) -> list[tuple[str, str]]:
    """PyInstaller datas for the runtime's license texts."""
    root = Path(base_prefix if base_prefix is not None else sys.base_prefix)
    license_txt = root / "LICENSE.txt"
    if not license_txt.is_file():
        raise FreezeInputError(
            f"the build Python has no LICENSE.txt at {root}; the engine cannot ship "
            "the Python runtime without it")
    incorporated = incorporated_license_files(incorporated_dir)
    if not incorporated:
        raise FreezeInputError(f"no incorporated-software license texts in {incorporated_dir}")
    datas = [(str(license_txt), PYTHON_LICENSE_DEST)]
    datas.extend((str(path), INCORPORATED_DEST) for path in incorporated)
    return datas


def _manifest_rows(repo: Path) -> list[dict]:
    manifest = Path(repo) / "packaging" / "python-lane-payloads.jsonl"
    return [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _lane_license(row: dict, checkout: Path, notice: dict) -> Path:
    lane = row["lane"]
    path = (checkout / str(notice["path"])).resolve()
    if not path.is_relative_to(checkout):
        raise FreezeInputError(f"{lane}: license {notice['path']} escapes its checkout")
    if not path.is_file() or _hash_file(path) != notice["sha256"]:
        raise FreezeInputError(
            f"{lane}: license {notice['path']} missing or hash mismatch with its pin")
    return path


def python_lane_license_datas(repo: Path | str, source_root: Path | str
                              ) -> list[tuple[str, str]]:
    """PyInstaller datas for every manifest lane's license, relay included.

    Licenses resolve against the full checkout ``<source_root>/<lane>-<tag>``,
    which a sliced lane keeps beside its ``-slice`` import tree."""
    datas: list[tuple[str, str]] = []
    for row in _manifest_rows(Path(repo)):
        notices = row["owner_project"].get("license_files") or []
        if not notices:
            raise FreezeInputError(f"{row['lane']}: manifest row pins no license file")
        checkout = (Path(source_root) / f"{row['lane']}-{row['owner_tag']}").resolve()
        for notice in notices:
            path = _lane_license(row, checkout, notice)
            datas.append((str(path), f"{LANE_LICENSE_DEST}/{row['lane']}"))
    return datas


def frozen_license_datas(repo: Path | str, source_root: Path | str,
                         base_prefix: Path | str | None = None) -> list[tuple[str, str]]:
    """Every license text the frozen engine ships."""
    return [*python_runtime_license_datas(base_prefix),
            *python_lane_license_datas(repo, source_root)]
