"""Installer CRT selection follows the actual toolset and coherent file versions."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'desktop/scripts/crt_selection.ps1'

# One call takes about 0.4 s on a warm machine, process start included. The old
# 30 s limit failed once on a windows-latest shard (run 36886773490, attempt 1)
# on the first PowerShell launch of the file and passed on the rerun. The cause
# was not established; a cold launch that pays module load and the first script
# scan is the leading reading. The first launch now runs alone under a long
# limit, and every later call keeps a margin of about 300x.
PS_TIMEOUT = 120
PS_FIRST_LAUNCH_TIMEOUT = 240
_warm = {'done': False}


def _shell():
    shell = shutil.which('powershell') or shutil.which('pwsh')
    if shell is None:
        pytest.skip('PowerShell unavailable')
    return shell


def _run(shell, script, timeout):
    env = dict(os.environ)
    # Python does not apply pwsh's native-child PSModulePath normalization for Windows PowerShell.
    env['PSModulePath'] = str(Path(shell).parent / 'Modules') + os.pathsep + env.get('PSModulePath', '')
    # -NonInteractive and a closed stdin turn any prompt into an error instead of a wait.
    return subprocess.run([shell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                           '-Command', script], capture_output=True, text=True, timeout=timeout,
                          env=env, stdin=subprocess.DEVNULL)


def ps(body):
    shell = _shell()
    literal = str(HELPER).replace("'", "''")
    if not _warm['done']:
        warm = _run(shell, f". '{literal}'\n'WARM'", PS_FIRST_LAUNCH_TIMEOUT)
        assert warm.returncode == 0 and warm.stdout.strip() == 'WARM', warm.stdout + warm.stderr
        _warm['done'] = True
    result = _run(shell, f". '{literal}'\n" + body, PS_TIMEOUT)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


MOCK = r'''
function Get-CrtFileRecord([string]$Directory, [string]$Name) {
  $version = switch ($Directory) { 'old' {'14.29.30133.0'} 'new' {'14.50.35719.0'}
    'mixed' { if ($Name -eq 'vcruntime140_1.dll') {'14.29.30133.0'} else {'14.60.1.0'} }
    'serviced' { if ($Name -eq 'vcruntime140_1.dll') {'14.50.35720.0'} else {'14.50.35719.0'} }
    'preview' {'14.9.99999.0'} default { throw 'missing DLL' } }
  [pscustomobject]@{name=$Name; version=$version; sha256=('a'*64); machine='x64'}
}
'''


SELECTION_CASES = {
    'newest': "@('old','preview','new')",
    'mixed_vs_new': "@('mixed','new')",
    'serviced': "@('serviced')",
    'only_old': "@('old')",
    'only_mixed': "@('mixed')",
    'only_missing': "@('missing')",
}


@pytest.fixture(scope='module')
def selections():
    """Every mocked selection case in one PowerShell process.

    The cases share one mock and differ only in their folder list, so one launch
    runs them all. Each case reports either the selection or the error message,
    and each test below asserts on its own case.
    """
    lines = [MOCK, '$out = [ordered]@{}']
    for name, folders in SELECTION_CASES.items():
        lines.append(f"try {{ $out['{name}'] = @{{ ok = (Select-CompatibleCrt {folders} ([version]'14.50.35717')) }} }}"
                     f" catch {{ $out['{name}'] = @{{ error = $_.Exception.Message }} }}")
    lines.append('$out | ConvertTo-Json -Depth 6')
    return json.loads(ps('\n'.join(lines)))


def test_numeric_newest_selection_not_directory_order(selections):
    result = selections['newest']['ok']
    assert result['directory'] == 'new' and result['version'] == '14.50.35719.0'
    assert len(result['files']) == 3


def test_mixed_runtime_set_cannot_win_even_with_newer_file(selections):
    assert selections['mixed_vs_new']['ok']['directory'] == 'new'


def test_compatible_serviced_patch_differences_are_preserved(selections):
    result = selections['serviced']['ok']
    assert result['version'] == '14.50.35719.0'
    assert {item['version'] for item in result['files']} == {'14.50.35719.0', '14.50.35720.0'}


@pytest.mark.parametrize('case', ['only_old', 'only_mixed', 'only_missing'])
def test_incompatible_incomplete_or_mixed_only_fails(selections, case):
    outcome = selections[case]
    assert 'ok' not in outcome, f'false success: {outcome}'
    assert 'compatible coherent' in outcome['error']


def test_ps_calls_keep_a_timeout_margin_and_never_wait_on_input(monkeypatch):
    """The limit that failed was 30 s against a 0.4 s call. Pin the margin."""
    seen = []

    def fake_run(argv, **kwargs):
        seen.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout='WARM' if len(seen) == 1 else 'ok', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    monkeypatch.setitem(_warm, 'done', False)
    monkeypatch.setattr(shutil, 'which', lambda name: r'C:\fake\powershell.exe')
    assert ps("'ok'") == 'ok'
    (warm_argv, warm_kw), (call_argv, call_kw) = seen
    assert warm_kw['timeout'] >= 240 and call_kw['timeout'] >= 120
    for argv, kw in seen:
        assert '-NonInteractive' in argv and kw['stdin'] is subprocess.DEVNULL


def test_requirement_comes_from_generated_compiler_binding(tmp_path):
    folder = tmp_path / 'CMakeFiles/4.1.1'
    folder.mkdir(parents=True)
    (folder / 'CMakeCXXCompiler.cmake').write_text(
        'set(CMAKE_CXX_COMPILER "C:/VS/VC/Tools/MSVC/14.50.35717/bin/Hostx64/x64/cl.exe")\n'
        'set(CMAKE_CXX_COMPILER_ID "MSVC")\nset(CMAKE_CXX_COMPILER_VERSION "19.50.35721.0")\n')
    literal = str(tmp_path).replace("'", "''")
    result = json.loads(ps(f"Get-CrtBuildRequirement '{literal}' | ConvertTo-Json"))
    assert result['toolset_version'] == '14.50.35717'
    assert result['compiler_version'] == '19.50.35721.0'
    assert 'C:/VS' not in json.dumps(result)


def test_ambiguous_compiler_binding_refuses(tmp_path):
    for name, version in [('a', '14.44.1'), ('b', '14.50.1')]:
        folder = tmp_path / 'CMakeFiles' / name
        folder.mkdir(parents=True)
        (folder / 'CMakeCXXCompiler.cmake').write_text(
            f'set(CMAKE_CXX_COMPILER "C:/VS/VC/Tools/MSVC/{version}/bin/Hostx64/x64/cl.exe")\n'
            'set(CMAKE_CXX_COMPILER_ID "MSVC")\nset(CMAKE_CXX_COMPILER_VERSION "19.50.1.0")\n')
    literal = str(tmp_path).replace("'", "''")
    assert ps(f"""
