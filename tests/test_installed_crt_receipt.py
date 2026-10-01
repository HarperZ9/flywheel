"""Publication refuses a Windows candidate whose bundled C++ runtime is older
than the toolset that compiled the app, or whose receipt names other bytes.

Runs 36835664677, 36837358359 and 36839153961 crashed on native close with
c0000005 in MSVCP140.dll after the installer staged Redist 14.29.30133 next to
an app compiled by toolset 14.5x. Run 36842151728 passed with 14.51.36247.0.
The receipts below copy the CRT fields and file digests from those runs.
"""
import copy
import hashlib
import json

import pytest

from scripts.verify_installed_candidate import RECEIPTS, verify
from tests.installed_crt_fixture import GOOD_FILES, OLD_FILES, build_manifest, crt_receipt

def write_candidate(root, crt, manifest):
    installer = root / 'Flywheel-Setup-1.2.0-x64.exe'
    installer.write_bytes(b'installer fixture')
    digest = hashlib.sha256(installer.read_bytes()).hexdigest()
    hashes = {}
    for name in RECEIPTS:
        path = root / name
        path.parent.mkdir(exist_ok=True)
        if name == 'crt-selection.json':
            # The builder writes this file from Windows PowerShell, with a BOM.
            path.write_text(json.dumps(crt), encoding='utf-8-sig')
        elif name == 'installed-build-manifest.json':
            path.write_text(json.dumps(manifest), encoding='utf-8')
        else:
            path.write_text('{"synthetic_fixture":true}')
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    summary = {'schema': 'flywheel.windows-installed-acceptance-ci/v1', 'verdict': 'PASS',
               'source_kind': 'tag-candidate', 'source_commit': 'a' * 40, 'version': '1.2.0',
               'installer_unchanged': True, 'installer': {'name': installer.name, 'sha256': digest},
               'receipt_sha256': hashes}
    (root / 'ci-installed-acceptance-summary.json').write_text(json.dumps(summary))
    return digest


def test_compatible_runtime_bound_to_installed_bytes_verifies(tmp_path):
    digest = write_candidate(tmp_path, crt_receipt(GOOD_FILES, '14.51.36247.0'),
                             build_manifest(GOOD_FILES))
    verify(tmp_path, digest, '1.2.0', 'a' * 40)


def test_runtime_older_than_toolset_refuses(tmp_path):
    # The exact shape of the crashing candidates: a 14.29 CRT under a 14.51 toolset.
    digest = write_candidate(tmp_path, crt_receipt(OLD_FILES, '14.29.30133.0'),
                             build_manifest(OLD_FILES))
    with pytest.raises(ValueError, match='CRT'):
        verify(tmp_path, digest, '1.2.0', 'a' * 40)


def test_receipt_naming_other_bytes_than_installed_refuses(tmp_path):
    # A compatible receipt does not vouch for an older CRT that was installed.
    digest = write_candidate(tmp_path, crt_receipt(GOOD_FILES, '14.51.36247.0'),
                             build_manifest(OLD_FILES))
    with pytest.raises(ValueError, match='CRT'):
        verify(tmp_path, digest, '1.2.0', 'a' * 40)


def _mutations():
    good = crt_receipt(GOOD_FILES, '14.51.36247.0')

    def change(fn):
        receipt = copy.deepcopy(good)
        fn(receipt)
        return receipt
    yield 'schema', change(lambda r: r.update(schema='other/v1'))
    yield 'arch', change(lambda r: r.update(architecture='x86'))
    yield 'file-arch', change(lambda r: r['files'][0].update(machine='x86'))
    yield 'missing-file', change(lambda r: r['files'].pop())
    yield 'duplicate-file', change(lambda r: r['files'].append(dict(r['files'][0])))
    yield 'one-old-file', change(lambda r: r['files'][2].update(version='14.29.30133.0'))
    yield 'floor-overstated', change(lambda r: r.update(runtime_floor_version='14.52.0.0'))
    yield 'bad-toolset', change(lambda r: r.update(toolset_version='latest'))
    yield 'not-v14', change(lambda r: [f.update(version='15.0.0.0') for f in r['files']])
    yield 'bad-digest', change(lambda r: r['files'][0].update(sha256='z' * 64))


@pytest.mark.parametrize('receipt', [r for _, r in _mutations()], ids=[k for k, _ in _mutations()])
def test_malformed_or_incompatible_receipt_refuses(tmp_path, receipt):
    digest = write_candidate(tmp_path, receipt, build_manifest(GOOD_FILES))
    with pytest.raises(ValueError, match='CRT'):
        verify(tmp_path, digest, '1.2.0', 'a' * 40)


def test_installed_crt_outside_app_root_does_not_count(tmp_path):
    manifest = build_manifest({})
    manifest['payload']['files'] += [{'origin': 'build', 'path': 'engine/' + n, 'sha256': h, 'size': 1}
                                     for n, h in GOOD_FILES.items()]
    digest = write_candidate(tmp_path, crt_receipt(GOOD_FILES, '14.51.36247.0'), manifest)
    with pytest.raises(ValueError, match='CRT'):
        verify(tmp_path, digest, '1.2.0', 'a' * 40)
