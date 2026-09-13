"""Import Inspect JSON evidence locally; scorer claims are not independent proof."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .inspect_evidence import InspectImportError, import_inspect_log
from .private_artifact_fs import PrivateArtifactError, open_artifact_root


def _error(code: str) -> int:
    print(json.dumps({'schema': 'flywheel.inspect-import-error/v1', 'error': code}))
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='flywheel import-inspect', description=__doc__)
    parser.add_argument('source', help='local Inspect JSON log or inspect log dump export')
    parser.add_argument('--expected-sha256', help='reject bytes that differ from this digest')
    args = parser.parse_args(argv)
    path = Path(args.source).absolute()
    if path.suffix.lower() == '.eval':
        return _error('INSPECT_JSON_REQUIRED')
    if args.expected_sha256 is not None and (
        len(args.expected_sha256) != 64
        or any(c not in '0123456789abcdefABCDEF' for c in args.expected_sha256)
    ):
        return _error('INVALID_EXPECTED_DIGEST')
    try:
        with open_artifact_root(path.parent, writable=False) as reader:
            raw = reader.read_bytes(path.name, max_bytes=16 * 1024 * 1024)
        if raw.startswith(b'PK\x03\x04'):
            return _error('INSPECT_JSON_REQUIRED')
        if args.expected_sha256 is not None and (
            hashlib.sha256(raw).hexdigest() != args.expected_sha256.lower()
        ):
            return _error('SOURCE_DIGEST_MISMATCH')
        result = import_inspect_log(raw)
    except (OSError, ValueError, PrivateArtifactError, InspectImportError):
        return _error('INSPECT_INPUT_REJECTED')
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, allow_nan=False))
    # Exit zero describes a complete import, never independent score verification.
    return 0 if result['assessment'] == 'reported' else 3


if __name__ == '__main__':
    raise SystemExit(main())
