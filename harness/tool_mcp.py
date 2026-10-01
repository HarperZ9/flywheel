"""Restricted, model-free stdio companion to the full Flywheel client."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import sys

from .cli_version import installed_version
from .path_identity import device_or_unc, remote_drive, reserved_device_name
from .receipt_operations import ReceiptOperationError, mcp_tool_descriptors, verify_receipt_inclusion
from .skill_resources import list_resources, read_resource

PROTOCOL = '2025-06-18'
TOOLS = [{
    'name': 'flywheel.tool_status', 'description': 'Report the local tool profile without probing models.',
    'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
}, *mcp_tool_descriptors()]
for _tool in TOOLS:
    _tool['annotations'] = {'readOnlyHint': True, 'destructiveHint': False,
                            'idempotentHint': True, 'openWorldHint': False}


def checked_path(value: str | Path, *, directory=True) -> Path:
    path = Path(value)
    if (not path.is_absolute() or device_or_unc(str(path)) or '..' in path.parts
            or reserved_device_name(str(path)) or remote_drive(str(path))):
        raise ValueError('select an absolute local path')
    for part in [path, *path.parents]:
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('linked paths are unavailable in the tool profile')
    if directory and (not path.is_dir() or path == Path(path.anchor)):
        raise ValueError('select an existing local directory below the volume root')
    return path.resolve(strict=True)


def parse_args(args: list[str]) -> tuple[Path, Path]:
    if len(args) != 4 or set(args[::2]) != {'--root', '--run-root'}:
        raise ValueError('tool MCP requires only --root WORKSPACE --run-root STATE')
    values = dict(zip(args[::2], args[1::2]))
    workspace, state = (checked_path(values[name]) for name in ('--root', '--run-root'))
    if workspace == state or workspace in state.parents or state in workspace.parents:
        raise ValueError('workspace and state must be separate directories')
    return workspace, state


def receipt_ledger(state: Path) -> dict:
    checked_path(state)
    folder = state / 'envelopes'
    if not folder.exists() and not folder.is_symlink():
        return {'envelopes': []}
    checked_path(folder)
    files = sorted(folder.glob('*.json'))
    if len(files) > 10000:
        raise ValueError('receipt inventory exceeds the tool profile limit')
    rows = []
    for path in files:
        safe = checked_path(path, directory=False)
        info = safe.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16_000_000 or info.st_nlink != 1:
            raise ValueError('receipt file is not a bounded regular file')
        with safe.open('rb') as stream:
            data = stream.read(16_000_001)
        after = checked_path(path, directory=False).stat()
        if len(data) > 16_000_000 or (info.st_ino, info.st_size, info.st_mtime_ns) != (
                after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError('receipt changed while reading')
        rows.append({'sha256': hashlib.sha256(data).hexdigest()})
    return {'envelopes': rows}


def tool_result(value, *, error=False):
    result = {'content': [{'type': 'text', 'text': json.dumps(value)}], 'structuredContent': value}
    if error:
        result['isError'] = True
    return result


def handle(request, workspace: Path, state: Path):
    rid = request.get('id') if isinstance(request, dict) else None
    def fail(code, message):
        return {'jsonrpc': '2.0', 'id': rid, 'error': {'code': code, 'message': message}}
    if (not isinstance(request, dict) or request.get('jsonrpc') != '2.0'
            or not isinstance(request.get('method'), str)
            or ('id' in request and type(rid) not in (int, str))):
        return fail(-32600, 'invalid request')
    method, params = request['method'], request.get('params', {})
    # Notifications carry no response ID. Ignore even unknown methods rather
    # than emitting an id:null reply that a real MCP client cannot correlate.
    if 'id' not in request:
        return None
    if not isinstance(params, dict):
        return fail(-32602, 'params must be an object')
    if '_meta' in params:
        metadata = params['_meta']
        if (not isinstance(metadata, dict) or ('progressToken' in metadata
                and type(metadata['progressToken']) not in (str, int))):
            return fail(-32602, 'invalid request metadata')
        # Request metadata is transport context only, never business arguments or authority.
        params = {key: value for key, value in params.items() if key != '_meta'}
    try:
        if method == 'initialize':
            value = {'protocolVersion': PROTOCOL, 'capabilities': {'tools': {}, 'resources': {}},
                     'serverInfo': {'name': 'flywheel-tools', 'version': installed_version()}}
        elif method == 'ping':
            value = {}
        elif method == 'tools/list':
            value = {'tools': TOOLS}
        elif method == 'resources/list':
            value = list_resources()
        elif method == 'resources/read':
            if set(params) != {'uri'}:
                return fail(-32602, 'only a public resource URI is accepted')
            value = read_resource(params['uri'])
        elif method == 'tools/call':
            name, args = params.get('name'), params.get('arguments', {})
            if set(params) - {'name', 'arguments'} or not isinstance(args, dict):
                return fail(-32602, 'invalid tool arguments')
            if name == 'flywheel.tool_status':
                if args:
                    return fail(-32602, 'status accepts no arguments')
                value = tool_result({'profile': 'local-evidence', 'version': installed_version(),
                    'model_calls': False, 'network': False, 'exec': False, 'write': False,
                    'does_not_prove': ['full client availability', 'model or endpoint health']})
            elif name == 'receipt.verify_inclusion':
                value = tool_result(verify_receipt_inclusion(args, ledger=lambda: receipt_ledger(state)))
            else:
                value = tool_result({'error': {'code': 'TOOL_UNAVAILABLE',
                    'message': 'the tool is unavailable in the local-evidence profile'}}, error=True)
        else:
            return fail(-32601, 'method unavailable in the local-evidence profile')
    except ReceiptOperationError as exc:
        value = tool_result({'error': {'code': exc.code, 'message': exc.message}}, error=True)
    except (KeyError, ValueError, OSError):
        return fail(-32602, 'resource or selected state unavailable')
    return {'jsonrpc': '2.0', 'id': rid, 'result': value}


def strict_json(line):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError('duplicate key')
            out[key] = value
        return out
    def nonfinite(_):
        raise ValueError('nonfinite value')
    return json.loads(line, object_pairs_hook=unique, parse_constant=nonfinite)


def main(args, stdin=None, stdout=None):
    try:
        workspace, state = parse_args(args)
    except (ValueError, OSError):
        return 2
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    while line := stdin.readline(1_000_001):
        if len(line) > 1_000_000:
            return 2
        try:
            response = handle(strict_json(line), workspace, state)
        except (ValueError, RecursionError):
            response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'invalid JSON'}}
        if response is not None:
            stdout.write(json.dumps(response) + '\n')
            stdout.flush()
    return 0
