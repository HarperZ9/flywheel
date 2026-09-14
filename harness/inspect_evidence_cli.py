"""Import Inspect JSON evidence locally; scorer claims are not independent proof."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .inspect_evidence import (
    InspectImportError,
    import_inspect_log,
    import_inspect_log_with_unit_contract,
)
from .private_artifact_fs import PrivateArtifactError, open_artifact_root


def _error(code: str) -> int:
    print(json.dumps({'schema': 'flywheel.inspect-import-error/v1', 'error': code}))
    return 2


def _unit_contract_ok(result: dict) -> bool:
    analysis = result.get('scorer_unit_analysis')
    if analysis is None:
        return True
    contracts = analysis.get('contracts') if type(analysis) is dict else None
    return (type(contracts) is list and contracts
            and all(type(item) is dict
                    and type(item.get('mapping_consistency')) is dict
                    and item['mapping_consistency'].get('status') == 'MATCH'
                    for item in contracts))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='flywheel import-inspect', description=__doc__)
    parser.add_argument('source', help='local Inspect JSON log or inspect log dump export')
    parser.add_argument('--expected-sha256', help='reject bytes that differ from this digest')
    parser.add_argument('--unit-contract',
                        help='optional flywheel.inspect-scorer-unit-contract/v1 sidecar JSON')
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
        unit_raw = None
        if args.unit_contract:
            unit_path = Path(args.unit_contract).absolute()
            with open_artifact_root(unit_path.parent, writable=False) as reader:
                unit_raw = reader.read_bytes(unit_path.name, max_bytes=8 * 1024 * 1024)
        result = (import_inspect_log(raw) if unit_raw is None
                  else import_inspect_log_with_unit_contract(raw, unit_raw))
    except (OSError, ValueError, PrivateArtifactError, InspectImportError):
        return _error('INSPECT_INPUT_REJECTED')
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, allow_nan=False))
    # Exit zero describes a complete import, never independent score verification.
    return 0 if result['assessment'] == 'reported' and _unit_contract_ok(result) else 3


if __name__ == '__main__':
    raise SystemExit(main())
