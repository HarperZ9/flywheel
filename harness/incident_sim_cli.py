"""Check a submitted synthetic incident trace and emit a local process audit."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .evidence_json import strict_load_json, strict_load_json_value
from .gateway_effect_offline import build_gateway_effect_component
from .incident_sim_eval import evaluate_incident_sim
from .incident_sim_packet import build_process_audit_packet, verify_process_audit_packet
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


def _read_value(source: str) -> tuple[object, dict]:
    path = Path(source).absolute()
    with open_artifact_root(path.parent, writable=False) as reader:
        raw = reader.read_bytes(path.name, max_bytes=MAX_BYTES)
    identity = {'sha256': hashlib.sha256(raw).hexdigest(), 'byte_length': len(raw)}
    return strict_load_json_value(raw, max_bytes=MAX_BYTES, max_depth=64), identity


def _error(code: str) -> int:
    print(json.dumps({'schema': 'flywheel.incident-sim-error/v1', 'error': code}))
    return 2


def _exit_for(verdict: str) -> int:
    return {'MATCH': 0, 'DRIFT': 1}.get(verdict, 3)


def _expected_gateway_hashes(args) -> dict | None:
    pairs = {
        "terminal_result_sha256": args.expected_gateway_terminal_result_sha256,
        "lifecycle_history_sha256": args.expected_gateway_lifecycle_history_sha256,
        "trace_records_sha256": args.expected_gateway_trace_records_sha256,
    }
    out = {key: value.lower() for key, value in pairs.items()
           if value is not None}
    return out or None


def _verify_packet(source: str, expected_hashes: dict | None = None) -> int:
    packet, identity = _read(source, None)
    verification = verify_process_audit_packet(packet, expected_hashes=expected_hashes)
    print(json.dumps({
        'schema': 'flywheel.incident-sim-verify-command/v1',
        'sources': {'packet': identity},
        'verification': verification,
        'does_not_prove': [
            'Semantic correctness of the task, trace, evaluation, scorer or access claim.',
            'External wall-clock truth, disclosure completeness or immutable history.',
        ],
    }, ensure_ascii=True, sort_keys=True, allow_nan=False))
    return _exit_for(verification['verdict'])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='flywheel incident-sim', description=__doc__)
    parser.add_argument('--task', help='local frozen incident task JSON')
    parser.add_argument('--trace', help='local submitted trace JSON')
    parser.add_argument('--expected-task-sha256')
    parser.add_argument('--expected-trace-sha256')
    parser.add_argument('--institutional-access', help='declared institutional access record JSON')
    parser.add_argument('--institutional-access-scope', help='institutional access scope JSON')
    parser.add_argument('--gateway-effect-component', help='typed gateway_effect component JSON')
    parser.add_argument('--gateway-terminal-result')
    parser.add_argument('--gateway-lifecycle-history')
    parser.add_argument('--gateway-trace-records')
    parser.add_argument('--verify-packet', help='offline recheck of emitted process-audit packet JSON')
    parser.add_argument('--expected-gateway-terminal-result-sha256')
    parser.add_argument('--expected-gateway-lifecycle-history-sha256')
    parser.add_argument('--expected-gateway-trace-records-sha256')
    args = parser.parse_args(argv)
    for digest in (
            args.expected_task_sha256, args.expected_trace_sha256,
            args.expected_gateway_terminal_result_sha256,
            args.expected_gateway_lifecycle_history_sha256,
            args.expected_gateway_trace_records_sha256):
        if digest is not None and (len(digest) != 64 or
                any(c not in '0123456789abcdefABCDEF' for c in digest)):
            return _error('INVALID_EXPECTED_DIGEST')
    build_options = [
        args.task, args.trace, args.expected_task_sha256, args.expected_trace_sha256,
        args.institutional_access, args.institutional_access_scope,
        args.gateway_effect_component, args.gateway_terminal_result,
        args.gateway_lifecycle_history, args.gateway_trace_records,
    ]
    if args.verify_packet is not None:
        if any(option is not None for option in build_options):
            return _error('CONFLICTING_OPTIONS')
        try:
            return _verify_packet(args.verify_packet, _expected_gateway_hashes(args))
        except (OSError, ValueError, PrivateArtifactError):
            return _error('INCIDENT_INPUT_REJECTED')
    if args.task is None or args.trace is None:
        return _error('TASK_TRACE_REQUIRED')
    if (args.institutional_access is None) != (args.institutional_access_scope is None):
        return _error('INSTITUTIONAL_ACCESS_PAIR_REQUIRED')
    gateway_sources = [
        args.gateway_terminal_result, args.gateway_lifecycle_history,
        args.gateway_trace_records]
    if args.gateway_effect_component is not None and any(gateway_sources):
        return _error('CONFLICTING_OPTIONS')
    if any(gateway_sources) and not all(gateway_sources):
        return _error('GATEWAY_EFFECT_INPUTS_REQUIRED')
    try:
        task, task_identity = _read(args.task, args.expected_task_sha256)
        trace, trace_identity = _read(args.trace, args.expected_trace_sha256)
        institutional_access = institutional_access_scope = None
        access_identity = scope_identity = None
        if args.institutional_access is not None:
            institutional_access, access_identity = _read(args.institutional_access, None)
            institutional_access_scope, scope_identity = _read(args.institutional_access_scope, None)
        gateway_effect = None
        gateway_identity = None
        if args.gateway_effect_component is not None:
            gateway_effect, gateway_identity = _read(args.gateway_effect_component, None)
        elif all(gateway_sources):
            terminal, terminal_identity = _read(args.gateway_terminal_result, None)
            lifecycle, lifecycle_identity = _read_value(args.gateway_lifecycle_history)
            records, records_identity = _read_value(args.gateway_trace_records)
            gateway_effect = build_gateway_effect_component(
                terminal_result=terminal,
                lifecycle_history=lifecycle,
                trace_records=records)
            gateway_identity = {
                "terminal_result": terminal_identity,
                "lifecycle_history": lifecycle_identity,
                "trace_records": records_identity,
            }
        evaluation = evaluate_incident_sim(task, trace)
        packet = build_process_audit_packet(
            task, trace,
            institutional_access=institutional_access,
            institutional_access_scope=institutional_access_scope,
            gateway_effect=gateway_effect,
        )
    except SourceDigestMismatch:
        return _error('SOURCE_DIGEST_MISMATCH')
    except (OSError, ValueError, PrivateArtifactError):
        return _error('INCIDENT_INPUT_REJECTED')
    sources = {'task': task_identity, 'trace': trace_identity}
    if access_identity is not None and scope_identity is not None:
        sources['institutional_access'] = access_identity
        sources['institutional_access_scope'] = scope_identity
    if gateway_identity is not None:
        sources['gateway_effect'] = gateway_identity
    result = {
        'schema': 'flywheel.incident-sim-command/v1',
        'sources': sources,
        'evaluation': evaluation, 'audit_packet': packet,
        'does_not_prove': [
            'Submitted actions actually executed or complete workstation observation.',
            'Model alignment, independent ground truth or security certification.',
        ],
    }
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    return _exit_for(evaluation['overall']['verdict'])


if __name__ == '__main__':
    raise SystemExit(main())
