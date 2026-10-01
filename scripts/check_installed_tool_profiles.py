"""Check both restricted MCP profiles using the installed engine's exact bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.lanes_registry import LANES
from harness.tool_mcp import TOOLS
from scripts import check_frozen_articulate as articulate
from scripts import check_frozen_tool_mcp as tool_mcp
from scripts.build_native_mcp_bundle import frozen_identity
from scripts.check_installed_canon_context import _resolve_engine

LIMITS = [
    'The outer installed acceptance gate verifies the installer registry and payload manifest.',
    'This wrapper alone does not prove that the supplied root was installed by an installer.',
    'Only installed engine command profiles and synthetic local fixtures are exercised.',
    'No native client UI, voice, model quality, marketplace approval or global egress proof.',
    'Ordinary before/after identity checks do not prove adversarial TOCTOU immunity.',
]


def require(value, code):
    if not value:
        raise RuntimeError(code)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def bound_identity(engine, version, commit, expected_sha):
    require(digest(engine) == expected_sha, 'ENGINE_SHA256_MISMATCH')
    frozen_identity(engine.parent, {'head': commit, 'version': version, 'mode': 'release'})


def run(args, receipt):
    require(re.fullmatch('[0-9a-f]{40}', args.source_commit), 'SOURCE_COMMIT_INVALID')
    require(re.fullmatch('[0-9a-f]{64}', args.expected_engine_sha256), 'ENGINE_SHA256_INVALID')
    require(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', args.expected_version), 'VERSION_INVALID')
    engine = _resolve_engine(args.install_root)
    bound_identity(engine, args.expected_version, args.source_commit, args.expected_engine_sha256)
    receipt.update(source_commit=args.source_commit, version=args.expected_version,
                   engine_sha256=args.expected_engine_sha256, frozen_source_clean=True)
    receipt['stage'] = 'tool_mcp'
    tool = tool_mcp.check(engine, args.expected_version)
    require(tool.get('schema') == 'flywheel.frozen-tool-mcp/v1' and tool.get('status') == 'PASS'
            and tool.get('version') == args.expected_version
            and tool.get('executable_sha256') == args.expected_engine_sha256
            and tool.get('receipt_fixture_verified') is True
            and tool.get('selected_roots_unchanged') is True, 'TOOL_PROFILE_HELD')
    receipt['stage'] = 'articulate'
    art = {}
    version = LANES['articulate'].version
    articulate.check(engine, version, art)
    require(art.get('observed_version') == version
            and art.get('executable_sha256') == 'sha256:' + args.expected_engine_sha256
            and art.get('tool_names') == sorted(articulate.TOOLS)
            and all(art.get(key) is True for key in ('local_only', 'host_edit_roundtrip',
                    'numeric_change_refused', 'isolated_runtime_removed'))
            and art.get('backend_refusals') == 15 and art.get('sampling_requests') == 0,
            'ARTICULATE_PROFILE_HELD')
    receipt['stage'] = 'final_identity'
    bound_identity(engine, args.expected_version, args.source_commit, args.expected_engine_sha256)
    # Explicit projection: checker paths, exception text, request bodies and temporary roots stay local.
    receipt['profiles'] = {
        'tool_mcp': {'verdict': 'PASS', 'version': args.expected_version,
                     'tool_names': sorted(t['name'] for t in TOOLS),
                     'receipt_fixture_verified': True, 'selected_roots_unchanged': True},
        'articulate': {'verdict': 'PASS', 'version': version,
                       'tool_names': sorted(articulate.TOOLS), 'local_only': True,
                       'host_edit_roundtrip': True, 'numeric_change_refused': True,
                       'backend_refusals': 15, 'sampling_requests': 0},
    }
    receipt['identity_verified_before_after'] = True
    receipt['stage'] = 'complete'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root', type=Path, required=True)
    parser.add_argument('--expected-engine-sha256', required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = {'schema': 'flywheel.installed-tool-profiles/v1', 'verdict': 'HOLD',
               'registry_installation_verified': False, 'stage': 'identity', 'limits': LIMITS}
    try:
        run(args, receipt)
        receipt['verdict'] = 'PASS'
    except Exception:
        # Do not persist arbitrary exception text or checker output in uploaded receipts.
        receipt['failure'] = 'INSTALLED_PROFILE_ACCEPTANCE_FAILED'
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'schema': receipt['schema'], 'verdict': receipt['verdict']}))
    return 0 if receipt['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
