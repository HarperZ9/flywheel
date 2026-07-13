# -*- mode: python ; coding: utf-8 -*-
# flywheel.spec -- PyInstaller spec for the `flywheel` umbrella exe.
#
# Renamed from local-harness.spec (kept alongside as a one-release shim). The
# entry point is the new thin dispatcher harness/cli_entry.py, which locates
# the repo root and delegates to scripts/run_harness_cli.py for all existing
# subcommands plus the new umbrella subcommands (lanes, loop-status, ...).


a = Analysis(
    ['C:\\dev\\local-model\\harness\\cli_entry.py'],
    pathex=['C:\\dev\\local-model'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='flywheel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
