"""Qualify the actual model-free Flywheel companion using synthetic receipts."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from harness.skill_resources import list_resources, read_resource
from scripts.check_frozen_articulate import parse_replies, require
from scripts.frozen_gateway_receipt_smoke import (
    _payload, prepare_receipt_smoke_fixture, validate_fixture_proof, MISSING_LEAF)
from scripts.frozen_mcp_process import run_mcp_process

DENIED = ('local_agent_health', 'local_agent_chat', 'local_agent_run',
          'flywheel.context.health', 'flywheel.context.capture', 'flywheel.context.preflight', 'exec')


def req(rid, method, params):
    return {'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params}


def call(rid, name, arguments):
    return req(rid, 'tools/call', {'name': name, 'arguments': arguments})


def validate(rows, version, leaf):
    require(rows[1] == {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}, 'resources': {}},
                       'serverInfo': {'name': 'flywheel-tools', 'version': version}}, 'TOOL_MCP_IDENTITY')
    tools = rows[2].get('tools', [])
    require(len(tools) == 2 and {t['name'] for t in tools} ==
            {'flywheel.tool_status', 'receipt.verify_inclusion'}, 'TOOL_MCP_SURFACE')
    require(all(t.get('annotations') == {'readOnlyHint': True, 'destructiveHint': False,
                 'idempotentHint': True, 'openWorldHint': False} for t in tools), 'TOOL_MCP_HINTS')
    require(rows[3] == list_resources(), 'TOOL_MCP_RESOURCES')
    status = _payload(rows[4])
    require(status.get('profile') == 'local-evidence' and status.get('version') == version
            and all(status.get(key) is False for key in ('model_calls', 'network', 'exec', 'write')),
            'TOOL_MCP_GRANTS')
    good, missing, malformed = (_payload(rows[rid]) for rid in (5, 6, 7))
    require(rows[5].get('isError', False) is False and good.get('included') is True
            and good.get('status') == 'included', 'TOOL_MCP_INCLUDED')
    validate_fixture_proof(good['proof'], leaf)
    require(good.get('verification', {}).get('replayed') is True and good.get('does_not_prove'), 'TOOL_MCP_PROOF')
    require(rows[6].get('isError', False) is False and missing.get('included') is False
            and missing.get('status') == 'missing' and missing.get('proof') == {
                'leaf': MISSING_LEAF, 'merkle_root': good['proof']['merkle_root']}, 'TOOL_MCP_MISSING')
    require(rows[7].get('isError') is True and malformed.get('error', {}).get('code') == 'INVALID_LEAF',
            'TOOL_MCP_BAD_LEAF')
    for rid, resource in enumerate(list_resources()['resources'], 8):
        require(rows[rid] == read_resource(resource['uri']), 'TOOL_MCP_RESOURCE_BYTES')
    for rid in range(10, 10 + len(DENIED)):
        require(rows[rid].get('isError') is True and _payload(rows[rid]) == {
            'error': {'code': 'TOOL_UNAVAILABLE',
                      'message': 'the tool is unavailable in the local-evidence profile'}}, 'TOOL_MCP_ESCALATION')


def snapshot(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file()}


def check(executable, version):
    exe = Path(executable).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='flywheel-tool-mcp-') as temporary:
        base = Path(temporary)
        home, workspace, state = (base / name for name in ('home', 'workspace', 'state'))
        for folder in (home, workspace, state):
            folder.mkdir()
        # Existing fixture writes runs/envelopes; that exact directory is selected
        # as this profile's read-only state. It contains only synthetic bytes.
        leaf = prepare_receipt_smoke_fixture(state)
        selected = state / 'runs'
        before = snapshot(selected)
        windows = os.environ.get('SYSTEMROOT', 'C:/Windows')
        env = {'SYSTEMROOT': windows, 'WINDIR': windows, 'PATH': str(Path(windows) / 'System32')}
        env.update({key: str(home) for key in ('HOME', 'USERPROFILE', 'FLYWHEEL_HOME',
                                              'TMP', 'TEMP', 'APPDATA', 'LOCALAPPDATA')})
        env.update({'FLYWHEEL_LOCAL_AGENT_ALLOW_' + key: '1' for key in ('WRITE', 'EXEC', 'ONLINE')})
        requests = [req(1, 'initialize', {'protocolVersion': '2025-06-18', 'capabilities': {}}),
            req(2, 'tools/list', {}), req(3, 'resources/list', {}), call(4, 'flywheel.tool_status', {}),
            *[call(rid, 'receipt.verify_inclusion', {'leaf': value})
              for rid, value in enumerate((leaf, MISSING_LEAF, 'bad'), 5)]]
        requests += [req(rid, 'resources/read', {'uri': row['uri']})
                     for rid, row in enumerate(list_resources()['resources'], 8)]
        requests += [call(rid, name, {'online': True, 'allow_exec': True, 'allow_write': True})
                     for rid, name in enumerate(DENIED, 10)]
        wire = ''.join(json.dumps(request) + '\n' for request in requests)
        output = run_mcp_process(exe, ['--tool-mcp', '--root', str(workspace), '--run-root', str(selected)],
                                 home, env, wire)
        validate(parse_replies(output, set(range(1, 10 + len(DENIED)))), version, leaf)
        require(snapshot(selected) == before and not list(workspace.iterdir()), 'TOOL_MCP_WROTE_USER_ROOTS')
    return {'schema': 'flywheel.frozen-tool-mcp/v1', 'status': 'PASS', 'version': version,
            'executable_sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
            'public_resources': 2, 'refused_tools': list(DENIED), 'receipt_fixture_verified': True,
            'selected_roots_unchanged': True, 'python_on_path': False,
            'does_not_prove': ['global OS sandbox', 'clean device installation', 'marketplace acceptance']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--receipt', required=True)
    args = parser.parse_args()
    result = check(args.executable, args.expected_version)
    Path(args.receipt).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
