"""An archive contains exactly the checked bundle, with reproducible bytes."""
import hashlib
import os
from pathlib import Path
import subprocess
import zipfile

import pytest

from claude_plugin_helpers import load

build = load('build_claude_plugin')


def test_archive_is_reproducible_and_excludes_git(tmp_path):
    archive = load('archive_claude_plugin')
    plugin = tmp_path / 'plugin'
    build.build(plugin)
    (plugin / '.git').mkdir()
    (plugin / '.git' / 'private-note').write_text('must not ship')
    first = archive.archive(plugin, tmp_path / 'one')
    second = archive.archive(plugin, tmp_path / 'two')
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as z:
        expected = sorted(p.relative_to(plugin).as_posix() for p in plugin.rglob('*')
                          if p.is_file() and '.git' not in p.relative_to(plugin).parts)
        assert z.namelist() == expected
        for name in expected:
            assert z.read(name) == (plugin / name).read_bytes()
    digest = hashlib.sha256(first.read_bytes()).hexdigest()
    assert (first.parent / 'SHA256SUMS').read_text() == f'{digest}  {first.name}\n'


def test_archive_refuses_invalid_bundle_and_nested_destination(tmp_path):
    archive = load('archive_claude_plugin')
    plugin = tmp_path / 'plugin'
    build.build(plugin)
    with pytest.raises(ValueError, match='outside'):
        archive.archive(plugin, plugin / 'artifacts')
    (plugin / '.env').write_text('SECRET=planted')
    with pytest.raises(ValueError, match='credential'):
        archive.archive(plugin, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_archive_refuses_resolved_escape_before_reading(tmp_path, monkeypatch):
    from pathlib import Path
    archive = load('archive_claude_plugin')
    plugin = tmp_path / 'plugin'
    build.build(plugin)
    linked = plugin / 'server' / 'linked.txt'
    linked.write_text('inside')
    outside = tmp_path / 'outside.txt'
    outside.write_text('synthetic outside sentinel')
    resolve = Path.resolve
    read = Path.read_bytes
    monkeypatch.setattr(Path, 'resolve', lambda self, *a, **kw:
                        outside if self == linked else resolve(self, *a, **kw))
    def protected_read(self):
        assert self not in (linked, outside), 'escaped file was read'
        return read(self)
    monkeypatch.setattr(Path, 'read_bytes', protected_read)
    with pytest.raises(ValueError, match='outside'):
        archive.archive(plugin, tmp_path / 'out')
    assert 'outside' in '; '.join(archive.rules.check_bundle(plugin))


@pytest.mark.skipif(os.name != 'nt', reason='Windows junction boundary')
@pytest.mark.parametrize('link_path', ['server/linked', '.git'])
def test_junction_cannot_read_outside_directory(tmp_path, monkeypatch, link_path):
    archive = load('archive_claude_plugin')
    plugin = tmp_path / 'plugin'
    build.build(plugin)
    outside = tmp_path / 'outside'
    outside.mkdir()
    sentinel = outside / 'synthetic-sentinel.md'
    sentinel.write_text('synthetic test content only')
    junction = plugin / link_path
    # Create and remove the link itself; never recursively remove its target.
    script = ("$ErrorActionPreference = 'Stop'; New-Item -ItemType Junction "
              "-Path $env:ARTICULATE_TEST_LINK -Target $env:ARTICULATE_TEST_TARGET | Out-Null")
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                    script], check=True, capture_output=True,
                   env=dict(os.environ, ARTICULATE_TEST_LINK=str(junction),
                            ARTICULATE_TEST_TARGET=str(outside)))
    read_bytes, read_text, iterdir = Path.read_bytes, Path.read_text, Path.iterdir
    def guard(path):
        assert path != outside and outside not in path.parents
        assert path != junction and junction not in path.parents
    def guarded_bytes(path):
        guard(path)
        return read_bytes(path)
    def guarded_text(path, *args, **kwargs):
        guard(path)
        return read_text(path, *args, **kwargs)
    def guarded_iterdir(path):
        guard(path)
        return iterdir(path)
    monkeypatch.setattr(Path, 'read_bytes', guarded_bytes)
    monkeypatch.setattr(Path, 'read_text', guarded_text)
    monkeypatch.setattr(Path, 'iterdir', guarded_iterdir)
    try:
        if link_path == '.git':
            # Git metadata is ignored by all validation and archive passes.
            assert archive.rules.check_files(plugin) == []
            assert archive.rules.check_bundle(plugin) == []
            target = archive.archive(plugin, tmp_path / 'out')
            with zipfile.ZipFile(target) as bundle:
                assert not any(name.startswith('.git/') for name in bundle.namelist())
        else:
            assert 'reparse' in '; '.join(archive.rules.check_files(plugin))
            assert 'reparse' in '; '.join(archive.rules.check_bundle(plugin))
            with pytest.raises(ValueError, match='reparse'):
                archive.archive(plugin, tmp_path / 'out')
            assert not (tmp_path / 'out').exists()
    finally:
        os.rmdir(junction)
    assert read_text(sentinel) == 'synthetic test content only'


