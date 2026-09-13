"""Check a submitted synthetic incident trace and emit a local process audit."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .evidence_json import strict_load_json
from .incident_sim_eval import evaluate_incident_sim
from .incident_sim_packet import build_process_audit_packet
from .private_artifact_fs import PrivateArtifactError, open_artifact_root

MAX_BYTES = 1024 * 1024


class SourceDigestMismatch(ValueError):
    pass


def _read(source: str, expected: str | None) -> tuple[dict, dict]:
    path = Path(source).absolute()
    with open_artifact_root(path.parent, writable=False) as reader:
        raw = reader.read_bytes(path.name, max_bytes=MAX_BYTES)
    identity = {'sha256': hashlib.sha256(raw).hexdigest(), 'byte_length': len(raw)}
    if expected is not None and identity['sha256'] != expected.lower():
        raise SourceDigestMismatch()
    return strict_load_json(raw, max_bytes=MAX_BYTES, max_depth=32), identity


def _error(code: str) -> int:
    print(json.dumps({'schema': 'flywheel.incident-sim-error/v1', 'error': code}))
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='flywheel incident-sim', description=__doc__)
    parser.add_argument('--task', required=True, help='local frozen incident task JSON')
    parser.add_argument('--trace', required=True, help='local submitted trace JSON')
    parser.add_argument('--expected-task-sha256')
    parser.add_argument('--expected-trace-sha256')
    args = parser.parse_args(argv)
    for digest in (args.expected_task_sha256, args.expected_trace_sha256):
        if digest is not None and (len(digest) != 64 or
                any(c not in '0123456789abcdefABCDEF' for c in digest)):
            return _error('INVALID_EXPECTED_DIGEST')
    try:
        task, task_identity = _read(args.task, args.expected_task_sha256)
        trace, trace_identity = _read(args.trace, args.expected_trace_sha256)
        evaluation = evaluate_incident_sim(task, trace)
        packet = build_process_audit_packet(task, trace)
    except SourceDigestMismatch:
        return _error('SOURCE_DIGEST_MISMATCH')
    except (OSError, ValueError, PrivateArtifactError):
        return _error('INCIDENT_INPUT_REJECTED')
    result = {
        'schema': 'flywheel.incident-sim-command/v1',
        'sources': {'task': task_identity, 'trace': trace_identity},
        'evaluation': evaluation, 'audit_packet': packet,
        'does_not_prove': [
            'Submitted actions actually executed or complete workstation observation.',
            'Model alignment, independent ground truth or security certification.',
        ],
    }
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, allow_nan=False))
    return {'MATCH': 0, 'DRIFT': 1}.get(evaluation['overall']['verdict'], 3)


if __name__ == '__main__':
    raise SystemExit(main())
