# PyInstaller spec for the frozen Flywheel gateway (onedir).
#
# Build (from the repo root):
#   python -m PyInstaller packaging/flywheel-gateway.spec --noconfirm
# Output: dist/flywheel-gateway/ -- the folder the desktop installer ships
# as its `engine/` payload. Console stays on: the gateway prints its
# endpoints, and the desktop launches it detached with stdio captured.
#
# site/ rides as datas so the gateway's static shell (REPO/site) resolves
# inside the bundle exactly as it does in a checkout: gateway.REPO is the
# parent of harness/, which in the bundle is _internal/.

from pathlib import Path

repo = Path(SPECPATH).parent

a = Analysis(
    [str(repo / "packaging" / "gateway_entry.py")],
    pathex=[str(repo)],
    datas=[(str(repo / "site"), "site")],
    hiddenimports=[],
    excludes=["tkinter", "matplotlib", "numpy", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="flywheel-gateway",
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="flywheel-gateway",
)
