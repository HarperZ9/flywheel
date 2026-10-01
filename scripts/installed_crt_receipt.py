"""Check the Windows CRT selection receipt against the installed payload.

Release candidates 1f2869c5, f4e967d1 and 561e3f29 crashed on native close
(c0000005 in MSVCP140.dll) because the installer staged Redist 14.29.30133 next
to an app compiled by toolset 14.5x. desktop/scripts/crt_selection.ps1 now picks
a coherent Redist set at or above the toolset and writes crt-selection.json.

Publication binds that receipt by digest. This module also reads it, so a
candidate whose receipt records an older runtime, or names CRT bytes other than
the ones the installed payload manifest lists at the app root, is refused even
when every digest matches. Stdlib only.
"""
from __future__ import annotations

import re

SCHEMA = 'flywheel.windows-crt-selection/v1'
CRT_NAMES = ('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')
_TOOLSET = re.compile(r'14\.[0-9]+\.[0-9]+')
_FILE_VERSION = re.compile(r'14\.[0-9]+\.[0-9]+\.[0-9]+')
_DIGEST = re.compile(r'[0-9a-f]{64}')


def _version(text: object, pattern: re.Pattern[str]) -> tuple[int, ...]:
    if not isinstance(text, str) or not pattern.fullmatch(text):
        raise ValueError(f'CRT receipt version {text!r} is not a supported v14 version')
    return tuple(int(part) for part in text.split('.'))


def _receipt_files(receipt: dict) -> dict[str, tuple[tuple[int, ...], str]]:
    files = receipt.get('files')
    if not isinstance(files, list) or len(files) != len(CRT_NAMES):
        raise ValueError('CRT receipt must list exactly the three x64 runtime DLLs')
    found: dict[str, tuple[tuple[int, ...], str]] = {}
    for item in files:
        name = item.get('name') if isinstance(item, dict) else None
        if name not in CRT_NAMES or name in found or item.get('machine') != 'x64':
            raise ValueError('CRT receipt names an unexpected, duplicate or non-x64 DLL')
        digest = item.get('sha256')
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            raise ValueError('CRT receipt digest is not lowercase sha256')
        found[name] = (_version(item.get('version'), _FILE_VERSION), digest)
    return found


def _installed_crt(manifest: dict) -> dict[str, str]:
    payload = manifest.get('payload') if isinstance(manifest, dict) else None
    entries = payload.get('files') if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ValueError('CRT check needs the installed payload file list')
    installed: dict[str, list[str]] = {name: [] for name in CRT_NAMES}
    for entry in entries:
        path = entry.get('path') if isinstance(entry, dict) else None
        # The app loads its CRT from its own folder, so only root entries count.
        if isinstance(path, str) and path.lower() in installed:
            installed[path.lower()].append(str(entry.get('sha256')))
    if any(len(digests) != 1 for digests in installed.values()):
        raise ValueError('installed payload must hold each CRT DLL once at the app root')
    return {name: digests[0] for name, digests in installed.items()}


def check_crt_receipt(receipt: dict, manifest: dict) -> None:
    """Raise ValueError unless the installed CRT is the compatible set the receipt records."""
    if not isinstance(receipt, dict) or receipt.get('schema') != SCHEMA:
        raise ValueError('CRT receipt schema mismatch')
    if receipt.get('architecture') != 'x64':
        raise ValueError('CRT receipt architecture is not x64')
    toolset = _version(receipt.get('toolset_version'), _TOOLSET)
    files = _receipt_files(receipt)
    floor = min(version for version, _ in files.values())
    if floor < toolset:
        raise ValueError('CRT runtime is older than the MSVC toolset that built the app')
    if _version(receipt.get('runtime_floor_version'), _FILE_VERSION) != floor:
        raise ValueError('CRT receipt floor does not match its oldest DLL')
    installed = _installed_crt(manifest)
    if any(installed[name] != digest for name, (_, digest) in files.items()):
        raise ValueError('installed CRT bytes differ from the CRT receipt')
