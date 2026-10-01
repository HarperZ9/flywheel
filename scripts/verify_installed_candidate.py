"""Bind archived CI acceptance evidence to the exact candidate before publication.

This verifies bytes and source identity; it relies on the upstream checked CI
phase for the meaning of its PASS. It is not external attestation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from desktop.tool.installed_payload_binding import _scan_files

RECEIPTS = tuple('installed-acceptance/' + name + '.json' for name in (
    'installed-launch-full', 'installed-launch-inspect', 'installed-canon-context',
    'installed-tool-profiles', 'installed-native-ui', 'installed-lanes-per-user',
    'installed-lanes-all-users')) + ('installed-build-manifest.json', 'crt-selection.json')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(root, accepted_hash, version, commit):
    files = dict(_scan_files(Path(root)))
    summary_path = files.get('ci-installed-acceptance-summary.json')
    if summary_path is None or summary_path.stat().st_size > 256000:
        raise ValueError('installed acceptance summary missing or oversized')
    summary = json.loads(summary_path.read_text(encoding='utf-8-sig'))
    if (summary.get('schema') != 'flywheel.windows-installed-acceptance-ci/v1'
            or summary.get('verdict') != 'PASS' or summary.get('source_kind') != 'tag-candidate'
            or summary.get('source_commit') != commit or not re.fullmatch('[0-9a-f]{40}', commit)
            or summary.get('version') != version or not re.fullmatch(r'[0-9]+\.[0-9]+\.0', version)
            or summary.get('installer_unchanged') is not True):
        raise ValueError('installed acceptance source or result mismatch')
    installers = [name for name in files if re.fullmatch(r'Flywheel-Setup-[^/]+\.exe', name)]
    binding = summary.get('installer', {})
    if (len(installers) != 1 or installers[0] != binding.get('name')
            or binding.get('sha256') != accepted_hash
            or not re.fullmatch('[0-9a-f]{64}', accepted_hash)
            or sha(files[installers[0]]) != accepted_hash):
        raise ValueError('accepted installer bytes differ from installed candidate')
    hashes = summary.get('receipt_sha256', {})
    if set(hashes) != set(RECEIPTS):
        raise ValueError('installed acceptance evidence inventory incomplete')
    for name in RECEIPTS:
        if name not in files or files[name].stat().st_size > 10000000 or sha(files[name]) != hashes[name]:
            raise ValueError('installed acceptance evidence bytes missing or changed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--accepted-installer-sha256', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    verify(args.candidate, args.accepted_installer_sha256, args.version, args.source_commit)
    print('Exact installed candidate and archived acceptance evidence verified.')
