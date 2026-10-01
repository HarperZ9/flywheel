"""The source companion preserves the restricted MCP and exact source identity."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tomllib
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']


def test_source_bundle_carries_contained_tools_with_required_user_roots(tmp_path):
    output = tmp_path / 'source'
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/build_source_tool_plugin.py'),
                             '--out', str(output), '--dev'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    archive, = output.glob('flywheel-tools-*-dev-source-plugin.zip')
    with zipfile.ZipFile(archive) as package:
        names = set(package.namelist())
        manifest = json.loads(package.read('.claude-plugin/plugin.json'))
        launch = json.loads(package.read('.mcp.json'))['mcpServers']['flywheel']
        identity = json.loads(package.read('SOURCE.json'))
        assert manifest['name'] == 'flywheel-tools'
        assert manifest['displayName'] == 'Flywheel tools'
        assert set(manifest['userConfig']) == {'workspace', 'state'}
        assert all(row['type'] == 'directory' and row['required'] is True
                   and 'default' not in row for row in manifest['userConfig'].values())
        assert launch['command'] == 'python3'
        assert launch['args'] == ['-I', '-S', '-B', '${CLAUDE_PLUGIN_ROOT}/server/serve.py',
                                 '--root', '${user_config.workspace}', '--run-root', '${user_config.state}']
        assert not launch.get('env')
        assert identity['mode'] == 'development' and identity['version'] == VERSION
        assert {'pyproject.toml', 'LICENSE', 'scripts/source_tool_closure.json',
                'scripts/source_tool_manifests.py', 'scripts/build_source_tool_plugin.py',
                'plugins/flywheel-tools/server/serve.py', 'plugins/flywheel-tools/README.md'} <= set(identity['input_provenance'])
        assert 'unpublished' in package.read('README.md').decode().lower()
        assert '.codex-plugin/plugin.json' in names and 'plugin.json' in names and 'mcp.json' in names
        assert len(names) < 100 and all(info.file_size < 256 * 1024 for info in package.infolist())
        for name, expected in identity['payload_sha256'].items():
            assert hashlib.sha256(package.read(name)).hexdigest() == expected
        for name in names:
            assert not name.endswith(('.exe', '.dll', '.pyc', '.sqlite'))
        assert package.read('server/harness/tool_mcp.py') == (ROOT / 'harness/tool_mcp.py').read_text(encoding='utf-8').encode('utf-8')
    sums = output / 'source-plugin-SHA256SUMS.txt'
    assert hashlib.sha256(archive.read_bytes()).hexdigest() in sums.read_text()


def test_minimal_closure_refuses_new_unreviewed_local_dependency(tmp_path):
    from scripts.source_tool_payload import REVIEW, reviewed_payload
    for name in json.loads(REVIEW.read_text()):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    target = tmp_path / 'harness/tool_mcp.py'
    target.write_bytes(target.read_bytes() + b'\nfrom harness.gateway import gateway\n')
    with pytest.raises(ValueError, match='reviewed|closure'):
        reviewed_payload(tmp_path)


@pytest.mark.parametrize('newline', ['\n', '\r\n'])
def test_source_closure_is_independent_of_checkout_line_endings(tmp_path, newline):
    from scripts.source_tool_payload import REVIEW, TEMPLATE, TEMPLATE_FILES, reviewed_payload
    paths = [*json.loads(REVIEW.read_text()), 'pyproject.toml', 'LICENSE',
             *(TEMPLATE + '/' + name for name in TEMPLATE_FILES)]
    for name in paths:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        text = (ROOT / name).read_text(encoding='utf-8')
        target.write_bytes(text.replace('\n', newline).encode('utf-8'))
    assert reviewed_payload(tmp_path) == reviewed_payload(ROOT)


def test_missing_reviewed_module_refuses_before_output(tmp_path):
    from scripts.source_tool_payload import reviewed_payload
    with pytest.raises((ValueError, FileNotFoundError)):
        reviewed_payload(tmp_path)


def test_output_directory_is_never_overwritten(tmp_path):
    from scripts.build_source_tool_plugin import bundle
    output = tmp_path / 'occupied'
    output.mkdir()
    sentinel = output / 'existing.txt'
    sentinel.write_text('preserve')
    with pytest.raises(FileExistsError):
        bundle(output, dev=True)
    assert sentinel.read_text() == 'preserve'


def test_release_source_requires_clean_exact_tag(tmp_path):
    from scripts.build_source_tool_plugin import bundle
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'pyproject.toml').write_text('[project]\nversion="1.2.0"\n')
    for args in (['init', '-q'], ['config', 'user.name', 'Fixture'],
                 ['config', 'user.email', 'fixture@example.invalid'], ['add', '.'],
                 ['commit', '-qm', 'fixture']):
        subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)
    with pytest.raises(ValueError, match='tag'):
        bundle(tmp_path / 'untagged', repo=repo)
    subprocess.run(['git', '-C', str(repo), 'tag', 'v1.2.0'], check=True)
    (repo / 'dirty.txt').write_text('unpublished')
    with pytest.raises(ValueError, match='clean'):
        bundle(tmp_path / 'dirty', repo=repo)


def test_source_checksum_verifier_rejects_modified_archive(tmp_path):
    from scripts.build_source_tool_plugin import bundle, verify
    archive = bundle(tmp_path / 'artifact', dev=True)
    sums = archive.parent / 'source-plugin-SHA256SUMS.txt'
    accepted = hashlib.sha256(sums.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='release'):
        verify(sums, accepted, VERSION)
    archive.write_bytes(archive.read_bytes() + b'changed')
    with pytest.raises(ValueError):
        verify(sums, accepted, VERSION, dev=True)


def test_source_zip_is_reproducible_without_output_path_data(tmp_path):
    from scripts.build_source_tool_plugin import bundle
    first = bundle(tmp_path / 'first', dev=True)
    second = bundle(tmp_path / 'second', dev=True)
    assert first.read_bytes() == second.read_bytes()