try {{ Get-CrtBuildRequirement '{literal}'; throw 'false success' }}
catch {{ if ($_.Exception.Message -notmatch 'compiler binding') {{ throw }} }}
'PASS'
""") == 'PASS'


def test_builder_and_release_preserve_crt_receipt():
    builder = (ROOT / 'desktop/scripts/build_installer.ps1').read_text()
    assert 'Select-CompatibleCrt' in builder and 'Get-CrtBuildRequirement' in builder
    assert 'Stage-CrtSet' in builder
    assert 'crt-selection.json' in builder
    assert builder.index('$crtDir = Join-Path $repo "build\\crt"') < builder.index('"/DCrtDir=$crtDir"')
    workflow = (ROOT / '.github/workflows/desktop-release.yml').read_text()
    assert 'crt-selection.json' in workflow


@pytest.mark.parametrize('corrupt', [False, True])
def test_complete_stage_preserves_old_set_and_refuses_changed_source(tmp_path, corrupt):
    source, build = tmp_path / 'source', tmp_path / 'build'
    source.mkdir()
    old = build / 'crt'
    old.mkdir(parents=True)
    names = ('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')
    for name in names:
        (source / name).write_bytes(b'new fixture')
        (old / name).write_bytes(b'old fixture')
    source_ps, build_ps = (str(p).replace("'", "''") for p in (source, build))
    body = f"""
$files = @('msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll') | ForEach-Object {{
  [pscustomobject]@{{ name=$_; sha256=(Get-FileHash (Join-Path '{source_ps}' $_) -Algorithm SHA256).Hash.ToLowerInvariant() }}
}}
$selection = [pscustomobject]@{{ directory='{source_ps}'; files=$files }}
"""
    if corrupt:
        body += "$files[1].sha256 = '0' * 64\n"
        body += f"try {{ Stage-CrtSet $selection '{build_ps}'; throw 'false success' }} catch {{ if ($_.Exception.Message -notmatch 'source changed') {{ throw }} }}"
    else:
        body += f"Stage-CrtSet $selection '{build_ps}'"
    assert ps(body + "\n'PASS'") == 'PASS'
    expected = b'old fixture' if corrupt else b'new fixture'
    assert all((old / name).read_bytes() == expected for name in names)
    if not corrupt:
        backups = list(build.glob('crt-previous-*'))
        assert len(backups) == 1
        assert all((backups[0] / name).read_bytes() == b'old fixture' for name in names)


def test_non_x64_pe_is_refused(tmp_path):
    import struct
    pe = bytearray(128)
    pe[:2] = b'MZ'
    struct.pack_into('<I', pe, 60, 64)
    pe[64:68] = b'PE\0\0'
    struct.pack_into('<H', pe, 68, 0x14c)
    (tmp_path / 'msvcp140.dll').write_bytes(pe)
    literal = str(tmp_path).replace("'", "''")
    assert ps(f"try {{ Get-CrtFileRecord '{literal}' 'msvcp140.dll'; throw 'false success' }} catch {{ if ($_.Exception.Message -notmatch 'not x64') {{ throw }} }}\n'PASS'") == 'PASS'
