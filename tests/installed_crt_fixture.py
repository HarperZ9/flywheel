"""CRT receipt and installed-manifest fixtures copied from installed acceptance runs.

GOOD_FILES: run 36842151728 (Redist 14.51.36247.0, PASS). OLD_FILES: run
36839153961 (Redist 14.29.30133, crashed on native close in MSVCP140.dll).
"""

GOOD_FILES = {
    'msvcp140.dll': '7c26614e1d733892c2deac7e245ce115504b1d80592dd0a01b08e3e5a55f89ca',
    'vcruntime140.dll': 'd1f4225df2cd877dbf130d5668a021dce3f94118455ff5ec952061c30afc9ce7',
    'vcruntime140_1.dll': 'a7146c08f89fe5b04541ab507cdb59ff7b44534d4ba3c668a426c6450a03434e',
}
OLD_FILES = {  # Redist 14.29.30133 staged by the crashing runs.
    'msvcp140.dll': '75872c426555ac8af55b5a7f6d4aea8831af74353b22612850a2bfc40e3b67e1',
    'vcruntime140.dll': '270ba17bf89cc2eb6e6ce536eb78e4614ab5499f653ab7e07fe9e3d33bf3b6e3',
    'vcruntime140_1.dll': 'f3754fc6ec87bcf84e05f3287b5de7bd305a30a0e1db7d478cb6353600682784',
}


def crt_receipt(files, version):
    return {
        'schema': 'flywheel.windows-crt-selection/v1', 'architecture': 'x64',
        'runtime_floor_version': version, 'toolset_version': '14.51.36231',
        'compiler_version': '19.51.36257.0',
        'files': [{'name': n, 'version': version, 'machine': 'x64', 'sha256': h}
                  for n, h in files.items()],
        'compatibility_basis': 'fixture'}


def build_manifest(files):
    entries = [{'origin': 'build', 'path': 'flywheel_desktop.exe', 'sha256': 'b' * 64, 'size': 1}]
    entries += [{'origin': 'build', 'path': n, 'sha256': h, 'size': 1} for n, h in files.items()]
    return {'schema': 'flywheel.installed-build-manifest/v1', 'version': '1.2.0',
            'payload': {'schema': 'flywheel.installed-payload/v1', 'files': entries}}
