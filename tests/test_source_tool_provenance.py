"""Exact-tag provenance must survive Git status blind spots."""
from pathlib import Path
import subprocess

import pytest


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def fixture(tmp_path):
    git(tmp_path, 'init', '-q')
    git(tmp_path, 'config', 'user.name', 'Fixture')
    git(tmp_path, 'config', 'user.email', 'fixture@example.invalid')
    git(tmp_path, 'config', 'core.autocrlf', 'false')
    (tmp_path / '.gitignore').write_text('ignored/\n')
    (tmp_path / 'README.md').write_text('reviewed template\n')
    (tmp_path / 'review.json').write_text('{}\n')
    git(tmp_path, 'add', '.')
    git(tmp_path, 'commit', '-qm', 'fixture')
    git(tmp_path, 'tag', 'v1.2.0')
    return git(tmp_path, 'rev-parse', 'HEAD')


def test_valid_tag_does_not_authorize_an_ignored_untracked_template(tmp_path):
    from scripts.source_tool_provenance import check_inputs
    head = fixture(tmp_path)
    (tmp_path / 'ignored').mkdir()
    (tmp_path / 'ignored/README.md').write_text('not committed\n')
    assert git(tmp_path, 'status', '--porcelain') == ''
    with pytest.raises(ValueError, match='Git|tracked'):
        check_inputs(tmp_path, head, ['ignored/README.md'], release=True)
    rows = check_inputs(tmp_path, head, ['ignored/README.md'], release=False)
    assert rows['ignored/README.md']['matches_git'] is False
    assert rows['ignored/README.md']['git_sha256'] is None


@pytest.mark.parametrize('name', ['README.md', 'review.json'])
def test_assume_unchanged_template_or_review_cannot_claim_release(tmp_path, name):
    from scripts.source_tool_provenance import check_inputs
    head = fixture(tmp_path)
    git(tmp_path, 'update-index', '--assume-unchanged', name)
    (tmp_path / name).write_text('hidden modification\n')
    assert git(tmp_path, 'status', '--porcelain') == ''
    with pytest.raises(ValueError, match='Git|tracked'):
        check_inputs(tmp_path, head, [name], release=True)
    assert check_inputs(tmp_path, head, [name], release=False)[name]['matches_git'] is False


def test_git_lf_and_worktree_crlf_are_same_canonical_input(tmp_path):
    from scripts.source_tool_provenance import check_inputs
    head = fixture(tmp_path)
    (tmp_path / 'README.md').write_bytes(b'reviewed template\r\n')
    rows = check_inputs(tmp_path, head, ['README.md'], release=True)
    assert rows['README.md']['matches_git'] is True
    assert rows['README.md']['git_sha256'] == rows['README.md']['source_sha256']


def release_fixture(tmp_path, *, ignored_template=False):
    from scripts.source_tool_provenance import input_paths
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / 'repo'
    repo.mkdir()
    for name in input_paths(root):
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((root / name).read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
    if ignored_template:
        (repo / '.gitignore').write_text('/plugins/flywheel-tools/README.md\n')
    for args in (['init', '-q'], ['config', 'user.name', 'Fixture'],
                 ['config', 'user.email', 'fixture@example.invalid'],
                 ['config', 'core.autocrlf', 'false'], ['add', '.'], ['commit', '-qm', 'fixture']):
        git(repo, *args)
    import tomllib
    version = tomllib.loads((repo / 'pyproject.toml').read_text())['project']['version']
    git(repo, 'tag', 'v' + version)
    assert git(repo, 'status', '--porcelain') == ''
    return repo


def test_complete_release_builder_accepts_exact_committed_inputs(tmp_path):
    import json
    import zipfile
    from scripts.build_source_tool_plugin import bundle
    repo = release_fixture(tmp_path)
    archive = bundle(tmp_path / 'release', repo=repo)
    with zipfile.ZipFile(archive) as package:
        source = json.loads(package.read('SOURCE.json'))
    assert source['mode'] == 'release' and source['source_dirty'] is False
    assert all(row['matches_git'] for row in source['input_provenance'].values())


def test_builder_refuses_ignored_template_but_marks_development_dirty(tmp_path):
    import json
    import zipfile
    from scripts.build_source_tool_plugin import bundle
    repo = release_fixture(tmp_path, ignored_template=True)
    with pytest.raises(ValueError, match='tracked Git'):
        bundle(tmp_path / 'release', repo=repo)
    archive = bundle(tmp_path / 'development', repo=repo, dev=True)
    with zipfile.ZipFile(archive) as package:
        source = json.loads(package.read('SOURCE.json'))
    assert source['source_dirty'] is True and source['mode'] == 'development'
    assert source['input_provenance']['plugins/flywheel-tools/README.md']['matches_git'] is False


@pytest.mark.parametrize('name', ['plugins/flywheel-tools/README.md', 'scripts/source_tool_closure.json'])
def test_builder_refuses_assume_unchanged_input(tmp_path, name):
    from scripts.build_source_tool_plugin import bundle
    repo = release_fixture(tmp_path)
    git(repo, 'update-index', '--assume-unchanged', name)
    target = repo / name
    target.write_bytes(target.read_bytes() + b'\n')
    assert git(repo, 'status', '--porcelain') == ''
    with pytest.raises(ValueError, match='tracked Git|packaging code'):
        bundle(tmp_path / 'release', repo=repo)
