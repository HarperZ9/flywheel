"""Publication refuses missing or changed evidence from the exact installed candidate."""
import hashlib
import json

import pytest

from scripts.verify_installed_candidate import verify, RECEIPTS
from tests.installed_crt_fixture import GOOD_FILES, build_manifest, crt_receipt


@pytest.fixture
def candidate(tmp_path):
    installer = tmp_path / 'Flywheel-Setup-1.2.0-x64.exe'
    installer.write_bytes(b'installer fixture')
    digest = hashlib.sha256(installer.read_bytes()).hexdigest()
    hashes = {}
    for name in RECEIPTS:
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        if name == 'crt-selection.json':
            path.write_text(json.dumps(crt_receipt(GOOD_FILES, '14.51.36247.0')))
        elif name == 'installed-build-manifest.json':
            path.write_text(json.dumps(build_manifest(GOOD_FILES)))
        else:
            path.write_text('{"synthetic_fixture":true}')
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    summary = {'schema': 'flywheel.windows-installed-acceptance-ci/v1', 'verdict': 'PASS',
        'source_kind': 'tag-candidate', 'source_commit': 'a' * 40, 'version': '1.2.0',
        'installer_unchanged': True, 'installer': {'name': installer.name, 'sha256': digest},
        'receipt_sha256': hashes}
    (tmp_path / 'ci-installed-acceptance-summary.json').write_text(json.dumps(summary))
    return tmp_path, digest, summary


def test_exact_evidence_binding(candidate):
    root, digest, _ = candidate
    verify(root, digest, '1.2.0', 'a' * 40)


@pytest.mark.parametrize('change', ['source', 'kind', 'hash', 'missing', 'changed', 'hold', 'manifest', 'crt'])
def test_wrong_candidate_or_missing_evidence_refuses(candidate, change):
    root, digest, summary = candidate
    if change == 'source':
        summary['source_commit'] = 'b' * 40
    elif change == 'kind':
        summary['source_kind'] = 'rebuilt-ci'
    elif change == 'hash':
        digest = '0' * 64
    elif change == 'hold':
        summary['verdict'] = 'HOLD'
    elif change == 'missing':
        (root / RECEIPTS[0]).unlink()
    elif change == 'manifest':
        (root / 'installed-build-manifest.json').write_text('changed')
    elif change == 'crt':
        (root / 'crt-selection.json').write_text('changed')
    else:
        (root / RECEIPTS[0]).write_text('changed')
    (root / 'ci-installed-acceptance-summary.json').write_text(json.dumps(summary))
    with pytest.raises((ValueError, OSError)):
        verify(root, digest, '1.2.0', 'a' * 40)
