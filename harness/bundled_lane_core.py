"""Build-time source witnesses for fixed core MCP components.

The manifest witnesses entrypoint source bytes. The release payload hash binds
the frozen interpreter and dependency closure; this is not a whole-build hash.
"""
from pathlib import Path, PurePosixPath
import hashlib
import re

from .evidence_json import canonical_sha256

CORE_ENTRYPOINTS = {
    'local-model': ('harness.local_mcp', 'local_mcp.py'),
    'writing': ('harness.writing_mcp', 'writing_mcp.py'),
}


def manifest_file_row(value, source_path):
    if not isinstance(value, dict) or set(value) != {'path', 'bytes', 'sha256'}:
        return False
    path = value.get('path')
    if not isinstance(path, str) or not path.startswith(source_path + '/'):
        return False
    parsed = PurePosixPath(path)
    return (not parsed.is_absolute() and '\\' not in path
            and '..' not in parsed.parts and parsed.as_posix() == path
            and path.endswith('.py') and type(value.get('bytes')) is int
            and value['bytes'] >= 0 and isinstance(value.get('sha256'), str)
            and re.fullmatch(r'sha256:[a-f0-9]{64}', value['sha256']) is not None)


def build_core_descriptor(repo_root, name, *, commit):
    from .bundled_lane_admission import SCHEMA, SOURCE_ALGORITHM
    module, filename = CORE_ENTRYPOINTS[name]
    data = (Path(repo_root) / 'harness' / filename).read_bytes().replace(b'\r\n', b'\n')
    files = [{'path': 'harness/' + filename, 'bytes': len(data),
              'sha256': 'sha256:' + hashlib.sha256(data).hexdigest()}]
    return {
        'schema': SCHEMA, 'name': name, 'version': '0.1.0',
        'source': {'repo': 'https://github.com/HarperZ9/flywheel',
            'commit': commit, 'path': 'harness', 'algorithm': SOURCE_ALGORITHM,
            'file_count': len(files), 'bytes': len(data), 'files': files,
            'manifest_sha256': 'sha256:' + canonical_sha256(files)},
        'entrypoint': {'argv': ['--bundled-lane-mcp', name],
            'module': module, 'callable': 'serve', 'health_tool': name + '.status'},
        'allowed_tools': [name + '.status', name + '.doctor'],
        'does_not_prove': [
            'NOT_PROVES_PAYLOAD_IDENTITY: entrypoint source bytes are witnessed; '
            'the separate release receipt binds the interpreter and dependency payload.',
            'NOT_PROVES_WORKFLOW_SUCCESS: status and doctor do not execute a useful workflow.',
            'NOT_PROVES_PROVIDER_READINESS: no account, network or model readiness is attested.',
        ],
    }


def check_core_descriptor(repo_root, name):
    """Build gate: compare entrypoint bytes and descriptor with compiled pins."""
    from .bundled_lane_admission import _load_descriptor, _validate_descriptor
    from .bundled_lane_expectations import expected_bundled_lane
    expected = expected_bundled_lane(name)
    path = Path(repo_root) / 'packaging' / 'bundled-lanes' / (name + '.json')
    saved, load_codes = _load_descriptor(path)
    codes = list(load_codes)
    try:
        computed = build_core_descriptor(repo_root, name, commit=expected['source_commit'])
        codes.extend(_validate_descriptor(computed, expected))
        if saved != computed:
            codes.append('bundled_descriptor_source_drift')
    except (OSError, KeyError, ValueError):
        codes.append('bundled_source_manifest_unavailable')
    return {'lane': name, 'verdict': 'HOLD' if codes else 'PASS',
            'blocking_codes': list(dict.fromkeys(codes))}