def test_mcpb_reuses_source_and_declares_required_python(tmp_path):
    import json
    import os
    import sys
    archive = load('archive_claude_plugin')
    smoke = load('smoke_claude_plugin')
    plugin = tmp_path / 'plugin'
    build.build(plugin)
    mcpb = archive.archive(plugin, tmp_path / 'one', format='mcpb')
    second = archive.archive(plugin, tmp_path / 'two', format='mcpb')
    assert mcpb.suffix == '.mcpb'
    assert mcpb.read_bytes() == second.read_bytes()
    extracted = tmp_path / 'installed extension with spaces'
    with zipfile.ZipFile(mcpb) as z:
        manifest = json.loads(z.read('manifest.json'))
        names = set(z.namelist())
        assert names == {'manifest.json'} | {
            p.relative_to(plugin).as_posix() for p in plugin.rglob('*')
            if p.is_file() and (p.relative_to(plugin).parts[0] in ('src', 'server')
                                or p.name in ('LICENSE', 'README.md', 'PRIVACY.md', 'SECURITY.md'))}
        for name in names - {'manifest.json'}:
            assert z.read(name) == (plugin / name).read_bytes()
        z.extractall(extracted)
    identity = json.loads((plugin / 'plugin.json').read_text())
    assert (manifest['name'], manifest['version']) == (identity['name'], identity['version'])
    assert manifest['manifest_version'] == '0.3'
    assert manifest['server']['type'] == 'python'
    assert manifest['server']['entry_point'] == 'server/serve.py'
    assert manifest['compatibility'] == {'platforms': ['darwin', 'win32'],
                                          'runtimes': {'python': '>=3.9'}}
    user = manifest['user_config']['python_path']
    assert user['required'] is True and user['type'] == 'file'
    assert 'default' not in user
    cfg = manifest['server']['mcp_config']
    assert cfg['command'] == '${user_config.python_path}'
    assert cfg['args'][-1] == '${__dirname}/server/serve.py'
    argv = [sys.executable] + [s.replace('${__dirname}', extracted.as_posix()) for s in cfg['args']]
    answers, code, stderr = smoke.exchange(argv, dict(os.environ, **cfg['env']))
    results = smoke.evaluate(answers, code, manifest['version'])
    assert all(ok for _, ok, _ in results), (results, stderr)
    digest = hashlib.sha256(mcpb.read_bytes()).hexdigest()
    assert (mcpb.parent / 'SHA256SUMS').read_text() == f'{digest}  {mcpb.name}\n'


def test_both_formats_have_one_complete_checksum_file(tmp_path):
    archive = load('archive_claude_plugin')
    plugin, output = tmp_path / 'plugin', tmp_path / 'out'
    build.build(plugin)
    assert archive.main([str(plugin), str(output), '--format', 'both']) == 0
    lines = (output / 'SHA256SUMS').read_text().splitlines()
    assert len(lines) == 2
    assert {Path(line.split('  ')[1]).suffix for line in lines} == {'.zip', '.mcpb'}
    for line in lines:
        digest, name = line.split('  ')
        assert digest == hashlib.sha256((output / name).read_bytes()).hexdigest()
