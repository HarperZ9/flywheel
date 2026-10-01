"""Installer CRT selection follows the actual toolset and coherent file versions."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'desktop/scripts/crt_selection.ps1'


def ps(body):
    shell = shutil.which('powershell') or shutil.which('pwsh')
    if shell is None:
        pytest.skip('PowerShell unavailable')
    literal = str(HELPER).replace("'", "''")
    env = dict(os.environ)
    # Python does not apply pwsh's native-child PSModulePath normalization for Windows PowerShell.
    env['PSModulePath'] = str(Path(shell).parent / 'Modules') + os.pathsep + env.get('PSModulePath', '')
    result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command',
                             f". '{literal}'\n" + body], capture_output=True, text=True, timeout=30, env=env)
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


def test_numeric_newest_selection_not_directory_order():
    result = json.loads(ps(MOCK + "(Select-CompatibleCrt @('old','preview','new') ([version]'14.50.35717')) | ConvertTo-Json -Depth 5"))
    assert result['directory'] == 'new' and result['version'] == '14.50.35719.0'
    assert len(result['files']) == 3


def test_mixed_runtime_set_cannot_win_even_with_newer_file():
    result = json.loads(ps(MOCK + "(Select-CompatibleCrt @('mixed','new') ([version]'14.50.35717')) | ConvertTo-Json -Depth 5"))
    assert result['directory'] == 'new'


def test_compatible_serviced_patch_differences_are_preserved():
    result = json.loads(ps(MOCK + "(Select-CompatibleCrt @('serviced') ([version]'14.50.35717')) | ConvertTo-Json -Depth 5"))
    assert result['version'] == '14.50.35719.0'
    assert {item['version'] for item in result['files']} == {'14.50.35719.0', '14.50.35720.0'}


@pytest.mark.parametrize('folders', ["@('old')", "@('mixed')", "@('missing')"])
def test_incompatible_incomplete_or_mixed_only_fails(folders):
    assert ps(MOCK + f"""
try {{ Select-CompatibleCrt {folders} ([version]'14.50.35717'); throw 'false success' }}
catch {{ if ($_.Exception.Message -notmatch 'compatible coherent') {{ throw }} }}
'PASS'
""") == 'PASS'


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
