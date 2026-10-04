"""Import Inspect JSON evidence locally; scorer claims are not independent proof."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from .inspect_evidence import (
    InspectImportError,
    import_inspect_log,
    import_inspect_log_with_unit_contract,
)
from .private_artifact_fs import BUSY, CONFLICT, PrivateArtifactError, open_artifact_root

# On Windows the artifact reader opens the file, and every directory above it,
# with read-only sharing, so it refuses while any other process holds one of
# them open for writing: a virus scanner, a search indexer or a sync client
# touching a file that was just written. That refusal used to surface as
# INSPECT_INPUT_REJECTED before the digest was compared, so the METR packet's
# changed-byte control read as a failure on Windows while the tampered input
# was still refused. A short bounded retry rides out a transient holder; a
# holder that stays reports INSPECT_INPUT_BUSY, never a digest verdict.
_SHARING_CODES = (BUSY, CONFLICT)
_RETRY_DELAYS = (0.05, 0.1, 0.2, 0.4, 0.8)


def _error(code: str, detail: str | None = None) -> int:
    body = {'schema': 'flywheel.inspect-import-error/v1', 'error': code}
    if detail:
        body['detail'] = detail
    print(json.dumps(body))
    return 2


def _read(path: Path, max_bytes: int) -> bytes:
    """Read through the private artifact reader, retrying a sharing refusal."""
    for delay in (*_RETRY_DELAYS, None):
        try:
            with open_artifact_root(path.parent, writable=False) as reader:
                return reader.read_bytes(path.name, max_bytes=max_bytes)
        except PrivateArtifactError as exc:
            if exc.code not in _SHARING_CODES or delay is None:
                raise
            time.sleep(delay)
    raise AssertionError('unreachable')


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
        raw = _read(path, 16 * 1024 * 1024)
        if raw.startswith(b'PK\x03\x04'):
            return _error('INSPECT_JSON_REQUIRED')
        if args.expected_sha256 is not None and (
            hashlib.sha256(raw).hexdigest() != args.expected_sha256.lower()
        ):
            return _error('SOURCE_DIGEST_MISMATCH')
        unit_raw = None
        if args.unit_contract:
            unit_path = Path(args.unit_contract).absolute()
            unit_raw = _read(unit_path, 8 * 1024 * 1024)
        result = (import_inspect_log(raw) if unit_raw is None
                  else import_inspect_log_with_unit_contract(raw, unit_raw))
    except PrivateArtifactError as exc:
        # The code names the refusal (for example UNSAFE_PATH or CONFLICT) and
        # never the file's content, so it is safe to print.
        if exc.code in _SHARING_CODES:
            return _error('INSPECT_INPUT_BUSY', exc.code)
        return _error('INSPECT_INPUT_REJECTED', exc.code)
    except (OSError, ValueError, InspectImportError) as exc:
        return _error('INSPECT_INPUT_REJECTED', type(exc).__name__)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, allow_nan=False))
    # Exit zero describes a complete import, never independent score verification.
    return 0 if result['assessment'] == 'reported' and _unit_contract_ok(result) else 3


if __name__ == '__main__':
    raise SystemExit(main())
