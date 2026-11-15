"""Release qualification must refuse before a build or archive creates output."""
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from claude_plugin_helpers import load, ROOT


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


@pytest.fixture
def release_source(tmp_path, monkeypatch):
    monkeypatch.delenv('GITHUB_REF', raising=False)
    root = tmp_path / 'repo'
    root.mkdir()
    (root / 'src/articulate').mkdir(parents=True)
    for name in ('__init__', 'detector', 'masking', 'profiles', 'genres', 'modes'):
        shutil.copyfile(ROOT / f'src/articulate/{name}.py', root / f'src/articulate/{name}.py')
    init = root / 'src/articulate/__init__.py'
    init.write_text(re.sub(r'(?m)^__version__ = "[^"]+"$', '__version__ = "0.6.0"',
                          init.read_text(encoding='utf-8')), encoding='utf-8')
    (root / 'pyproject.toml').write_text('[project]\nversion = "0.6.0"\n')
    for relative in ('plugin.json', '.claude-plugin/plugin.json', '.codex-plugin/plugin.json'):
        path = root / 'claude-plugin' / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'version': '0.6.0'}))
    git(root, 'init', '-q')
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        'add', '.')
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        'commit', '-qm', 'fixture')
    git(root, 'tag', 'v0.6.0')
    return root


def test_tagged_clean_release_source_qualifies(release_source):
    result = load('native_release_source').qualify(release_source, '0.6.0', ref='refs/tags/v0.6.0')
    assert result['mode'] == 'release'
    assert result['commit'] == git(release_source, 'rev-parse', 'HEAD')


def test_patch_release_qualifies(release_source):
    # A bug fix ships as X.Y.Z with Z > 0; the tag, ref and ruleset checks still hold.
    helper = load('native_release_source')
    for path in ('src/articulate/__init__.py', 'pyproject.toml', 'claude-plugin/plugin.json',
                 'claude-plugin/.claude-plugin/plugin.json', 'claude-plugin/.codex-plugin/plugin.json'):
        target = release_source / path
        target.write_text(target.read_text(encoding='utf-8').replace('0.6.0', '0.6.1'), encoding='utf-8')
    git(release_source, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        'commit', '-qam', 'patch')
    with pytest.raises(ValueError, match='release source Git qualification failed'):
        helper.qualify(release_source, '0.6.1', ref='refs/tags/v0.6.1')
    git(release_source, 'tag', 'v0.6.1')
    result = helper.qualify(release_source, '0.6.1', ref='refs/tags/v0.6.1')
    assert (result['version'], result['tag']) == ('0.6.1', 'v0.6.1')
    with pytest.raises(ValueError, match='release ref must equal the version tag'):
        helper.qualify(release_source, '0.6.1', ref='refs/tags/v0.6.0')


@pytest.mark.parametrize('mutation', ['dirty', 'untracked', 'wrong-tag', 'missing-tag', 'ref', 'version', 'rules'])
def test_source_mutations_refuse_before_archive_output(release_source, tmp_path, mutation):
    if mutation == 'dirty':
        (release_source / 'pyproject.toml').write_text('[project]\nversion="0.7.0"\n')
    elif mutation == 'untracked':
        (release_source / 'extra.py').write_text('changed source')
    elif mutation == 'wrong-tag':
        git(release_source, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            'commit', '--allow-empty', '-qm', 'later')
    elif mutation == 'missing-tag':
        git(release_source, 'tag', '-d', 'v0.6.0')
    elif mutation == 'rules':
        (release_source / 'src/articulate/masking.py').write_text('changed rules')
    out = tmp_path / 'archive'
    with pytest.raises((ValueError, RuntimeError)):
        load('archive_native_articulate').archive(tmp_path / 'absent', out,
            '0.7.0' if mutation == 'version' else '0.6.0', root=release_source,
            release_ref='refs/heads/main' if mutation == 'ref' else None)
    assert not out.exists()


def test_dirty_builder_default_refuses_before_output(tmp_path, release_source):
    (release_source / 'extra.py').write_text('untracked source')
    out = tmp_path / 'build'
    with pytest.raises(ValueError):
        load('build_native_articulate').build(out, root=release_source)
    assert not out.exists()


def test_development_mode_is_explicit_and_keeps_version_alignment(release_source):
    (release_source / 'extra.py').write_text('development changes')
    helper = load('native_release_source')
    assert helper.qualify(release_source, '0.6.0', mode='dev')['mode'] == 'dev'
    with pytest.raises(ValueError, match='version'):
        helper.qualify(release_source, '0.7.0', mode='dev')


def test_release_source_rejects_inherited_wrong_ci_ref(release_source, monkeypatch):
    monkeypatch.setenv('GITHUB_REF', 'refs/heads/main')
    with pytest.raises(ValueError, match='release ref'):
        load('native_release_source').qualify(release_source, '0.6.0')


@pytest.mark.parametrize('failure', ['status', 'version', 'executable_sha256'])
def test_failed_native_validation_cannot_create_release_archive(release_source, tmp_path, monkeypatch, failure):
    import hashlib
    from test_native_package import payload
    stage = payload(tmp_path)
    mod = load('archive_native_articulate')
    result = {'status': 'PASS', 'version': '0.6.0',
              'executable_sha256': hashlib.sha256((stage / 'articulate-local.exe').read_bytes()).hexdigest()}
    result[failure] = 'wrong'
    monkeypatch.setattr(mod, 'check_native', lambda *args: result)
    with pytest.raises(ValueError, match='native validation'):
        mod.archive(stage, tmp_path / 'out', '0.6.0', root=release_source)
    assert not (tmp_path / 'out').exists()


def test_release_archive_uses_qualified_version_without_dev_claims(release_source, tmp_path, monkeypatch):
    import hashlib
    import zipfile
    from test_native_package import payload
    stage = payload(tmp_path)
    mod = load('archive_native_articulate')
    monkeypatch.setattr(mod, 'check_native', lambda *args: {
        'status': 'PASS', 'version': '0.6.0',
        'executable_sha256': hashlib.sha256((stage / 'articulate-local.exe').read_bytes()).hexdigest()})
    archives = mod.archive(stage, tmp_path / 'out', '0.6.0', root=release_source)
    for archive in archives:
        assert '-dev-' not in archive.name
        with zipfile.ZipFile(archive) as contents:
            manifest = json.loads(contents.read('manifest.json'))
            assert manifest['version'] == '0.6.0'
            assert 'development' not in contents.read('README.md').decode().lower()
            qualification = json.loads(contents.read('QUALIFICATION.json'))
            assert qualification['source']['tag'] == 'v0.6.0'
            assert qualification['native']['version'] == manifest['version']
