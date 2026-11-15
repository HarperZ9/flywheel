"""The frozen Windows binary must carry every package data file the server reads.

0.8.0 failed its release build because PyInstaller bundles imported modules only,
and the house voice spec under src/articulate/data was left out, so the server
crashed at start-up. This test reads the build command, so it runs on any OS
without PyInstaller.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts" / "build_native_articulate.py"


def _data_dirs():
    pkg = ROOT / "src" / "articulate"
    return sorted({p.parent.relative_to(pkg).as_posix() for p in pkg.rglob("*")
                   if p.is_file() and p.suffix not in (".py", ".pyc") and p.name != "py.typed"
                   and "__pycache__" not in p.parts})


def test_package_data_exists_to_bundle():
    assert "data" in _data_dirs()
    assert (ROOT / "src/articulate/data/house_voice_v2.json").is_file()


def test_every_package_data_folder_is_added_to_the_frozen_binary():
    source = BUILD.read_text(encoding="utf-8")
    for folder in _data_dirs():
        added = f"'--add-data', str(root / 'src/articulate/{folder}') + os.pathsep + 'articulate/{folder}'"
        assert added in source, f"src/articulate/{folder} is not bundled into the native build"


def test_package_data_is_part_of_the_build_source_hashes():
    source = BUILD.read_text(encoding="utf-8")
    assert "(root / 'src/articulate/data').glob('*.json')" in source
